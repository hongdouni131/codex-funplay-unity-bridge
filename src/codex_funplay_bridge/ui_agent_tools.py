"""Named, project-scoped MCP tools for the UI Agent Unity package."""

from __future__ import annotations

import json
import re
import threading
import time
import base64
import mimetypes
import math
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Literal

from .audit_logging import AuditLogger
from .broker import BridgeError, FunplayBroker
from .config import BridgeConfig
from .ui_agent_runtime import MAX_TRUSTED_DATA_CODE_LENGTH, call_guarded_command, csharp_string_literal
from .sprite_selection import SpriteSelectionSessions, enrich_selection_slot
from .spec_selection_merge import fingerprint as spec_fingerprint, parse_spec, node_index, merge_selection
from .spec_revision import revise_spec

MAX_SPEC_LENGTH = 16_384
MAX_COMPOSITION_SPEC_LENGTH = 65_536
MAX_FONT_PATH_LENGTH = 240
MAX_AUDIT_PAGES = 100
AUDIT_PAGE_SIZE = 500
_FINGERPRINT = re.compile(r"^[0-9a-fA-F]{64}$")


class UiAgentTools:
    def __init__(
        self,
        config_loader: Callable[[], BridgeConfig],
        broker_factory: Callable[[BridgeConfig], FunplayBroker] = FunplayBroker,
    ) -> None:
        self._config_loader = config_loader
        self._broker_factory = broker_factory
        self._lock = threading.RLock()
        self._prepared: OrderedDict[str, tuple[float, str, str, str]] = OrderedDict()
        self._composition_prepared: OrderedDict[str, tuple[float, str, str]] = OrderedDict()
        self._audit: dict[str, Any] | None = None
        self._sprite_selection_sessions = SpriteSelectionSessions()

    def find_sprites(self, source_path: str, name_contains: str = "", offset: int = 0,
                     limit: int = 50, catalog_fingerprint: str | None = None) -> dict[str, Any]:
        _validate_assets_path(source_path)
        if not isinstance(name_contains, str) or len(name_contains) > 64 or any(ord(c) < 32 for c in name_contains):
            raise BridgeError("invalid_arguments", "name_contains must be at most 64 characters without controls")
        if type(offset) is not int or not 0 <= offset <= 10_000 or type(limit) is not int or not 1 <= limit <= 100:
            raise BridgeError("invalid_arguments", "offset must be 0..10000 and limit must be 1..100")
        if catalog_fingerprint is not None and (not isinstance(catalog_fingerprint, str) or not _FINGERPRINT.fullmatch(catalog_fingerprint)):
            raise BridgeError("invalid_arguments", "catalog_fingerprint must be a SHA-256 hex string")
        if offset and catalog_fingerprint is None:
            raise BridgeError("invalid_arguments", "Subsequent pages require the first page's catalog_fingerprint")
        return self._execute("ui_agent_find_sprites",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionSpriteCatalog.QueryJson("
            f"{_csharp_data(source_path)}, {_csharp_data(name_contains)}, {offset}, {limit}, "
            f"{_csharp_data(catalog_fingerprint) if catalog_fingerprint is not None else 'null'}));")

    def audit_sprite_imports(self, source_path: str) -> dict[str, Any]:
        _validate_assets_path(source_path)
        return self._execute("ui_agent_audit_sprite_imports",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionSpriteImportAuditor.AuditJson("
            f"{_csharp_data(source_path)}));")

    def create_sprite_selection_session(self, source_path: str, catalog_fingerprint: str,
                                        slots_json: str, spec_json: str | None = None) -> dict[str, Any]:
        _validate_assets_path(source_path)
        if not isinstance(catalog_fingerprint, str) or not _FINGERPRINT.fullmatch(catalog_fingerprint):
            raise BridgeError("invalid_arguments", "catalog_fingerprint must be a SHA-256 hex string")
        try:
            if not isinstance(slots_json, str) or len(slots_json.encode("utf-16-le")) // 2 > 16_384:
                raise BridgeError("invalid_arguments", "slots_json must not exceed 16384 UTF-16 units")
            raw_slots = json.loads(slots_json)
        except (TypeError, UnicodeEncodeError, json.JSONDecodeError) as exc:
            raise BridgeError("invalid_arguments", "slots_json must contain a JSON array") from exc
        if not isinstance(raw_slots, list) or not 1 <= len(raw_slots) <= 12:
            raise BridgeError("invalid_arguments", "slots_json must contain 1..12 usage slots")

        if spec_json is not None:
            _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        bound_spec = parse_spec(spec_json) if spec_json is not None else None
        bound_nodes = node_index(bound_spec) if bound_spec is not None else None

        config = self._config_loader()
        if config.unity_project_root is None:
            raise BridgeError("project_identity_unverified", "This Bridge configuration has no Unity project root")
        layout = self._measure_layout(spec_json, config) if bound_spec is not None else None
        measured_nodes = {entry["nodeId"]: entry for entry in layout["nodes"]} if layout else None
        sprites = self._read_complete_catalog(source_path, catalog_fingerprint, config)
        lookup = {(sprite.get("path"), sprite.get("guid"), sprite.get("localFileId")): sprite for sprite in sprites}
        slots: list[dict[str, Any]] = []
        total_candidates = 0
        total_preview_bytes = 0
        slot_ids: set[str] = set()
        mapped_ids: set[str] = set()
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                raise BridgeError("invalid_arguments", "Each usage slot must be an object")
            slot_id, label, description = raw_slot.get("id"), raw_slot.get("label"), raw_slot.get("description", "")
            usage_hint = raw_slot.get("usageHint", "")
            beginner_tip = raw_slot.get("beginnerTip", "")
            spec_node_id = raw_slot.get("specNodeId", slot_id)
            write_scope = raw_slot.get("writeScope", "")
            target_size = raw_slot.get("targetSize")
            if (not isinstance(slot_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", slot_id)
                    or slot_id in slot_ids or not isinstance(label, str) or not 1 <= len(label) <= 80
                    or not isinstance(description, str) or len(description) > 240
                    or not isinstance(usage_hint, str) or len(usage_hint) > 240
                    or not isinstance(beginner_tip, str) or len(beginner_tip) > 240
                    or not isinstance(spec_node_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", spec_node_id)
                    or not isinstance(write_scope, str) or len(write_scope) > 300):
                raise BridgeError("invalid_arguments", "Slots need unique id, label, optional guidance, and a valid Spec node id")
            if target_size is not None:
                if (not isinstance(target_size, list) or len(target_size) != 2
                        or any(type(value) is not int or not 16 <= value <= 4096 for value in target_size)):
                    raise BridgeError("invalid_arguments", "targetSize must be [width, height] with integer values from 16 to 4096")
            if measured_nodes is not None:
                if spec_node_id in mapped_ids:
                    raise BridgeError("ambiguous_mapping", "Each slot must map to a different Spec node")
                if spec_node_id not in bound_nodes or bound_nodes[spec_node_id].get("type") not in {"Panel", "Button", "Toggle", "Slider"}:
                    raise BridgeError("invalid_mapping", f"Spec image node '{spec_node_id}' was not found")
                entry = measured_nodes.get(spec_node_id)
                if entry is None:
                    raise BridgeError("invalid_response", f"Unity did not measure Spec node '{spec_node_id}'")
                target_size = entry["targetSize"]
                if any(value <= 0 or value > 4096 for value in target_size):
                    raise BridgeError("invalid_arguments", f"Spec node '{spec_node_id}' has an unsupported preview size {target_size}")
                size_source = "unity_layout"
                mapped_ids.add(spec_node_id)
            else:
                size_source = "manual" if target_size is not None else "role_default"
            slot_ids.add(slot_id)
            identities = raw_slot.get("candidates")
            if not isinstance(identities, list) or not 1 <= len(identities) <= 12:
                raise BridgeError("invalid_arguments", "Each usage slot must contain 1..12 exact candidate identities")
            candidates: list[dict[str, Any]] = []
            seen: set[tuple[Any, Any, Any]] = set()
            for identity in identities:
                if not isinstance(identity, dict):
                    raise BridgeError("invalid_arguments", "Candidate identities must be objects with path, guid, and localFileId")
                key = (identity.get("path"), identity.get("guid"), identity.get("localFileId"))
                if key in seen or key not in lookup:
                    raise BridgeError("candidate_not_in_catalog", "A candidate is duplicated or absent from the current complete Unity catalog", {"identity": list(key)})
                seen.add(key)
                sprite = lookup[key]
                candidate, preview_size = self._verified_candidate(sprite, config.unity_project_root)
                candidates.append(candidate)
                total_preview_bytes += preview_size
                total_candidates += 1
                if total_candidates > 30 or total_preview_bytes > 24 * 1024 * 1024:
                    raise BridgeError("selection_too_large", "Selection page is limited to 30 candidates and 24 MiB of preview images")
            slots.append(enrich_selection_slot({
                "id": slot_id,
                "label": label,
                "description": description,
                "usageHint": usage_hint,
                "beginnerTip": beginner_tip,
                "specNodeId": spec_node_id,
                "writeScope": write_scope,
                "targetSize": target_size,
                "targetSizeSource": size_source,
                "referencePixelsPerUnit": measured_nodes[spec_node_id]["referencePixelsPerUnit"] if measured_nodes else 100,
                "pixelsPerUnitMultiplier": measured_nodes[spec_node_id]["pixelsPerUnitMultiplier"] if measured_nodes else 1,
                "layoutFingerprint": layout["layoutFingerprint"] if layout else None,
                "candidates": candidates,
            }))
        return {"ok": True, "result": self._sprite_selection_sessions.create(
            slots, catalog_fingerprint, source_path, str(config.unity_project_root.resolve()),
            spec_fingerprint(bound_spec) if bound_spec is not None else None, layout["layoutFingerprint"] if layout else None)}

    def get_sprite_selection(self, session_id: str, wait_seconds: int = 120) -> dict[str, Any]:
        if type(wait_seconds) is not int or not 0 <= wait_seconds <= 300:
            raise BridgeError("invalid_arguments", "wait_seconds must be an integer from 0 to 300")
        self._validate_selection_session_id(session_id)
        session = self._sprite_selection_sessions.wait_for_submission(session_id, wait_seconds)
        if session is None:
            raise BridgeError("session_expired", "Sprite selection session does not exist or has expired")
        if session.submitted is None:
            return {"ok": True, "result": {"status": "waiting_for_user", "expiresInSeconds": self._session_seconds_remaining(session.created_at)}}
        config = self._config_loader()
        if config.unity_project_root is None or str(config.unity_project_root.resolve()) != session.project_root:
            raise BridgeError("project_mismatch", "Candidate session belongs to a different Unity project")
        current = self._read_complete_catalog(session.source_path, session.catalog_fingerprint, config)
        identity_set = {(sprite.get("path"), sprite.get("guid"), sprite.get("localFileId")) for sprite in current}
        for selection in session.submitted:
            identity = (selection["sourcePath"], selection["sourceGuid"], selection["spriteLocalFileId"])
            if identity not in identity_set:
                raise BridgeError("catalog_stale", "The submitted Sprite no longer matches the Unity catalog. Re-query and create a new selection session.", {"slot": selection["slot"]})
        return {"ok": True, "result": {
            "status": "submitted",
            "catalogFingerprint": session.catalog_fingerprint,
            "selections": session.submitted,
            "baseSpecFingerprint": session.base_spec_fingerprint,
            "layoutFingerprint": session.layout_fingerprint,
            "mergeAvailable": session.base_spec_fingerprint is not None,
            "nextStep": "Merge the selected styles into the displayed Spec, run Validate and Prepare, show the complete plan, and wait for explicit developer confirmation before Generate. This selection is not generation approval.",
        }}

    def cancel_sprite_selection(self, session_id: str) -> dict[str, Any]:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", session_id):
            raise BridgeError("invalid_arguments", "session_id is invalid")
        return {"ok": True, "result": {"cancelled": self._sprite_selection_sessions.cancel(session_id)}}

    def measure_composition_layout(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        parse_spec(spec_json)
        return {"ok": True, "result": self._measure_layout(spec_json, self._config_loader())}

    def _measure_layout(self, spec_json: str, config: BridgeConfig) -> dict[str, Any]:
        response = self._execute("ui_agent_measure_composition_layout",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionGenerator.MeasureLayoutJson("
            f"{_csharp_data(spec_json)}));", config=config, max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)
        report = response.get("result")
        if response.get("ok") is not True or not isinstance(report, dict) or report.get("status") != "measured":
            raise BridgeError("layout_unavailable", "Unity could not measure this Spec; resolve reported errors first", {"response": response})
        layout = report.get("layout")
        if (not isinstance(layout, dict) or layout.get("basis") != "unity_ugui_reference_resolution"
                or not isinstance(layout.get("layoutFingerprint"), str)
                or not _FINGERPRINT.fullmatch(layout["layoutFingerprint"])
                or not isinstance(layout.get("nodes"), list) or not 1 <= len(layout["nodes"]) <= 256):
            raise BridgeError("invalid_response", "Unity returned an incomplete layout measurement")
        seen = set()
        for entry in layout["nodes"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("nodeId"), str) or entry["nodeId"] in seen:
                raise BridgeError("invalid_response", "Unity layout contains invalid or duplicate nodes")
            seen.add(entry["nodeId"])
            size = entry.get("targetSize")
            if (not isinstance(size, list) or len(size) != 2
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in size)
                    or any(type(entry.get(key)) not in (int, float) or not math.isfinite(entry[key]) or entry[key] <= 0
                           for key in ("referencePixelsPerUnit", "pixelsPerUnitMultiplier"))):
                raise BridgeError("invalid_response", "Unity layout contains invalid geometry/PPU values")
        return layout

    def merge_sprite_selection(self, session_id: str, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        spec = parse_spec(spec_json)
        session = self._get_selection_session(session_id)
        if session.base_spec_fingerprint is None:
            raise BridgeError("spec_binding_required", "Create a new candidate session with spec_json before using reliable merge")
        if spec_fingerprint(spec) != session.base_spec_fingerprint:
            raise BridgeError("spec_stale", "Spec changed after the candidate page was created; create a new session")
        if session.submitted is None:
            raise BridgeError("selection_required", "Candidate choices have not been submitted")
        # Reuse the fresh catalog/project check; arbitrary caller-provided selection JSON is never accepted.
        self.get_sprite_selection(session_id, wait_seconds=0)
        fresh_layout = self._measure_layout(spec_json, self._config_loader())
        if fresh_layout["layoutFingerprint"] != session.layout_fingerprint:
            raise BridgeError("layout_stale", "Unity layout dependencies changed since selection; create a new session")
        result = merge_selection(spec, session.base_spec_fingerprint, session.submitted)
        merged_json = json.dumps(result["spec"], ensure_ascii=False, separators=(",", ":"))
        _validate_spec(merged_json, MAX_COMPOSITION_SPEC_LENGTH)
        validation = self.validate_composition(merged_json)
        report = validation.get("result")
        if validation.get("ok") is not True or not isinstance(report, dict) or report.get("valid") is not True:
            raise BridgeError("merged_spec_invalid", "Merged Spec did not pass Unity Validate", {"validation": validation})
        result["status"] = "merged_requires_prepare"
        result["validation"] = report
        result["nextStep"] = "Show field changes, run Prepare on the returned Spec, display the entire plan and obtain developer confirmation. No files or Prefabs have been written."
        return {"ok": True, "result": result}

    def _read_complete_catalog(self, source_path: str, fingerprint: str, config: BridgeConfig) -> list[dict[str, Any]]:
        sprites: list[dict[str, Any]] = []
        offset = 0
        for _ in range(100):
            report = self._execute("ui_agent_find_sprites", "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionSpriteCatalog.QueryJson("
                f"{_csharp_data(source_path)}, \"\", {offset}, 100, {_csharp_data(fingerprint)}));", config=config,
                max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH).get("result")
            if not isinstance(report, dict) or report.get("complete") is not True or report.get("status") != "complete" or report.get("catalogFingerprint") != fingerprint or not isinstance(report.get("sprites"), list):
                raise BridgeError("catalog_stale", "Unity could not return a complete catalog with the supplied fingerprint. Re-query candidates.")
            sprites.extend(report["sprites"])
            if report.get("hasMore") is not True:
                return sprites
            next_offset = report.get("nextOffset")
            if type(next_offset) is not int or next_offset <= offset or next_offset > 10_000:
                break
            offset = next_offset
        raise BridgeError("catalog_incomplete", "Unity Sprite catalog exceeded the bounded session scan")

    @staticmethod
    def _verified_candidate(sprite: dict[str, Any], project_root: Path) -> tuple[dict[str, Any], int]:
        if not all(isinstance(sprite.get(key), str) and sprite[key] for key in ("path", "guid", "name", "localFileId")):
            raise BridgeError("invalid_response", "Unity catalog returned a Sprite without a complete identity")
        rect, border = sprite.get("rect"), sprite.get("border")
        reference, preview = sprite.get("specReference"), sprite.get("preview")
        if not isinstance(rect, list) or len(rect) != 4 or not isinstance(border, list) or len(border) != 4 or not isinstance(reference, dict) or not isinstance(preview, dict):
            raise BridgeError("invalid_response", "Unity catalog returned incomplete Sprite geometry")
        integer_border = all(type(value) in (int, float) and math.isfinite(value)
                             and 0 <= value <= 4096 and int(value) == value for value in border)
        if integer_border:
            # Unity serializes Vector4 as floats; the v2 Spec requires integer Border pixels.
            border = [int(value) for value in border]
        preview_path = preview.get("texturePath")
        preview_rect = preview.get("rect")
        texture_width, texture_height = preview.get("textureWidth"), preview.get("textureHeight")
        if (not isinstance(preview_path, str) or not isinstance(preview_rect, list) or len(preview_rect) != 4
                or type(texture_width) is not int or type(texture_height) is not int
                or not 0 < texture_width <= 32768 or not 0 < texture_height <= 32768):
            raise BridgeError("invalid_response", "Unity catalog did not identify the preview texture")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in preview_rect):
            raise BridgeError("invalid_response", "Unity catalog returned an invalid Sprite preview rect")
        px, py, pw, ph = preview_rect
        if px < 0 or py < 0 or pw <= 0 or ph <= 0 or px + pw > texture_width or py + ph > texture_height or pw * ph > 16_777_216:
            raise BridgeError("invalid_response", "Unity Sprite preview rect is outside the texture or too large")
        _validate_assets_path(preview_path)
        assets_root = (project_root / "Assets").resolve(strict=True)
        image_path = (project_root / preview_path).resolve(strict=True)
        try:
            image_path.relative_to(assets_root)
        except ValueError as exc:
            raise BridgeError("invalid_arguments", "Sprite preview must resolve inside the configured project's Assets folder") from exc
        if not image_path.is_file() or image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise BridgeError("preview_unavailable", "Sprite preview is not a supported local image", {"path": preview_path})
        size = image_path.stat().st_size
        if size <= 0 or size > 6 * 1024 * 1024:
            raise BridgeError("preview_too_large", "Each Sprite source preview must be no larger than 6 MiB", {"path": preview_path, "bytes": size})
        image = image_path.read_bytes()
        mime = mimetypes.guess_type(image_path.name)[0]
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise BridgeError("preview_unavailable", "Sprite preview MIME type is not supported")
        usable_types = ["simple"]
        if sprite.get("slicedBorderUsable") is True and integer_border:
            if type(sprite.get("pixelsPerUnit")) not in (int, float) or not math.isfinite(sprite["pixelsPerUnit"]) or sprite["pixelsPerUnit"] <= 0:
                raise BridgeError("invalid_response", "Sliced preview requires a fresh Unity catalog with Sprite pixelsPerUnit")
            usable_types.append("sliced")
        return ({
            "path": sprite["path"], "guid": sprite["guid"], "name": sprite["name"],
            "localFileId": sprite["localFileId"], "rect": rect, "border": border,
            "previewRect": preview_rect, "textureWidth": texture_width, "textureHeight": texture_height,
            "previewOrigin": preview.get("origin", "bottom_left"),
            "specReference": reference, "imageTypes": usable_types,
            "pixelsPerUnit": sprite.get("pixelsPerUnit"),
            "padding": sprite.get("padding", [0, 0, 0, 0]),
            "previewBytes": image, "previewMime": mime,
        }, size)

    def _get_selection_session(self, session_id: str):
        self._validate_selection_session_id(session_id)
        session, exists = self._sprite_selection_sessions.get(session_id)
        if not exists or session is None:
            raise BridgeError("session_expired", "Sprite selection session does not exist or has expired")
        return session

    @staticmethod
    def _validate_selection_session_id(session_id: str) -> None:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", session_id):
            raise BridgeError("invalid_arguments", "session_id is invalid")

    @staticmethod
    def _session_seconds_remaining(created_at: float) -> int:
        from .sprite_selection import SESSION_TTL_SECONDS
        return max(0, int(SESSION_TTL_SECONDS - (time.monotonic() - created_at)))

    def diagnose_composition(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        parse_spec(spec_json)
        return self._execute("ui_agent_diagnose_composition",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionDiagnostics.DiagnoseJson("
            f"{_csharp_data(spec_json)}));", max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)

    def revise_composition(self, spec_json: str, diagnosis_fingerprint: str,
                           issue_ids_json: str, output_prefab_path: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        spec = parse_spec(spec_json)
        if not isinstance(diagnosis_fingerprint, str) or not _FINGERPRINT.fullmatch(diagnosis_fingerprint):
            raise BridgeError("invalid_arguments", "diagnosis_fingerprint must be a SHA-256 hex string")
        _validate_assets_path(output_prefab_path)
        response = self.diagnose_composition(spec_json)
        diagnosis = response.get("result")
        if response.get("ok") is not True or not isinstance(diagnosis, dict) or diagnosis.get("complete") is not True:
            raise BridgeError("diagnosis_incomplete", "Fresh saved-Prefab diagnosis failed", {"diagnosis": response})
        if diagnosis.get("diagnosisFingerprint") != diagnosis_fingerprint:
            raise BridgeError("diagnosis_stale", "Spec, project, saved Prefab or its dependencies changed; inspect a new diagnosis")
        result = revise_spec(spec, diagnosis, issue_ids_json, output_prefab_path)
        revised_json = json.dumps(result["spec"], ensure_ascii=False, separators=(",", ":"))
        _validate_spec(revised_json, MAX_COMPOSITION_SPEC_LENGTH)
        validation = self.validate_composition(revised_json)
        if validation.get("ok") is not True or validation.get("result", {}).get("valid") is not True:
            raise BridgeError("revised_spec_invalid", "Revision did not pass Unity Validate", {"validation": validation})
        result["validation"] = validation["result"]
        return {"ok": True, "result": result}

    def validate_composition(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        return self._execute("ui_agent_validate_composition",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionSpecValidator.ValidateJson("
            f"{_csharp_data(spec_json)}));", max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)

    def prepare_composition(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        config = self._config_loader()
        result = self._execute("ui_agent_prepare_composition",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionGenerator.PrepareJson("
            f"{_csharp_data(spec_json)}));", config=config, max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)
        report = result.get("result")
        plan = report.get("plan") if isinstance(report, dict) else None
        fingerprint = plan.get("planFingerprint") if isinstance(plan, dict) else None
        if result.get("ok") is True and isinstance(fingerprint, str) and _FINGERPRINT.fullmatch(fingerprint) and report.get("status") == "ready_for_confirmation":
            with self._lock:
                self._prune_plans()
                self._composition_prepared[fingerprint] = (time.monotonic(), spec_json, str(config.unity_project_root))
                self._composition_prepared.move_to_end(fingerprint)
                while len(self._composition_prepared) > 32:
                    self._composition_prepared.popitem(last=False)
        return result

    def generate_composition(self, spec_json: str, plan_fingerprint: str, user_confirmed: bool) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        if not isinstance(plan_fingerprint, str) or not _FINGERPRINT.fullmatch(plan_fingerprint):
            raise BridgeError("invalid_arguments", "plan_fingerprint must be a 64-character SHA-256 hex string")
        if type(user_confirmed) is not bool:
            raise BridgeError("invalid_arguments", "user_confirmed must be a boolean")
        if not user_confirmed:
            return _tool_error("confirmation_required", "Generation requires explicit developer confirmation of the displayed plan.")
        config = self._config_loader()
        with self._lock:
            self._prune_plans()
            prepared = self._composition_prepared.get(plan_fingerprint)
            if prepared is None:
                return _tool_error("confirmation_required", "No matching v2 plan in this Bridge session. Prepare and show the plan again.")
            _, prepared_spec, prepared_root = prepared
            if prepared_spec != spec_json or prepared_root != str(config.unity_project_root):
                self._composition_prepared.pop(plan_fingerprint, None)
                return _tool_error("confirmation_required", "Spec or Unity project differs from the prepared v2 plan.")
            # One attempt only, including timeouts/disconnects with an unknown outcome.
            self._composition_prepared.pop(plan_fingerprint, None)
        operation = (
            "var confirmation = new UIAgent.Tools.Editor.UiCompositionGenerator.Confirmation "
            f"{{ userConfirmed = true, planFingerprint = {csharp_string_literal(plan_fingerprint)} }}; "
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionGenerator.GenerateJson("
            f"{_csharp_data(spec_json)}, confirmation));")
        try:
            return self._execute("ui_agent_generate_composition", operation, config=config,
                                 max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)
        except BridgeError as exc:
            if exc.kind == "execution_status_unknown":
                raise BridgeError("execution_status_unknown",
                    "Generation outcome is unknown. Inspect the exact Prefab path and execute_code history; this write will not be replayed.",
                    {"plan_fingerprint": plan_fingerprint, "output_prefab_path": _output_path(spec_json)}) from exc
            raise

    def audit_composition(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json, MAX_COMPOSITION_SPEC_LENGTH)
        return self._execute("ui_agent_audit_composition",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiCompositionAssetAuditor.AuditPrefabJson("
            f"{_csharp_data(spec_json)}));", max_code_length=MAX_TRUSTED_DATA_CODE_LENGTH)

    def validate_spec(self, spec_json: str) -> dict[str, Any]:
        _validate_spec(spec_json)
        return self._execute(
            "ui_agent_validate_spec",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiSpecValidator.ValidateJson("
            f"{_csharp_data(spec_json)}));",
        )

    def prepare_main_menu(self, spec_json: str, font_asset_path: str) -> dict[str, Any]:
        _validate_spec(spec_json)
        _validate_font_path(font_asset_path)
        result = self._execute(
            "ui_agent_prepare_main_menu",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.MainMenuGenerator.PrepareJson("
            f"{_csharp_data(spec_json)}, {_csharp_data(font_asset_path)}));",
        )
        report = result.get("result")
        plan = report.get("plan") if isinstance(report, dict) else None
        fingerprint = plan.get("planFingerprint") if isinstance(plan, dict) else None
        if isinstance(fingerprint, str) and _FINGERPRINT.fullmatch(fingerprint) and report.get("status") == "ready_for_confirmation":
            config = self._config_loader()
            with self._lock:
                self._prune_plans()
                self._prepared[fingerprint] = (time.monotonic(), spec_json, font_asset_path, str(config.unity_project_root))
                self._prepared.move_to_end(fingerprint)
                while len(self._prepared) > 32:
                    self._prepared.popitem(last=False)
        return result

    def generate_main_menu(
        self,
        spec_json: str,
        font_asset_path: str,
        plan_fingerprint: str,
        user_confirmed: bool,
    ) -> dict[str, Any]:
        _validate_spec(spec_json)
        _validate_font_path(font_asset_path)
        if not isinstance(plan_fingerprint, str) or not _FINGERPRINT.fullmatch(plan_fingerprint):
            raise BridgeError("invalid_arguments", "plan_fingerprint must be a 64-character SHA-256 hex string")
        if not isinstance(user_confirmed, bool):
            raise BridgeError("invalid_arguments", "user_confirmed must be a boolean")
        if not user_confirmed:
            return _tool_error("confirmation_required", "Generation requires explicit user confirmation of the displayed plan.")

        config = self._config_loader()
        with self._lock:
            self._prune_plans()
            prepared = self._prepared.get(plan_fingerprint)
            if prepared is None:
                return _tool_error("confirmation_required", "No matching prepared plan exists in this Bridge session. Prepare and show the plan again.")
            _, prepared_spec, prepared_font, prepared_root = prepared
            if prepared_spec != spec_json or prepared_font != font_asset_path or prepared_root != str(config.unity_project_root):
                self._prepared.pop(plan_fingerprint, None)
                return _tool_error("confirmation_required", "The generation inputs or Unity project differ from the prepared plan.")
            # Consume before the write call so an ambiguous timeout cannot be replayed.
            self._prepared.pop(plan_fingerprint, None)

        fingerprint_literal = csharp_string_literal(plan_fingerprint)
        operation = (
            "var confirmation = new UIAgent.Tools.Editor.MainMenuGenerator.Confirmation "
            f"{{ userConfirmed = true, planFingerprint = {fingerprint_literal} }}; "
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.MainMenuGenerator.GenerateJson("
            f"{_csharp_data(spec_json)}, {_csharp_data(font_asset_path)}, confirmation));"
        )
        try:
            return self._execute("ui_agent_generate_main_menu", operation, config=config)
        except BridgeError as exc:
            if exc.kind == "execution_status_unknown":
                raise BridgeError(
                    "execution_status_unknown",
                    "Generation timed out; Unity may have created the Prefab or scene instance. Inspect the exact plan path before taking any further action. The Bridge will not replay this write.",
                    {"plan_fingerprint": plan_fingerprint, "output_prefab_path": _output_path(spec_json)},
                ) from exc
            raise

    def inspect_hierarchy(self, source: Literal["active_scene", "prefab"], asset_path: str | None = None) -> dict[str, Any]:
        if source == "active_scene":
            if asset_path is not None:
                raise BridgeError("invalid_arguments", "asset_path is only valid when source is 'prefab'")
            statement = "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiHierarchyInspector.InspectActiveSceneJson());"
        elif source == "prefab":
            _validate_prefab_path(asset_path)
            statement = "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.UiHierarchyInspector.InspectPrefabJson("
            statement += f"{_csharp_data(asset_path)}));"
        else:
            raise BridgeError("invalid_arguments", "source must be 'active_scene' or 'prefab'")
        return self._execute("ui_agent_inspect_hierarchy", statement)

    def audit_ui(self) -> dict[str, Any]:
        with self._lock:
            pending = self._audit
        if pending is None:
            local = self._execute(
                "ui_agent_audit_ui_local",
                "var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene(); "
                "var roots = scene.GetRootGameObjects(); "
                "var rootIds = new string[roots.Length]; for (int i = 0; i < roots.Length; i++) rootIds[i] = roots[i].GetInstanceID().ToString(); "
                "ctx.ReturnValue = new { scenePath = scene.path, rootIds = rootIds, "
                "report = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.DesktopMenuAuditor.AuditActiveSceneJson()) };",
            )
            local_value = local.get("result")
            if not isinstance(local_value, dict) or not isinstance(local_value.get("report"), dict):
                raise BridgeError("invalid_response", "UI Agent local audit returned an invalid report")
            scene_path = local_value.get("scenePath")
            root_ids = local_value.get("rootIds")
            if not isinstance(scene_path, str) or not isinstance(root_ids, list) or not all(isinstance(item, str) for item in root_ids):
                raise BridgeError("invalid_response", "Unity did not return active scene identity and roots")
            config_json = json.dumps({
                "required_references": [
                    {"component_type": "TMPro.TextMeshProUGUI", "property": "m_fontAsset"},
                    {"component_type": "UnityEngine.UI.Text", "property": "m_FontData.m_Font"},
                    {"component_type": "UnityEngine.UI.Button", "property": "m_TargetGraphic"},
                ],
                "suppressions": [],
            }, separators=(",", ":"))
            with self._open_broker() as broker:
                self._require_tool(broker, "audit_ui")
                started = _parse_funplay_payload(broker.call_tool("audit_ui", {
                    "scope": "scene",
                    "roots": json.dumps(root_ids, separators=(",", ":")),
                    "configuration": config_json,
                    "wait_seconds": 0,
                }))
            pending = {"scene_path": scene_path, "local_report": local_value["report"], "native": started}
            with self._lock:
                self._audit = pending

        native = pending.get("native")
        data = _audit_data(native)
        if not isinstance(data, dict):
            raise BridgeError("invalid_response", "Funplay audit response did not include a data object")
        if data.get("status") != "completed" or data.get("complete") is not True:
            task_id = _task_id(data)
            if not task_id:
                return {"ok": True, "tool": "ui_agent_audit_ui", "status": "incomplete", "report": pending["local_report"], "upstream": native}
            config = self._config_loader()
            with self._open_broker(config) as broker:
                self._require_tool(broker, "get_task")
                task_response = _parse_funplay_payload(broker.call_tool("get_task", {
                    "task_id": task_id, "wait_seconds": 0, "offset": 0, "limit": AUDIT_PAGE_SIZE,
                }))
            task_data = _audit_data(task_response)
            if isinstance(task_data, dict) and task_data.get("scope") == "scene":
                pending["native"] = task_response
                data = task_data
                if data.get("status") != "completed" or data.get("complete") is not True:
                    return {"ok": True, "tool": "ui_agent_audit_ui", "status": "in_progress", "task_id": task_id, "task": _task_state(task_response), "poll": "Call ui_agent_audit_ui again to check completion."}
            else:
                task_state = _task_state(task_response)
                return {"ok": True, "tool": "ui_agent_audit_ui", "status": "in_progress", "task_id": task_id, "task": task_state, "poll": "Call ui_agent_audit_ui again to check completion."}

        complete_native = self._collect_audit_pages(pending, data)
        scene_check = self._execute(
            "ui_agent_audit_ui_scene_check",
            "ctx.ReturnValue = new { scenePath = UnityEngine.SceneManagement.SceneManager.GetActiveScene().path };",
        ).get("result")
        active_scene = scene_check.get("scenePath") if isinstance(scene_check, dict) else None
        if active_scene != pending["scene_path"]:
            with self._lock:
                self._audit = None
            raise BridgeError("audit_scene_changed", "The active scene changed while its audit was running; results were not merged.", {"audited_scene": pending["scene_path"], "active_scene": active_scene})

        local_json = json.dumps(pending["local_report"], ensure_ascii=False, separators=(",", ":"))
        upstream_json = json.dumps(complete_native, ensure_ascii=False, separators=(",", ":"))
        merged = self._execute(
            "ui_agent_audit_ui_merge",
            "ctx.ReturnValue = Newtonsoft.Json.Linq.JToken.Parse(UIAgent.Tools.Editor.DesktopMenuAuditor.MergeFunplayJson("
            f"{_csharp_data(local_json)}, {_csharp_data(upstream_json)}));",
        )
        with self._lock:
            self._audit = None
        return merged

    def _collect_audit_pages(self, pending: dict[str, Any], first_data: dict[str, Any]) -> dict[str, Any]:
        native = pending["native"]
        data = first_data
        if data.get("scope") != "scene" or data.get("status") != "completed" or data.get("complete") is not True:
            raise BridgeError("audit_incomplete", "Funplay UI audit has not completed; call ui_agent_audit_ui again to poll it.", {"task": _task_state(native)})
        findings = data.get("findings")
        total = data.get("total_findings")
        offset = data.get("offset")
        if not isinstance(findings, list) or offset != 0 or not isinstance(total, int) or total < 0:
            raise BridgeError("invalid_response", "Funplay audit page has invalid offset or finding totals")
        aggregate = dict(data)
        all_findings = list(findings)
        next_offset = data.get("next_offset")
        task_id = _task_id(data)
        page_count = 0
        while next_offset is not None:
            page_count += 1
            if page_count > MAX_AUDIT_PAGES or not isinstance(next_offset, int) or next_offset != len(all_findings) or not task_id:
                aggregate.update({"complete": False, "next_offset": next_offset, "findings": all_findings})
                break
            config = self._config_loader()
            with self._open_broker(config) as broker:
                page_response = _parse_funplay_payload(broker.call_tool("get_task", {
                    "task_id": task_id, "wait_seconds": 0, "offset": next_offset, "limit": AUDIT_PAGE_SIZE,
                }))
            page = _audit_data(page_response)
            if not isinstance(page, dict) or page.get("scope") != "scene" or page.get("status") != "completed" or page.get("complete") is not True or page.get("offset") != next_offset or not isinstance(page.get("findings"), list):
                aggregate.update({"complete": False, "next_offset": next_offset, "findings": all_findings})
                break
            all_findings.extend(page["findings"])
            next_offset = page.get("next_offset")
        aggregate["findings"] = all_findings
        aggregate["offset"] = 0
        aggregate["next_offset"] = None if len(all_findings) >= total else next_offset
        aggregate["total_findings"] = total
        aggregate["complete"] = aggregate.get("complete") is True and len(all_findings) == total and aggregate.get("next_offset") is None
        native["data"] = aggregate
        return native

    def _execute(
        self,
        tool_name: str,
        operation: str,
        *,
        config: BridgeConfig | None = None,
        extra_usings: tuple[str, ...] = (),
        max_code_length: int = 65_536,
    ) -> dict[str, Any]:
        config = config or self._config_loader()
        try:
            with self._open_broker(config) as broker:
                command = "\n".join(extra_usings) + "\n" + operation if extra_usings else operation
                envelope = call_guarded_command(config, broker, command, timeout_seconds=config.execute_code_timeout_seconds,
                                                max_code_length=max_code_length)
        except BridgeError as exc:
            if exc.kind == "execute_code_failed":
                raise BridgeError("ui_agent_package_unavailable", "Unity could not compile or invoke the UI Agent Package API.", exc.details) from exc
            raise
        result = envelope.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError as exc:
                raise BridgeError("invalid_response", "UI Agent Package returned malformed JSON") from exc
        if not isinstance(result, dict):
            raise BridgeError("invalid_response", "UI Agent Package returned a non-object result")
        response = {"ok": True, "tool": tool_name, "project": {"name": envelope.get("guard", {}).get("projectName"), "root": envelope.get("guard", {}).get("projectRoot")}, "result": result}
        self._write_audit(config, tool_name, result)
        return response

    def _open_broker(self, config: BridgeConfig | None = None):
        broker = self._broker_factory(config or self._config_loader())
        broker.initialize()
        return broker

    @staticmethod
    def _require_tool(broker: FunplayBroker, name: str) -> None:
        if not any(item.get("name") == name for item in broker.list_tools()):
            raise BridgeError("funplay_tool_unavailable", f"Funplay does not provide the required {name} tool")

    @staticmethod
    def _write_audit(config: BridgeConfig, tool_name: str, result: dict[str, Any]) -> None:
        report = result
        if "result" in result and isinstance(result["result"], dict):
            report = result["result"]
        plan = report.get("plan") if isinstance(report, dict) else None
        AuditLogger(config.source.parent).write(
            "ui_agent_tool",
            project_name=config.project_name,
            tool_name=tool_name,
            status=report.get("status") if isinstance(report, dict) else None,
            plan_fingerprint=plan.get("planFingerprint") if isinstance(plan, dict) else None,
        )

    def _prune_plans(self) -> None:
        now = time.monotonic()
        for fingerprint, (created, *_rest) in list(self._prepared.items()):
            if now - created > 1800:
                self._prepared.pop(fingerprint, None)
        for fingerprint, (created, *_rest) in list(self._composition_prepared.items()):
            if now - created > 1800:
                self._composition_prepared.pop(fingerprint, None)


def _validate_spec(spec_json: str, max_length: int = MAX_SPEC_LENGTH) -> None:
    if not isinstance(spec_json, str):
        raise BridgeError("invalid_arguments", "spec_json must be a non-empty string")
    try:
        utf16_length = len(spec_json.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise BridgeError("invalid_arguments", "spec_json contains invalid Unicode") from exc
    if utf16_length > max_length:
        raise BridgeError("invalid_arguments", f"spec_json exceeds {max_length} UTF-16 units")
    if not spec_json.strip():
        raise BridgeError("invalid_arguments", "spec_json must be a non-empty string")
    try:
        json.loads(spec_json)
    except json.JSONDecodeError as exc:
        raise BridgeError("invalid_arguments", "spec_json must contain valid JSON") from exc


def _validate_assets_path(path: str) -> None:
    if (not isinstance(path, str) or not 1 <= len(path) <= MAX_FONT_PATH_LENGTH
            or (path != "Assets" and not path.startswith("Assets/"))
            or any(c in path for c in '\\:*?"<>|') or any(ord(c) < 32 for c in path)
            or any(p in {"", ".", ".."} or p.endswith((" ", ".")) for p in path.split("/"))):
        raise BridgeError("invalid_arguments", "source_path must be a normalized Assets-relative file or folder")


def _validate_font_path(font_asset_path: str) -> None:
    if not isinstance(font_asset_path, str) or not font_asset_path or len(font_asset_path) > MAX_FONT_PATH_LENGTH:
        raise BridgeError("invalid_arguments", f"font_asset_path must be 1..{MAX_FONT_PATH_LENGTH} characters")


def _validate_prefab_path(asset_path: str | None) -> None:
    if not isinstance(asset_path, str) or len(asset_path) > MAX_FONT_PATH_LENGTH or not asset_path.startswith("Assets/") or not asset_path.lower().endswith(".prefab"):
        raise BridgeError("invalid_arguments", "asset_path must be a normalized Assets-relative .prefab path")
    parts = asset_path.split("/")
    if "\\" in asset_path or any(part in {"", ".", ".."} for part in parts):
        raise BridgeError("invalid_arguments", "asset_path must not contain path traversal or empty segments")


def _output_path(spec_json: str) -> str | None:
    try:
        return json.loads(spec_json).get("outputPrefabPath")
    except (AttributeError, json.JSONDecodeError):
        return None


def _tool_error(kind: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"kind": kind, "message": message, "details": {}}}


def _csharp_data(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"System.Text.Encoding.UTF8.GetString(Convert.FromBase64String({csharp_string_literal(encoded)}))"


def _parse_funplay_payload(response: dict[str, Any]) -> dict[str, Any]:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = response.get("content")
    if isinstance(content, list):
        blocks = [item.get("text") for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
        for block in blocks:
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    if isinstance(response, dict):
        return response
    raise BridgeError("invalid_response", "Funplay returned an invalid audit response")


def _audit_data(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    if isinstance(data, dict) and isinstance(data.get("scope"), str) and "findings" in data:
        return data
    if isinstance(data, dict):
        nested = data.get("result")
        if isinstance(nested, dict):
            found = _audit_data(nested)
            if found:
                return found
        nested = data.get("original_result")
        if isinstance(nested, dict):
            found = _audit_data(nested)
            if found:
                return found
        if isinstance(data.get("scope"), str) and ("task" in data or "status" in data):
            return data
    if isinstance(value.get("scope"), str) and "findings" in value:
        return value
    return None


def _task_id(data: dict[str, Any]) -> str | None:
    task = data.get("task")
    if isinstance(task, dict) and isinstance(task.get("task_id"), str):
        return task["task_id"]
    return None


def _task_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    task = data.get("task") if isinstance(data, dict) else value.get("task")
    return {key: task.get(key) for key in ("task_id", "status", "phase", "revision", "poll_after_ms", "wait_reason") if key in task} if isinstance(task, dict) else None


def register_ui_agent_tools(server: Any, service: UiAgentTools) -> None:
    @server.tool(name="ui_agent_diagnose_composition", description="Read-only saved v2 Prefab diagnosis: verifies the original Spec asset contract, measures native layout/text in an isolated reference-resolution copy, locates outside-canvas rectangles and Simple Sprite stretch risks with node IDs and evidence. Returns bounded revision proposals and a dependency-bound fingerprint. Not runtime/input/aesthetic approval.")
    def ui_agent_diagnose_composition(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.diagnose_composition, spec_json)

    @server.tool(name="ui_agent_revise_composition", description="Apply selected diagnostic proposals to a returned NEW Spec only. Re-diagnoses Unity and rejects stale evidence; only supported position/imageType/Border proposals, new output path and Unity Validate. No writes, no existing Prefab edits, no automatic generation. Prepare, displayed plan and developer confirmation remain required.")
    def ui_agent_revise_composition(spec_json: str, diagnosis_fingerprint: str, issue_ids_json: str,
                                    output_prefab_path: str) -> dict[str, Any]:
        return _safe_call(service.revise_composition, spec_json, diagnosis_fingerprint, issue_ids_json, output_prefab_path)

    @server.tool(name="ui_agent_measure_composition_layout", description="Read-only Unity uGUI layout at Spec reference resolution, using the same generator and native LayoutGroups as Prepare. Returns measured node sizes and Canvas PPU. Does not require an unused output path, create assets, or authorize generation.")
    def ui_agent_measure_composition_layout(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.measure_composition_layout, spec_json)

    @server.tool(name="ui_agent_merge_sprite_selection", description="Merge a submitted Spec-bound candidate session into its unchanged v2 Spec. Rechecks project, fresh Sprite catalog and layout dependencies; changes only Sprite reference/imageType/Border fields, preserves colors and layout. Returns new Spec, field diff and Validate result; no file writes. Prepare and developer confirmation are still required before generation.")
    def ui_agent_merge_sprite_selection(session_id: str, spec_json: str) -> dict[str, Any]:
        return _safe_call(service.merge_sprite_selection, session_id, spec_json)

    @server.tool(name="ui_agent_create_sprite_selection", description="Create a short-lived local browser page for choosing among exact Sprite candidates. Rechecks a complete Unity catalog and serves only validated images from this project's Assets over loopback. Optionally pass a v2 spec_json so target previews use exact Spec node sizes.")
    def ui_agent_create_sprite_selection(source_path: str, catalog_fingerprint: str, slots_json: str,
                                         spec_json: str = "") -> dict[str, Any]:
        # FastMCP pre-parses JSON strings for union annotations; keep JSON data a plain string.
        return _safe_call(service.create_sprite_selection_session, source_path, catalog_fingerprint, slots_json, spec_json or None)

    @server.tool(name="ui_agent_get_sprite_selection", description="Wait up to 300 seconds (default 120) for browser choices, then rechecks the Unity catalog fingerprint and exact Sprite identities. Does not edit Spec or generate UI.")
    def ui_agent_get_sprite_selection(session_id: str, wait_seconds: int = 120) -> dict[str, Any]:
        return _safe_call(service.get_sprite_selection, session_id, wait_seconds)

    @server.tool(name="ui_agent_cancel_sprite_selection", description="Cancel a local Sprite selection session and discard its pending browser choices.")
    def ui_agent_cancel_sprite_selection(session_id: str) -> dict[str, Any]:
        return _safe_call(service.cancel_sprite_selection, session_id)

    @server.tool(name="ui_agent_audit_sprite_imports", description="Read-only bounded audit of imported UI Sprite readiness in an Assets file/folder. Reports texture type, Single/Multiple mode, exact slice identity, Rect/Border and separate Simple/Sliced usability; identifies sources requiring manual action. Never imports, slices, edits or reimports assets.")
    def ui_agent_audit_sprite_imports(source_path: str) -> dict[str, Any]:
        return _safe_call(service.audit_sprite_imports, source_path)

    @server.tool(name="ui_agent_find_sprites", description="Read-only v2 Sprite catalog for an Assets file/folder. Returns precise identities, Rect/Border, source preview coordinates and ready-to-use Spec references. IDs are strings. No imports or slicing. Follow nextOffset with catalogFingerprint; incomplete is not absence.")
    def ui_agent_find_sprites(source_path: str, name_contains: str = "", offset: int = 0, limit: int = 50,
                              catalog_fingerprint: str | None = None) -> dict[str, Any]:
        return _safe_call(service.find_sprites, source_path, name_contains, offset, limit, catalog_fingerprint)

    @server.tool(name="ui_agent_validate_composition", description="Read-only v2 Panel/Text/Button/Toggle Spec validation (up to 65536 UTF-16 units). Toggle is a constrained native uGUI control with declared initial state and label/indicator Text children; it does not bind application settings or callbacks. Includes Multiple Sprite selector syntax; project resource checks require prepare. Does not create UI.")
    def ui_agent_validate_composition(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.validate_composition, spec_json)

    @server.tool(name="ui_agent_prepare_composition", description="Read-only v2 composition preflight. Returns full plan, spriteReferences, resources and planFingerprint. Show the entire plan and obtain developer confirmation before generate. Does not modify/save the scene.")
    def ui_agent_prepare_composition(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.prepare_composition, spec_json)

    @server.tool(name="ui_agent_generate_composition", description="Create only a NEW v2 composition Prefab from this session's displayed, developer-confirmed plan. No overwrite, scene instance or scene save. user_confirmed and fingerprint are workflow inputs, not identity proof. Consumes plan before one write attempt; never replay an unknown outcome.")
    def ui_agent_generate_composition(spec_json: str, plan_fingerprint: str, user_confirmed: bool) -> dict[str, Any]:
        return _safe_call(service.generate_composition, spec_json, plan_fingerprint, user_confirmed)

    @server.tool(name="ui_agent_audit_composition", description="Read-only saved v2 Prefab versus original Spec asset-contract audit. Prefab path comes from Spec. Checks Single/Multiple Sprite identity and saved references. Preserves complete/errors/findings; not a visual, scene override, input or merged Funplay audit.")
    def ui_agent_audit_composition(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.audit_composition, spec_json)

    @server.tool(name="ui_agent_validate_spec", description="Validate a UI Agent Spec in the configured Unity project. This is read-only and creates no UI.")
    def ui_agent_validate_spec(spec_json: str) -> dict[str, Any]:
        return _safe_call(service.validate_spec, spec_json)

    @server.tool(name="ui_agent_prepare_main_menu", description="Prepare a read-only main-menu creation plan. Show the complete returned plan and obtain explicit user confirmation before calling ui_agent_generate_main_menu.")
    def ui_agent_prepare_main_menu(spec_json: str, font_asset_path: str) -> dict[str, Any]:
        return _safe_call(service.prepare_main_menu, spec_json, font_asset_path)

    @server.tool(name="ui_agent_generate_main_menu", description="Create the previously prepared main-menu Prefab and scene instance. Call only after showing the full plan and receiving explicit user confirmation. user_confirmed and plan_fingerprint are workflow inputs, not proof of human approval.")
    def ui_agent_generate_main_menu(spec_json: str, font_asset_path: str, plan_fingerprint: str, user_confirmed: bool) -> dict[str, Any]:
        return _safe_call(service.generate_main_menu, spec_json, font_asset_path, plan_fingerprint, user_confirmed)

    @server.tool(name="ui_agent_inspect_hierarchy", description="Read the UI hierarchy in the active scene or an Assets-relative Prefab. Read-only; Prefab audit merging is not supported.")
    def ui_agent_inspect_hierarchy(source: Literal["active_scene", "prefab"], asset_path: str | None = None) -> dict[str, Any]:
        return _safe_call(service.inspect_hierarchy, source, asset_path)

    @server.tool(name="ui_agent_audit_ui", description="Read-only audit of the active scene. Combines UI Agent rules with Funplay audit_ui, collecting asynchronous task results and all finding pages. Call again to poll an in-progress task.")
    def ui_agent_audit_ui() -> dict[str, Any]:
        return _safe_call(service.audit_ui)


def _safe_call(function: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    try:
        return function(*args)
    except BridgeError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except Exception:
        return {"ok": False, "error": {"kind": "internal_error", "message": "UI Agent Bridge operation failed", "details": {}}}
