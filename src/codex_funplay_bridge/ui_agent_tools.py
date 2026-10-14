"""Named, project-scoped MCP tools for the UI Agent Unity package."""

from __future__ import annotations

import json
import re
import threading
import time
import base64
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Literal

from .audit_logging import AuditLogger
from .broker import BridgeError, FunplayBroker
from .config import BridgeConfig
from .ui_agent_runtime import call_guarded_command, csharp_string_literal

MAX_SPEC_LENGTH = 16_384
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
        self._audit: dict[str, Any] | None = None

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
    ) -> dict[str, Any]:
        config = config or self._config_loader()
        try:
            with self._open_broker(config) as broker:
                command = "\n".join(extra_usings) + "\n" + operation if extra_usings else operation
                envelope = call_guarded_command(config, broker, command, timeout_seconds=config.execute_code_timeout_seconds)
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


def _validate_spec(spec_json: str) -> None:
    if not isinstance(spec_json, str):
        raise BridgeError("invalid_arguments", "spec_json must be a non-empty string")
    try:
        utf16_length = len(spec_json.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise BridgeError("invalid_arguments", "spec_json contains invalid Unicode") from exc
    if utf16_length > MAX_SPEC_LENGTH:
        raise BridgeError("invalid_arguments", f"spec_json exceeds {MAX_SPEC_LENGTH} UTF-16 units")
    if not spec_json.strip():
        raise BridgeError("invalid_arguments", "spec_json must be a non-empty string")
    try:
        json.loads(spec_json)
    except json.JSONDecodeError as exc:
        raise BridgeError("invalid_arguments", "spec_json must contain valid JSON") from exc


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
