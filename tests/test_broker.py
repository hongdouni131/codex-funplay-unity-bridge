from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from codex_funplay_bridge import __version__
from codex_funplay_bridge.broker import BridgeError, FunplayBroker
from codex_funplay_bridge.config import BridgeConfig
from conftest import FakeMcpServer


def config(url: str, timeout_seconds: float = 0.2) -> BridgeConfig:
    return BridgeConfig("Test", url, timeout_seconds, Path("bridge-project.toml"))


def test_initialize_list_and_call_forward_to_funplay(fake_server: FakeMcpServer) -> None:
    with FunplayBroker(config(fake_server.url)) as broker:
        initialization = broker.initialize()
        tools = broker.list_tools()
        result = broker.call_tool("read_scene", {"path": "Assets/Main.unity"})

    assert initialization["protocolVersion"] == "2025-03-26"
    assert fake_server.requests[0]["params"]["clientInfo"]["version"] == __version__
    assert tools[0]["name"] == "read_scene"
    assert result["content"][0]["text"] == "done"
    assert [request["method"] for request in fake_server.requests] == ["initialize", "notifications/initialized", "tools/list", "tools/call"]


def test_tool_call_accepts_operation_timeout() -> None:
    server = FakeMcpServer("slow")
    server.start()
    try:
        with FunplayBroker(config(server.url, timeout_seconds=0.05)) as broker:
            result = broker.call_tool("read_scene", {}, timeout_seconds=1)
    finally:
        server.stop()

    assert result["content"][0]["text"] == "done"


@pytest.mark.parametrize(
    ("mode", "expected_kind", "operation"),
    [
        ("not_found", "http_error", "list_tools"),
        ("invalid_json", "invalid_json", "list_tools"),
        ("jsonrpc_error", "jsonrpc_error", "list_tools"),
        ("old_protocol", "protocol_incompatible", "initialize"),
    ],
)
def test_broker_returns_structured_errors(mode: str, expected_kind: str, operation: str) -> None:
    server = FakeMcpServer(mode)
    server.start()
    try:
        with FunplayBroker(config(server.url)) as broker:
            with pytest.raises(BridgeError) as error:
                getattr(broker, operation)()
        assert error.value.kind == expected_kind
    finally:
        server.stop()


def test_connection_refused_is_diagnosable() -> None:
    def reject_connection(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = httpx.Client(transport=httpx.MockTransport(reject_connection))
    with FunplayBroker(config("http://127.0.0.1:22166/"), client=client) as broker:
        with pytest.raises(BridgeError) as error:
            broker.list_tools()
    assert error.value.kind == "connection_refused"


def test_timeout_is_diagnosable() -> None:
    server = FakeMcpServer("slow")
    server.start()
    try:
        with FunplayBroker(config(server.url, timeout_seconds=0.05)) as broker:
            with pytest.raises(BridgeError) as error:
                broker.list_tools()
        assert error.value.kind == "timeout"
    finally:
        server.stop()


def test_tool_argument_validation(fake_server: FakeMcpServer) -> None:
    with FunplayBroker(config(fake_server.url)) as broker:
        with pytest.raises(BridgeError, match="tool name"):
            broker.call_tool("", {})
        with pytest.raises(BridgeError, match="arguments"):
            broker.call_tool("read_scene", [])  # type: ignore[arg-type]
