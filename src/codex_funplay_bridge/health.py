"""Health checks for a configured local Funplay MCP service."""

from __future__ import annotations

import socket
import time
from typing import Any
from urllib.parse import urlsplit

from .broker import BridgeError, FunplayBroker
from .config import BridgeConfig


def probe_port(config: BridgeConfig) -> dict[str, Any]:
    parsed = urlsplit(config.funplay_url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.perf_counter()
    try:
        with socket.create_connection((parsed.hostname or "", port), timeout=config.timeout_seconds):
            return {"name": "port", "ok": True, "host": parsed.hostname, "port": port, "latency_ms": _elapsed(started)}
    except socket.gaierror as exc:
        return {"name": "port", "ok": False, "kind": "dns_error", "message": str(exc), "host": parsed.hostname, "port": port}
    except OSError as exc:
        return {
            "name": "port",
            "ok": False,
            "kind": "port_not_listening",
            "message": "Cannot reach the configured port. Unity/Funplay may be stopped or recompiling.",
            "host": parsed.hostname,
            "port": port,
            "details": str(exc),
        }


def run_health_check(config: BridgeConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [probe_port(config)]
    report: dict[str, Any] = {
        "ok": False,
        "project_name": config.project_name,
        "funplay_url": config.funplay_url,
        "config_source": str(config.source),
        "checks": checks,
    }
    if not checks[0]["ok"]:
        report["diagnosis"] = "The configured port is unreachable. Start Funplay in Unity, then retry after compilation or domain reload completes."
        return report

    started = time.perf_counter()
    try:
        with FunplayBroker(config) as broker:
            initialization = broker.initialize()
            checks.append({
                "name": "initialize",
                "ok": True,
                "protocol_version": initialization["protocolVersion"],
                "latency_ms": _elapsed(started),
            })
            tools = broker.list_tools()
            checks.append({"name": "tools/list", "ok": True, "tool_count": len(tools), "latency_ms": _elapsed(started)})
    except BridgeError as exc:
        checks.append({"name": "mcp", "ok": False, **exc.as_dict()})
        report["diagnosis"] = _diagnosis_for(exc.kind)
        return report

    report["ok"] = True
    report["tool_count"] = len(tools)
    report["latency_ms"] = _elapsed(started)
    return report


def _elapsed(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _diagnosis_for(kind: str) -> str:
    diagnoses = {
        "timeout": "Funplay did not respond in time. Unity may be busy compiling or reloading its domain.",
        "connection_refused": "Funplay is not accepting connections. Verify Unity and Funplay MCP Server are running.",
        "http_error": "Funplay returned an HTTP error. Confirm the exact URL shown in the Unity MCP Server window.",
        "invalid_json": "The endpoint did not return MCP JSON. Confirm this is the Funplay MCP URL, not another service.",
        "protocol_incompatible": "Funplay selected an unsupported MCP protocol version. Update the bridge or Funplay.",
        "jsonrpc_error": "Funplay rejected an MCP request. Inspect the structured error details and Unity Console.",
    }
    return diagnoses.get(kind, "Funplay returned an incompatible MCP response. Verify its server version and URL.")

