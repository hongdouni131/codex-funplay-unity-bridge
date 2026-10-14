from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_funplay_bridge import server
from codex_funplay_bridge.config import BridgeConfig


class RecordingBroker:
    instances: list["RecordingBroker"] = []

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.timeout: float | None = None
        self.tool_name = ""
        self.instances.append(self)

    def __enter__(self) -> "RecordingBroker":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def initialize(self) -> dict[str, Any]:
        return {}

    def call_tool(self, name: str, _arguments: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        self.tool_name = name
        self.timeout = timeout_seconds
        return {"content": []}


@pytest.mark.parametrize(("name", "expected_timeout"), [("execute_code", 60), ("read_scene", None)])
def test_unity_call_tool_uses_dedicated_timeout_only_for_execute_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, expected_timeout: float | None
) -> None:
    RecordingBroker.instances.clear()
    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml", execute_code_timeout_seconds=60)
    monkeypatch.setattr(server, "_load", lambda: config)
    monkeypatch.setattr(server, "FunplayBroker", RecordingBroker)

    result = server.unity_call_tool(name, {})

    assert result["ok"] is True
    assert RecordingBroker.instances[-1].timeout == expected_timeout


def test_execute_code_timeout_returns_unknown_status_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TimeoutBroker(RecordingBroker):
        calls = 0

        def call_tool(self, name: str, _arguments: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
            self.calls += 1
            from codex_funplay_bridge.broker import BridgeError

            raise BridgeError("timeout", "Timed out", {"timeout_seconds": timeout_seconds})

    config = BridgeConfig("Demo", "http://127.0.0.1:22166/", 10, tmp_path / "bridge.toml", execute_code_timeout_seconds=60)
    monkeypatch.setattr(server, "_load", lambda: config)
    monkeypatch.setattr(server, "FunplayBroker", TimeoutBroker)

    result = server.unity_call_tool("execute_code", {"code": "read only"})

    assert result["ok"] is False
    assert result["error"]["kind"] == "execution_status_unknown"
    assert TimeoutBroker.instances[-1].calls == 1
