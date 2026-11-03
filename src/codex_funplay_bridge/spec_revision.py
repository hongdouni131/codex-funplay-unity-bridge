"""Apply selected, freshly measured diagnostic proposals to a NEW Spec version only."""
from __future__ import annotations

import copy
import json
from typing import Any

from .broker import BridgeError
from .spec_selection_merge import fingerprint, node_index


def revise_spec(spec: dict[str, Any], diagnosis: dict[str, Any], issue_ids_json: str,
                output_prefab_path: str) -> dict[str, Any]:
    if diagnosis.get("complete") is not True or diagnosis.get("status") != "diagnosed":
        raise BridgeError("diagnosis_incomplete", "A complete fresh saved-Prefab diagnosis is required")
    if not isinstance(issue_ids_json, str) or len(issue_ids_json) > 8192:
        raise BridgeError("invalid_arguments", "issue_ids_json must be a bounded JSON string array")
    try:
        ids = json.loads(issue_ids_json)
    except (ValueError, TypeError) as exc:
        raise BridgeError("invalid_arguments", "issue_ids_json is invalid") from exc
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 64 or
            any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids)):
        raise BridgeError("invalid_arguments", "Select 1..64 unique diagnostic issue IDs")
    if not isinstance(output_prefab_path, str) or output_prefab_path == spec.get("outputPrefabPath"):
        raise BridgeError("new_output_required", "Revision must use a different new Prefab output path")
    issues = {i["issueId"]: i for i in diagnosis.get("issues", [])}
    revised = copy.deepcopy(spec)
    nodes = node_index(revised)
    changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for issue_id in ids:
        issue = issues.get(issue_id)
        if issue is None or not issue.get("suggestedChanges"):
            raise BridgeError("unsupported_revision", "Issue has no deterministic proposal; inspect its evidence manually", {"issueId": issue_id})
        for patch in issue["suggestedChanges"]:
            node_id, field = patch["nodeId"], patch["field"]
            if field not in {"placement.anchoredPosition", "style.imageType", "style.border"} or (node_id, field) in seen:
                raise BridgeError("conflicting_revision", "Diagnostic proposals conflict or exceed the revision allowlist")
            seen.add((node_id, field))
            node = nodes.get(node_id)
            parent, key = field.split(".")
            if node is None or not isinstance(node.get(parent), dict):
                raise BridgeError("spec_stale", "Diagnostic target does not exist")
            target = node[parent]
            if (key in target) != patch["beforeExists"] or target.get(key) != patch["before"]:
                raise BridgeError("spec_stale", "Spec field differs from measured evidence", {"nodeId": node_id, "field": field})
            target[key] = copy.deepcopy(patch["after"])
            changes.append({**copy.deepcopy(patch), "evidenceIssueId": issue_id})
    before_path = revised["outputPrefabPath"]
    revised["outputPrefabPath"] = output_prefab_path
    return {"status": "revised_requires_prepare", "spec": revised, "changes": changes,
            "outputChange": {"before": before_path, "after": output_prefab_path},
            "baseSpecFingerprint": fingerprint(spec), "revisedSpecFingerprint": fingerprint(revised),
            "diagnosisFingerprint": diagnosis["diagnosisFingerprint"],
            "writesPerformed": False, "requiresGenerationConfirmation": True,
            "nextStep": "Run Prepare, display the full plan and obtain developer confirmation before generating once. Re-diagnose the new Prefab and compare screenshots/input. This response writes no files."}
