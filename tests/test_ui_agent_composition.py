from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import pytest

from codex_funplay_bridge.broker import BridgeError
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.ui_agent_tools import UiAgentTools, register_ui_agent_tools


@pytest.fixture
def service(tmp_path: Path) -> UiAgentTools:
    return UiAgentTools(lambda: BridgeConfig("Demo", "http://127.0.0.1:21898/", 10, tmp_path / "bridge.toml", tmp_path))


def ready(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "result": {"status": "ready_for_confirmation", "plan": {"planFingerprint": "a" * 64}}}


def test_v2_uses_package_apis_and_preserves_exact_spec_data(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def execute(name: str, code: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((name, code, kwargs))
        return ready()
    monkeypatch.setattr(service, "_execute", execute)
    spec = json.dumps({"text": '中文"; throw new Exception(); //', "spriteLocalFileId": "-6054090792327852210"}, ensure_ascii=False)
    service.validate_composition(spec)
    service.prepare_composition(spec)
    service.generate_composition(spec, "a" * 64, True)
    service.audit_composition(spec)
    for call, api in zip(calls, ["UiCompositionSpecValidator.ValidateJson", "UiCompositionGenerator.PrepareJson",
                                 "UiCompositionGenerator.GenerateJson", "UiCompositionAssetAuditor.AuditPrefabJson"]):
        assert api in call[1]
        assert spec not in call[1]
        assert base64.b64encode(spec.encode()).decode() in call[1]
        assert call[2]["max_code_length"] == 280_000


@pytest.mark.parametrize("path", ["../Assets", "Assets/../x", "Assets//x", "Assets/a/", "Packages/a", "C:/a", "Assets/a\\x", "Assets/a:foo", "Assets/a\n", "Assets/a."])
def test_catalog_rejects_bad_paths_before_unity(service: UiAgentTools, path: str) -> None:
    with pytest.raises(BridgeError) as error:
        service.find_sprites(path)
    assert error.value.kind == "invalid_arguments"


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": True}, {"limit": True},
                                   {"offset": 1}, {"catalog_fingerprint": "bad"}, {"name_contains": "a" * 65}])
def test_catalog_rejects_invalid_paging(service: UiAgentTools, kwargs: dict[str, Any]) -> None:
    with pytest.raises(BridgeError):
        service.find_sprites("Assets/Art", **kwargs)


def test_catalog_preserves_id_strings_and_incomplete_status(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    report = {"complete": False, "sprites": [{"localFileId": "-6054090792327852210"}], "errors": [{"code": "SCAN_LIMIT"}]}
    monkeypatch.setattr(service, "_execute", lambda *_args, **_kwargs: {"ok": True, "result": report})
    result = service.find_sprites("Assets/Art", offset=50, catalog_fingerprint="a" * 64)
    assert result["result"] is report
    assert isinstance(result["result"]["sprites"][0]["localFileId"], str)


def test_sprite_import_audit_calls_read_only_package_api(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(service, "_execute", lambda name, code, **kwargs: calls.append((name, code, kwargs)) or {"ok": True})
    service.audit_sprite_imports("Assets/Art")
    assert len(calls) == 1
    assert calls[0][0] == "ui_agent_audit_sprite_imports"
    assert "UiCompositionSpriteImportAuditor.AuditJson" in calls[0][1]


@pytest.mark.parametrize("confirmed", [False, 1, "true"])
def test_generation_requires_boolean_confirmation(service: UiAgentTools, confirmed: Any) -> None:
    if confirmed is False:
        assert service.generate_composition("{}", "a" * 64, confirmed)["error"]["kind"] == "confirmation_required"
    else:
        with pytest.raises(BridgeError): service.generate_composition("{}", "a" * 64, confirmed)


def test_generation_is_bound_to_exact_spec_and_session(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_execute", ready)
    service.prepare_composition("{}")
    assert service.generate_composition("{ }", "a" * 64, True)["ok"] is False
    assert service.generate_composition("{}", "a" * 64, True)["ok"] is False
    service.prepare_main_menu("{}", "Assets/font.asset")
    assert service.generate_composition("{}", "a" * 64, True)["ok"] is False


def test_generation_cannot_change_projects(service: UiAgentTools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_execute", ready)
    service.prepare_composition("{}")
    monkeypatch.setattr(service, "_config_loader", lambda: BridgeConfig("Other", "http://127.0.0.1:21898/", 10, tmp_path / "other.toml", tmp_path / "Other"))
    assert service.generate_composition("{}", "a" * 64, True)["ok"] is False


def test_plan_is_consumed_even_if_write_outcome_unknown(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = '{"outputPrefabPath":"Assets/AgentDemos/UIAgent/Prefabs/PF_New.prefab"}'
    monkeypatch.setattr(service, "_execute", ready)
    service.prepare_composition(spec)
    def unknown(*_args: Any, **_kwargs: Any) -> None:
        raise BridgeError("execution_status_unknown", "timeout")
    monkeypatch.setattr(service, "_execute", unknown)
    with pytest.raises(BridgeError) as error:
        service.generate_composition(spec, "a" * 64, True)
    assert error.value.details["output_prefab_path"] == json.loads(spec)["outputPrefabPath"]
    assert service.generate_composition(spec, "a" * 64, True)["error"]["kind"] == "confirmation_required"


def test_expired_plans_and_cache_bound(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [10.0]
    monkeypatch.setattr("codex_funplay_bridge.ui_agent_tools.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(service, "_execute", ready)
    service.prepare_composition("{}")
    clock[0] += 1801
    assert service.generate_composition("{}", "a" * 64, True)["ok"] is False
    for i in range(35):
        monkeypatch.setattr(service, "_execute", lambda *_a, _i=i, **_k: {"ok": True, "result": {"status": "ready_for_confirmation", "plan": {"planFingerprint": f"{_i:064x}"}}})
        service.prepare_composition("{}")
    assert len(service._composition_prepared) == 32
    assert "0" * 64 not in service._composition_prepared


def test_v2_transport_size_boundary_and_v1_limit_unchanged(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_execute", ready)
    at_limit = '"' + "汉" * 65534 + '"'
    service.validate_composition(at_limit)
    with pytest.raises(BridgeError, match="65536"):
        service.validate_composition('"' + "🚀" * 32768 + '"')
    with pytest.raises(BridgeError, match="16384"):
        service.validate_spec(at_limit)


def test_registration_exposes_typed_tools_and_reports_errors(service: UiAgentTools) -> None:
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("test")
    register_ui_agent_tools(server, service)
    listed = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in listed}
    assert len(listed) == 18
    assert set(by_name["ui_agent_merge_sprite_selection"].inputSchema["required"]) == {"session_id", "spec_json"}
    assert by_name["ui_agent_measure_composition_layout"].inputSchema["required"] == ["spec_json"]
    assert by_name["ui_agent_generate_composition"].inputSchema["required"] == ["spec_json", "plan_fingerprint", "user_confirmed"]
    assert by_name["ui_agent_find_sprites"].inputSchema["properties"]["limit"]["type"] == "integer"
    assert by_name["ui_agent_create_sprite_selection"].inputSchema["required"] == ["source_path", "catalog_fingerprint", "slots_json"]
    assert by_name["ui_agent_get_sprite_selection"].inputSchema["properties"]["wait_seconds"]["type"] == "integer"
    assert "Toggle" in by_name["ui_agent_validate_composition"].description
    assert "Read-only" in by_name["ui_agent_audit_sprite_imports"].description
    result = asyncio.run(server.call_tool("ui_agent_validate_composition", {"spec_json": "not-json"}))
    # FastMCP returns content + structured data for dict annotations.
    assert result[1]["error"]["kind"] == "invalid_arguments"


def test_mcp_create_selection_keeps_spec_json_as_string(service: UiAgentTools, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp.server.fastmcp import FastMCP
    seen = []
    def create(_source, _fingerprint, _slots, spec_json):
        seen.append(spec_json)
        return {"ok": True, "result": {"bound": spec_json is not None}}
    monkeypatch.setattr(service, "create_sprite_selection_session", create)
    server = FastMCP("test-json-transport")
    register_ui_agent_tools(server, service)
    arguments = {"source_path": "Assets/UI", "catalog_fingerprint": "a"*64, "slots_json": "[]"}
    result = asyncio.run(server.call_tool("ui_agent_create_sprite_selection", {**arguments, "spec_json": '{"schemaVersion":2}'}))
    assert result[1]["ok"] and seen == ['{"schemaVersion":2}']
    asyncio.run(server.call_tool("ui_agent_create_sprite_selection", arguments))
    assert seen[-1] is None
