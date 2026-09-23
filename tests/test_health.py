from __future__ import annotations

from pathlib import Path

from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.health import run_health_check
from conftest import FakeMcpServer


def test_health_check_initializes_and_counts_tools(fake_server: FakeMcpServer) -> None:
    config = BridgeConfig("Test", fake_server.url, 1, Path("bridge-project.toml"))
    report = run_health_check(config)

    assert report["ok"] is True
    assert report["tool_count"] == 1
    assert [check["name"] for check in report["checks"]] == ["port", "initialize", "tools/list"]


def test_health_check_reports_unreachable_port() -> None:
    config = BridgeConfig("Test", "http://127.0.0.1:1/", 0.1, Path("bridge-project.toml"))
    report = run_health_check(config)

    assert report["ok"] is False
    assert report["checks"][0]["kind"] == "port_not_listening"

