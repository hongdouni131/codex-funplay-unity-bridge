"""HTTP JSON-RPC client for the Funplay MCP service."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import httpx

from . import __version__
from .config import BridgeConfig

SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26"})
REQUESTED_PROTOCOL_VERSION = "2025-03-26"


@dataclass
class BridgeError(Exception):
    kind: str
    message: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "details": self.details or {}}


class FunplayBroker:
    def __init__(self, config: BridgeConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        # Unity/Funplay is a local service. Environment proxy settings must not
        # redirect or block its loopback traffic.
        self._client = client or httpx.Client(timeout=config.timeout_seconds, trust_env=False)
        self._owns_client = client is None
        self._ids = itertools.count(1)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FunplayBroker":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def initialize(self) -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": REQUESTED_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "codex-funplay-bridge", "version": __version__},
            },
        )
        protocol_version = result.get("protocolVersion") if isinstance(result, dict) else None
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise BridgeError(
                "protocol_incompatible",
                "Funplay selected an unsupported MCP protocol version",
                {"received": protocol_version, "supported": sorted(SUPPORTED_PROTOCOL_VERSIONS)},
            )
        self._notify("notifications/initialized", {})
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise BridgeError("invalid_response", "tools/list response does not contain a tools array")
        if not all(isinstance(tool, dict) for tool in tools):
            raise BridgeError("invalid_response", "tools/list response contains an invalid tool definition")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise BridgeError("invalid_arguments", "tool name must be a non-empty string")
        if not isinstance(arguments, dict):
            raise BridgeError("invalid_arguments", "tool arguments must be an object")
        result = self._request("tools/call", {"name": name.strip(), "arguments": arguments}, timeout_seconds=timeout_seconds)
        if not isinstance(result, dict):
            raise BridgeError("invalid_response", "tools/call response must be an object")
        return result

    def _request(self, method: str, params: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        request_id = next(self._ids)
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        response = self._post(payload, timeout_seconds=timeout_seconds)
        try:
            body = response.json()
        except ValueError as exc:
            raise BridgeError("invalid_json", "Funplay returned a non-JSON response") from exc
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            raise BridgeError("invalid_response", "Funplay returned an invalid JSON-RPC response")
        if body.get("id") != request_id:
            raise BridgeError("invalid_response", "Funplay response ID does not match the request")
        if "error" in body:
            error = body["error"]
            raise BridgeError("jsonrpc_error", "Funplay returned a JSON-RPC error", {"error": error})
        if "result" not in body:
            raise BridgeError("invalid_response", "Funplay response is missing result")
        return body["result"]

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def _post(self, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> httpx.Response:
        try:
            response = self._client.post(
                self.config.funplay_url,
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
                timeout=self.config.timeout_seconds if timeout_seconds is None else timeout_seconds,
            )
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            effective_timeout = self.config.timeout_seconds if timeout_seconds is None else timeout_seconds
            raise BridgeError(
                "timeout",
                "Timed out while contacting Funplay",
                {"url": self.config.funplay_url, "timeout_seconds": effective_timeout},
            ) from exc
        except httpx.ConnectError as exc:
            raise BridgeError(
                "connection_refused",
                "Could not connect to Funplay. Verify Unity and Funplay MCP Server are running.",
                {"url": self.config.funplay_url},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise BridgeError(
                "http_error",
                f"Funplay returned HTTP {exc.response.status_code}",
                {"status_code": exc.response.status_code, "url": self.config.funplay_url},
            ) from exc
        except httpx.HTTPError as exc:
            raise BridgeError("http_error", "HTTP communication with Funplay failed", {"url": self.config.funplay_url}) from exc
