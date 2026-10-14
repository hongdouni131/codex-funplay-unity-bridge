from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Any

import pytest

from codex_funplay_bridge.broker import BridgeError, FunplayBroker
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.ui_agent_runtime import (
    build_context_probe,
    build_guarded_command,
    call_guarded_command,
    call_execute_code,
    csharp_string_literal,
    parse_execute_code_result,
    verify_context_result,
)
from conftest import FakeMcpServer


def test_guard_template_checks_project_and_editor_before_operation(tmp_path: Path) -> None:
    operation = 'ctx.ReturnValue = new { status = "ready" };'
    code = build_guarded_command(tmp_path, operation)

    assert "Application.dataPath" in code
    assert "StringComparison.OrdinalIgnoreCase" in code
    assert code.index('status = "project_mismatch"') < code.index(operation)
    assert code.index('status = "editor_not_ready"') < code.index(operation)
    assert "EditorApplication.isCompiling" in code
    assert "EditorApplication.isUpdating" in code
    assert "EditorApplication.isPlayingOrWillChangePlaymode" in code
    assert "guard = new { status = \"ready\"" in code


def test_csharp_string_literal_escapes_quotes_controls_and_supplementary_unicode() -> None:
    literal = csharp_string_literal('D:\\Unity "Agent"\n攻击 🚀')

    assert literal.startswith('"D:\\\\Unity \\\"Agent\\\"\\n')
    assert "\\U0001f680" in literal
    assert '攻击' in literal


def test_guard_template_encodes_configured_path_as_data(tmp_path: Path) -> None:
    root = tmp_path / 'Project"; ctx.ReturnValue = null;'
    code = build_context_probe(root)
    encoded_root = base64.b64encode(str(root.resolve()).encode("utf-8")).decode("ascii")

    assert encoded_root in code
    assert str(root.resolve()) not in code
    assert "Convert.FromBase64String" in code


def test_guard_builder_rejects_empty_operation(tmp_path: Path) -> None:
    with pytest.raises(BridgeError, match="operation template"):
        build_guarded_command(tmp_path, " ")


def test_guard_builder_rejects_relative_project_root() -> None:
    with pytest.raises(BridgeError) as error:
        build_guarded_command(Path("relative/project"), 'ctx.ReturnValue = new { status = "ready" };')

    assert error.value.kind == "project_identity_unverified"


def test_context_guard_requires_configured_root(tmp_path: Path) -> None:
    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml")

    with pytest.raises(BridgeError) as error:
        verify_context_result(config, {"status": "ready"})

    assert error.value.kind == "project_identity_unverified"


@pytest.mark.parametrize(
    ("result", "kind"),
    [
        ({"status": "project_mismatch", "actualProjectRoot": "D:/Other"}, "project_identity_mismatch"),
        ({"status": "editor_not_ready", "isCompiling": True}, "editor_not_ready"),
        ({"status": "unexpected"}, "invalid_response"),
    ],
)
def test_context_guard_rejects_mismatched_or_unready_editor(tmp_path: Path, result: dict[str, Any], kind: str) -> None:
    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml", tmp_path)

    with pytest.raises(BridgeError) as error:
        verify_context_result(config, result)

    assert error.value.kind == kind


def test_context_guard_checks_ready_path_against_configuration(tmp_path: Path) -> None:
    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml", tmp_path)

    verify_context_result(config, {"status": "ready", "projectRoot": str(tmp_path)})
    with pytest.raises(BridgeError) as error:
        verify_context_result(config, {"status": "ready", "projectRoot": str(tmp_path / "Other")})

    assert error.value.kind == "project_identity_mismatch"


def test_guarded_command_requires_project_identity_before_network_call(fake_server: FakeMcpServer) -> None:
    config = BridgeConfig("Demo", fake_server.url, 2, Path("bridge-project.toml"))
    with FunplayBroker(config) as broker:
        with pytest.raises(BridgeError) as error:
            call_guarded_command(config, broker, 'ctx.ReturnValue = "must not run";')

    assert error.value.kind == "project_identity_unverified"
    assert fake_server.requests == []


def test_guarded_command_executes_only_after_matching_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_funplay_bridge import ui_agent_runtime

    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml", tmp_path)
    monkeypatch.setattr(
        ui_agent_runtime,
        "call_execute_code",
        lambda _broker, _code, **_kwargs: {
            "guard": {"status": "ready", "projectRoot": str(tmp_path)},
            "result": {"status": "ready_for_confirmation"},
        },
    )

    result = call_guarded_command(config, object(), 'ctx.ReturnValue = "package result";')  # type: ignore[arg-type]

    assert result["result"]["status"] == "ready_for_confirmation"


def test_parses_structured_funplay_return_value() -> None:
    result = parse_execute_code_result({
        "content": [{"type": "text", "text": json.dumps({"success": True, "data": {"returnValue": {"status": "ready"}}})}]
    })

    assert result == {"status": "ready"}


def test_rejects_unstructured_or_failed_execute_code_results() -> None:
    with pytest.raises(BridgeError) as malformed:
        parse_execute_code_result({"content": [{"type": "text", "text": "COMPILATION_FAILED"}]})
    assert malformed.value.kind == "execute_code_failed"

    with pytest.raises(BridgeError) as failed:
        parse_execute_code_result({"content": [{"type": "text", "text": json.dumps({"success": False, "error": "compile failed"})}]})
    assert failed.value.kind == "execute_code_failed"


def test_execute_code_requires_safety_schema_and_sends_checks_enabled(fake_server: FakeMcpServer) -> None:
    server = FakeMcpServer("with_execute_code")
    server.start()
    config = BridgeConfig("Demo", server.url, 2, Path("bridge-project.toml"))
    try:
        with FunplayBroker(config) as broker:
            result = call_execute_code(broker, "public class ReadOnlyProbe {}")
    finally:
        server.stop()
    request = next(request for request in server.requests if request["method"] == "tools/call")
    assert request["params"]["name"] == "execute_code"
    assert request["params"]["arguments"]["safety_checks"] is True
    assert result == {"status": "ready"}


def test_execute_code_uses_configured_timeout_by_default(fake_server: FakeMcpServer, monkeypatch: pytest.MonkeyPatch) -> None:
    config = BridgeConfig("Demo", fake_server.url, 10, Path("bridge-project.toml"), execute_code_timeout_seconds=75)
    timeouts: list[float | None] = []
    with FunplayBroker(config) as broker:
        monkeypatch.setattr(broker, "list_tools", lambda: [{"name": "execute_code", "inputSchema": {"type": "object", "properties": {"safety_checks": {"type": "boolean"}}}}])
        monkeypatch.setattr(broker, "call_tool", lambda _name, _args, *, timeout_seconds=None: (timeouts.append(timeout_seconds) or {"content": [{"type": "text", "text": json.dumps({"success": True, "data": {"returnValue": {"ok": True}}})}]}))
        call_execute_code(broker, "public class ReadOnlyProbe {}")
    assert timeouts == [75]


def test_execute_code_timeout_reports_unknown_execution_status(fake_server: FakeMcpServer, monkeypatch: pytest.MonkeyPatch) -> None:
    config = BridgeConfig("Demo", fake_server.url, 10, Path("bridge-project.toml"), execute_code_timeout_seconds=60)
    with FunplayBroker(config) as broker:
        monkeypatch.setattr(broker, "list_tools", lambda: [{"name": "execute_code", "inputSchema": {"type": "object", "properties": {"safety_checks": {"type": "boolean"}}}}])
        monkeypatch.setattr(broker, "call_tool", lambda *_args, **_kwargs: (_ for _ in ()).throw(BridgeError("timeout", "network timeout")))
        with pytest.raises(BridgeError) as error:
            call_execute_code(broker, "public class ReadOnlyProbe {}")
    assert error.value.kind == "execution_status_unknown"
    assert error.value.details == {"timeout_seconds": 60}


def test_execute_code_rejects_oversized_code(fake_server: FakeMcpServer) -> None:
    config = BridgeConfig("Demo", fake_server.url, 2, Path("bridge-project.toml"))
    with FunplayBroker(config) as broker:
        with pytest.raises(BridgeError, match="size limit"):
            call_execute_code(broker, "x" * (65_536 + 1))


def test_execute_code_refuses_when_funplay_cannot_enable_safety_checks() -> None:
    server = FakeMcpServer("unsafe_execute_schema")
    server.start()
    config = BridgeConfig("Demo", server.url, 2, Path("bridge-project.toml"))
    try:
        with FunplayBroker(config) as broker:
            with pytest.raises(BridgeError) as error:
                call_execute_code(broker, "public class ReadOnlyProbe {}")
        assert error.value.kind == "execute_code_unsafe"
        assert [request["method"] for request in server.requests] == ["tools/list"]
    finally:
        server.stop()
