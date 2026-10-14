from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codex_funplay_bridge.broker import BridgeError
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.ui_agent_tools import UiAgentTools


@pytest.fixture
def config(tmp_path: Path) -> BridgeConfig:
    return BridgeConfig("Demo", "http://127.0.0.1:21898/", 10, tmp_path / "bridge.toml", tmp_path)


def service_for(config: BridgeConfig) -> UiAgentTools:
    return UiAgentTools(lambda: config)


def prepared_result(fingerprint: str = "a" * 64) -> dict[str, Any]:
    return {"ok": True, "tool": "prepare", "result": {"status": "ready_for_confirmation", "plan": {"planFingerprint": fingerprint}}}


def test_spec_validation_is_bounded_and_requires_json(config: BridgeConfig) -> None:
    service = service_for(config)
    with pytest.raises(BridgeError, match="valid JSON"):
        service.validate_spec("not-json")
    with pytest.raises(BridgeError, match="exceeds"):
        service.validate_spec(" " * 16_385)


def test_generate_requires_prepared_plan_and_consumes_before_call(config: BridgeConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    service = service_for(config)
    spec = '{"title":"Demo"}'
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: prepared_result())
    service.prepare_main_menu(spec, "Assets/font.asset")
    calls: list[str] = []

    def execute(_name: str, statement: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(statement)
        return {"ok": True, "result": {"status": "generated"}}

    monkeypatch.setattr(service, "_execute", execute)
    generated = service.generate_main_menu(spec, "Assets/font.asset", "a" * 64, True)
    assert generated["result"]["status"] == "generated"
    assert calls
    replay = service.generate_main_menu(spec, "Assets/font.asset", "a" * 64, True)
    assert replay["error"]["kind"] == "confirmation_required"


def test_generate_timeout_is_not_replayable_and_reports_exact_output(config: BridgeConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    service = service_for(config)
    spec = '{"outputPrefabPath":"Assets/AgentDemos/UIAgent/Prefabs/PF_Test.prefab"}'
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: prepared_result())
    service.prepare_main_menu(spec, "Assets/font.asset")

    def timeout(*_args: Any, **_kwargs: Any) -> None:
        raise BridgeError("execution_status_unknown", "timeout")

    monkeypatch.setattr(service, "_execute", timeout)
    with pytest.raises(BridgeError) as error:
        service.generate_main_menu(spec, "Assets/font.asset", "a" * 64, True)
    assert error.value.kind == "execution_status_unknown"
    assert error.value.details == {
        "plan_fingerprint": "a" * 64,
        "output_prefab_path": "Assets/AgentDemos/UIAgent/Prefabs/PF_Test.prefab",
    }
    replay = service.generate_main_menu(spec, "Assets/font.asset", "a" * 64, True)
    assert replay["error"]["kind"] == "confirmation_required"


@pytest.mark.parametrize("source,path", [("prefab", None), ("prefab", "Assets/../secret.prefab"), ("prefab", "C:/Temp/a.prefab")])
def test_prefab_hierarchy_rejects_unsafe_paths(config: BridgeConfig, source: str, path: str | None) -> None:
    with pytest.raises(BridgeError, match="asset_path"):
        service_for(config).inspect_hierarchy(source, path)  # type: ignore[arg-type]


def test_active_scene_hierarchy_rejects_irrelevant_path(config: BridgeConfig) -> None:
    with pytest.raises(BridgeError) as error:
        service_for(config).inspect_hierarchy("active_scene", "Assets/a.prefab")
    assert error.value.kind == "invalid_arguments"


def test_audit_collects_all_pages_and_preserves_totals(config: BridgeConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    service = service_for(config)
    first = {"success": True, "data": {"scope": "scene", "status": "completed", "complete": True,
        "offset": 0, "total_findings": 2, "findings": [{"rule": "A"}], "next_offset": 1,
        "skipped": [], "task": {"task_id": "ui_audit:abc"}}}
    second = {"success": True, "data": {"scope": "scene", "status": "completed", "complete": True,
        "offset": 1, "total_findings": 2, "findings": [{"rule": "B"}], "next_offset": None,
        "skipped": [], "task": {"task_id": "ui_audit:abc"}}}

    class Broker:
        def initialize(self) -> None: pass
        def list_tools(self) -> list[dict[str, Any]]: return [{"name": "get_task"}]
        def call_tool(self, _name: str, args: dict[str, Any]) -> dict[str, Any]:
            payload = second if args["offset"] == 1 else first
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}
        def __enter__(self) -> "Broker": return self
        def __exit__(self, *_args: Any) -> None: pass

    monkeypatch.setattr(service, "_broker_factory", lambda _config: Broker())
    pending = {"native": first}
    data = first["data"]
    result = service._collect_audit_pages(pending, data)
    collected = result["data"]
    assert collected["findings"] == [{"rule": "A"}, {"rule": "B"}]
    assert collected["next_offset"] is None
    assert collected["complete"] is True


def test_audit_polls_async_task_then_merges_completed_report(config: BridgeConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    service = service_for(config)
    calls: list[str] = []
    local_report = {"status": "local_checks_passed", "sourcePath": "Assets/Scene.unity"}
    completed_data = {"scope": "scene", "status": "completed", "complete": True, "offset": 0,
        "total_findings": 0, "findings": [], "next_offset": None, "skipped": [],
        "task": {"task_id": "ui_audit:abc"}}

    def execute(name: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append(name)
        if name == "ui_agent_audit_ui_local":
            return {"ok": True, "result": {"scenePath": "Assets/Scene.unity", "rootIds": ["1"], "report": local_report}}
        if name == "ui_agent_audit_ui_scene_check":
            return {"ok": True, "result": {"scenePath": "Assets/Scene.unity"}}
        return {"ok": True, "result": {"status": "passed"}}

    monkeypatch.setattr(service, "_execute", execute)

    class Broker:
        def initialize(self) -> None: pass
        def list_tools(self) -> list[dict[str, Any]]: return [{"name": "audit_ui"}, {"name": "get_task"}]
        def call_tool(self, name: str, _args: dict[str, Any]) -> dict[str, Any]:
            if name == "audit_ui":
                payload = {"success": True, "data": {"scope": "scene", "status": "running", "complete": False,
                    "task": {"task_id": "ui_audit:abc", "status": "running"}}}
            else:
                payload = {"success": True, "data": completed_data}
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}
        def __enter__(self) -> "Broker": return self
        def __exit__(self, *_args: Any) -> None: pass

    monkeypatch.setattr(service, "_broker_factory", lambda _config: Broker())
    result = service.audit_ui()
    assert result["result"]["status"] == "passed"
    assert calls == ["ui_agent_audit_ui_local", "ui_agent_audit_ui_scene_check", "ui_agent_audit_ui_merge"]


def test_audit_incomplete_page_is_never_marked_complete(config: BridgeConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    service = service_for(config)
    pending = {"native": {"success": True, "data": {}}}

    class Broker:
        def initialize(self) -> None: pass
        def list_tools(self) -> list[dict[str, Any]]: return [{"name": "get_task"}]
        def call_tool(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": json.dumps({"success": True, "data": {
                "scope": "scene", "status": "completed", "complete": True, "offset": 3,
                "total_findings": 4, "findings": [{"rule": "D"}], "next_offset": None,
            }})}]}
        def __enter__(self) -> "Broker": return self
        def __exit__(self, *_args: Any) -> None: pass

    monkeypatch.setattr(service, "_broker_factory", lambda _config: Broker())
    page_data = {"scope": "scene", "status": "completed", "complete": True, "offset": 0,
        "total_findings": 2, "findings": [{"rule": "A"}], "next_offset": 1,
        "task": {"task_id": "ui_audit:abc"}}
    result = service._collect_audit_pages(pending, page_data)["data"]
    assert result["complete"] is False
