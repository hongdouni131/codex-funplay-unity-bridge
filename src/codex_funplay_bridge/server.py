"""stdio MCP server exposing a small, diagnostic Funplay bridge surface."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .audit_logging import AuditLogger
from .broker import BridgeError, FunplayBroker
from .config import BridgeConfig, ConfigError
from .health import run_health_check
from .ui_agent_tools import UiAgentTools, register_ui_agent_tools

server = FastMCP("Codex-Funplay Unity Bridge")


def _load() -> BridgeConfig:
    return BridgeConfig.load()


_ui_agent_tools = UiAgentTools(_load)


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, BridgeError):
        return {"ok": False, "error": exc.as_dict()}
    if isinstance(exc, ConfigError):
        return {"ok": False, "error": {"kind": "configuration_error", "message": str(exc), "details": {}}}
    return {"ok": False, "error": {"kind": "internal_error", "message": "Bridge operation failed", "details": {}}}


@server.tool(name="unity_bridge_info", description="Return Bridge version and the active project configuration.")
def unity_bridge_info() -> dict[str, Any]:
    try:
        config = _load()
        return {
            "ok": True,
            "bridge_version": __version__,
            "project_name": config.project_name,
            "bridge_name": config.bridge_name or config.project_name,
            "unity_project_root": str(config.unity_project_root) if config.unity_project_root else None,
            "funplay_url": config.funplay_url,
            "config_source": str(config.source),
        }
    except Exception as exc:
        return _error(exc)


@server.tool(name="unity_health_check", description="Check local Funplay connectivity, MCP initialization, and tool discovery.")
def unity_health_check() -> dict[str, Any]:
    try:
        config = _load()
        audit = AuditLogger(config.source.parent)
        result = run_health_check(config)
        audit.write("health_check", project_name=config.project_name, result=result)
        return result
    except Exception as exc:
        return _error(exc)


@server.tool(name="unity_list_tools", description="Forward MCP tools/list to the configured Funplay server.")
def unity_list_tools() -> dict[str, Any]:
    try:
        config = _load()
        with FunplayBroker(config) as broker:
            broker.initialize()
            tools = broker.list_tools()
        AuditLogger(config.source.parent).write("list_tools", project_name=config.project_name, tool_count=len(tools))
        return {"ok": True, "tools": tools, "tool_count": len(tools)}
    except Exception as exc:
        return _error(exc)


@server.tool(name="unity_call_tool", description="Forward a validated MCP tools/call request to the configured Funplay server.")
def unity_call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        if not isinstance(name, str) or not name.strip():
            raise BridgeError("invalid_arguments", "name must be a non-empty string")
        if arguments is not None and not isinstance(arguments, dict):
            raise BridgeError("invalid_arguments", "arguments must be an object")
        config = _load()
        with FunplayBroker(config) as broker:
            broker.initialize()
            timeout = config.execute_code_timeout_seconds if name.strip() == "execute_code" else None
            try:
                result = broker.call_tool(name, arguments or {}, timeout_seconds=timeout)
            except BridgeError as exc:
                if name.strip() == "execute_code" and exc.kind == "timeout":
                    raise BridgeError(
                        "execution_status_unknown",
                        "Timed out waiting for execute_code. Unity may still have completed or be running it; inspect execute_code history before retrying.",
                        {"timeout_seconds": config.execute_code_timeout_seconds},
                    ) from exc
                raise
        AuditLogger(config.source.parent).write("call_tool", project_name=config.project_name, tool_name=name, arguments=arguments or {}, result=result)
        return {"ok": True, "tool_name": name, "result": result}
    except Exception as exc:
        return _error(exc)


register_ui_agent_tools(server, _ui_agent_tools)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

