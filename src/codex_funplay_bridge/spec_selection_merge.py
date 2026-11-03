"""Pure, bounded Sprite-reference patches. No file writes or Unity side effects."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from .broker import BridgeError

SPRITE_FIELDS = ("spritePath", "spriteGuid", "spriteName", "spriteLocalFileId", "imageType", "border")


def parse_spec(spec_json: str) -> dict[str, Any]:
    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite number")
        return number

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        spec = json.loads(spec_json, object_pairs_hook=unique_pairs, parse_float=finite_float,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (TypeError, ValueError, RecursionError) as exc:
        raise BridgeError("invalid_arguments", "Spec must be JSON with unique fields and finite numbers") from exc
    if not isinstance(spec, dict) or spec.get("schemaVersion") != 2 or not isinstance(spec.get("root"), dict):
        raise BridgeError("invalid_arguments", "A v2 composition Spec is required")
    return spec


def fingerprint(spec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def node_index(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    pending = [(spec["root"], 0)]
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise BridgeError("invalid_arguments", "Every Spec node must have a string id")
        if node["id"] in result or len(result) >= 256 or depth > 32:
            raise BridgeError("invalid_arguments", "Spec node ids must be unique within a bounded tree")
        result[node["id"]] = node
        children = node.get("children", [])
        if not isinstance(children, list):
            raise BridgeError("invalid_arguments", "Spec children must be an array")
        pending.extend((child, depth + 1) for child in reversed(children))
    return result


def merge_selection(spec: dict[str, Any], base_fingerprint: str,
                    selections: list[dict[str, Any]]) -> dict[str, Any]:
    if fingerprint(spec) != base_fingerprint:
        raise BridgeError("spec_stale", "Spec changed after candidate selection began; create a new session")
    merged = copy.deepcopy(spec)
    nodes = node_index(merged)
    changed_nodes, changes = set(), []
    reuse: dict[tuple[str, str, str], list[str]] = {}
    for selection in selections:
        node_id = selection["specNodeId"]
        if node_id in changed_nodes:
            raise BridgeError("ambiguous_mapping", "Multiple usage slots map to the same Spec node", {"nodeId": node_id})
        node = nodes.get(node_id)
        if node is None or node.get("type") not in {"Panel", "Button", "Toggle", "Slider"}:
            raise BridgeError("invalid_mapping", "Sprite slot must map to an existing image node", {"nodeId": node_id})
        if not isinstance(node.get("style"), dict):
            raise BridgeError("invalid_mapping", "Mapped node needs a style object", {"nodeId": node_id})
        changed_nodes.add(node_id)
        selected_style = selection["style"]
        if set(selected_style) - set(SPRITE_FIELDS):
            raise BridgeError("invalid_selection", "Selection contains fields outside the Sprite-reference allowlist")
        before = copy.deepcopy(node["style"])
        # Remove obsolete Multiple selectors or Sliced Border when switching to Single or Simple.
        after = {key: value for key, value in before.items() if key not in SPRITE_FIELDS}
        after.update(copy.deepcopy(selected_style))
        node["style"] = after
        for field in SPRITE_FIELDS:
            if (field in before) == (field in after) and before.get(field) == after.get(field):
                continue
            changes.append({"nodeId": node_id, "field": "style." + field,
                            "operation": "remove" if field not in after else "replace" if field in before else "add",
                            "before": before.get(field), "after": after.get(field)})
        key = (selection["sourcePath"], selection["sourceGuid"], selection["spriteLocalFileId"])
        reuse.setdefault(key, []).append(node_id)
    return {
        "status": "merged_requires_validation", "spec": merged,
        "baseSpecFingerprint": base_fingerprint, "mergedSpecFingerprint": fingerprint(merged),
        "changes": changes, "mappedNodeIds": sorted(changed_nodes),
        "reusedResources": [{"path": key[0], "guid": key[1], "localFileId": key[2], "nodeIds": ids}
                            for key, ids in reuse.items() if len(ids) > 1],
        "writesPerformed": False, "requiresGenerationConfirmation": True,
    }
