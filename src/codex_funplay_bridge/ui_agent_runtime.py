"""Safe Unity runtime guards and execute_code transport helpers."""

from __future__ import annotations

import json
import os
import base64
from pathlib import Path
from typing import Any

from .broker import BridgeError, FunplayBroker
from .config import BridgeConfig

MAX_EXECUTE_CODE_LENGTH = 65_536


def build_guarded_command(expected_project_root: Path, operation_statement: str) -> str:
    """Build a trusted command template that guards the operation on Unity's main thread.

    operation_statement must be a fixed Bridge-authored C# statement. Caller data must
    be encoded with csharp_string_literal and must never be interpolated as C# syntax.
    """
    root = expected_project_root.expanduser()
    if not root.is_absolute():
        raise BridgeError("project_identity_unverified", "Configured Unity project root must be absolute")
    root = root.resolve(strict=False)
    if not isinstance(operation_statement, str) or not operation_statement.strip():
        raise BridgeError("invalid_arguments", "A fixed Unity operation template is required")

    expected = base64.b64encode(str(root).encode("utf-8")).decode("ascii")
    return f'''using Funplay.Editor.Tools.Scripting;
using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

public class UiAgentGuardedCommand : IFunplayCommand
{{
    public void Execute(ExecutionContext ctx)
    {{
        string actualRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        string expectedRoot = Encoding.UTF8.GetString(Convert.FromBase64String("{expected}"));
        bool projectMatches = String.Equals(actualRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), expectedRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar), StringComparison.OrdinalIgnoreCase);
        if (!projectMatches)
        {{
            ctx.ReturnValue = new {{ guard = new {{ status = "project_mismatch", expectedProjectRoot = expectedRoot, actualProjectRoot = actualRoot }}, result = (object)null }};
            return;
        }}
        bool compiling = EditorApplication.isCompiling;
        bool updating = EditorApplication.isUpdating;
        bool playing = EditorApplication.isPlayingOrWillChangePlaymode;
        if (compiling || updating || playing)
        {{
            ctx.ReturnValue = new {{ guard = new {{ status = "editor_not_ready", projectRoot = actualRoot, isCompiling = compiling, isUpdating = updating, isPlayingOrChangingPlayMode = playing }}, result = (object)null }};
            return;
        }}
        {operation_statement.strip()}
        object operationResult = ctx.ReturnValue;
        ctx.ReturnValue = new {{ guard = new {{ status = "ready", projectRoot = actualRoot, projectName = Application.productName }}, result = operationResult }};
    }}
}}'''


def build_context_probe(expected_project_root: Path) -> str:
    return build_guarded_command(
        expected_project_root,
        "ctx.ReturnValue = Application.productName;",
    )


def csharp_string_literal(value: str) -> str:
    """Encode arbitrary caller text as one C# string literal."""
    escaped: list[str] = ['"']
    for char in value:
        code = ord(char)
        if char == '"':
            escaped.append('\\"')
        elif char == "\\":
            escaped.append("\\\\")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif code < 0x20 or code in (0x2028, 0x2029):
            escaped.append(f"\\u{code:04x}")
        elif code > 0xFFFF:
            escaped.append(f"\\U{code:08x}")
        else:
            escaped.append(char)
    escaped.append('"')
    return "".join(escaped)


def verify_context_result(config: BridgeConfig, result: dict[str, Any]) -> None:
    if config.unity_project_root is None:
        raise BridgeError(
            "project_identity_unverified",
            "This Bridge configuration has no unity_project_root; redeploy or update its project-local configuration.",
        )
    if not isinstance(result, dict):
        raise BridgeError("invalid_response", "Unity context probe did not return an object")

    context = result.get("guard", result)
    if not isinstance(context, dict):
        raise BridgeError("invalid_response", "Unity context guard did not return an object")
    status = context.get("status")
    if status == "project_mismatch":
        raise BridgeError(
            "project_identity_mismatch",
            "Connected Unity Editor does not match this project's Bridge configuration.",
            {"expected_project_root": str(config.unity_project_root), "actual_project_root": context.get("actualProjectRoot")},
        )
    if status == "editor_not_ready":
        raise BridgeError("editor_not_ready", "Unity Editor is compiling, updating, or playing", context)
    if status != "ready":
        raise BridgeError("invalid_response", "Unity context probe returned an unknown status", {"status": status})
    actual_root = context.get("projectRoot")
    if not isinstance(actual_root, str) or os.path.normcase(str(Path(actual_root).resolve(strict=False))) != os.path.normcase(str(config.unity_project_root)):
        raise BridgeError(
            "project_identity_mismatch",
            "Unity context result does not match this project's Bridge configuration.",
            {"expected_project_root": str(config.unity_project_root), "actual_project_root": actual_root},
        )


def call_guarded_command(
    config: BridgeConfig,
    broker: FunplayBroker,
    operation_statement: str,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if config.unity_project_root is None:
        raise BridgeError(
            "project_identity_unverified",
            "This Bridge configuration has no unity_project_root; redeploy or update its project-local configuration.",
        )
    code = build_guarded_command(config.unity_project_root, operation_statement)
    result = call_execute_code(broker, code, timeout_seconds=timeout_seconds)
    verify_context_result(config, result)
    if "guard" not in result or "result" not in result:
        raise BridgeError("invalid_response", "Unity command response is missing the runtime guard envelope")
    return result


def call_execute_code(
    broker: FunplayBroker,
    code: str,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if not isinstance(code, str) or not code.strip():
        raise BridgeError("invalid_arguments", "execute_code code must be a non-empty string")
    if len(code) > MAX_EXECUTE_CODE_LENGTH:
        raise BridgeError("invalid_arguments", "execute_code code exceeds the Bridge size limit")
    effective_timeout = timeout_seconds if timeout_seconds is not None else broker.config.execute_code_timeout_seconds
    if effective_timeout <= 0:
        raise BridgeError("invalid_arguments", "execute_code timeout_seconds must be positive")

    tool = next((item for item in broker.list_tools() if item.get("name") == "execute_code"), None)
    schema = tool.get("inputSchema") if isinstance(tool, dict) else None
    properties = schema.get("properties") if isinstance(schema, dict) else None
    safety_schema = properties.get("safety_checks") if isinstance(properties, dict) else None
    if not isinstance(safety_schema, dict) or safety_schema.get("type") != "boolean":
        raise BridgeError("execute_code_unsafe", "Funplay execute_code does not expose the required safety_checks boolean")

    try:
        response = broker.call_tool(
            "execute_code",
            {"code": code, "safety_checks": True},
            timeout_seconds=effective_timeout,
        )
    except BridgeError as exc:
        if exc.kind == "timeout":
            raise BridgeError(
                "execution_status_unknown",
                "Timed out waiting for execute_code. Unity may still have completed or be running it; inspect execute_code history before retrying.",
                {"timeout_seconds": effective_timeout},
            ) from exc
        raise
    return parse_execute_code_result(response)


def parse_execute_code_result(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise BridgeError("invalid_response", "execute_code returned a non-object response")
    if response.get("isError") is True:
        raise BridgeError("execute_code_failed", "Funplay rejected execute_code", _bounded_details(response))

    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        return _unwrap_execution_payload(structured)

    content = response.get("content")
    if not isinstance(content, list):
        raise BridgeError("invalid_response", "execute_code response has no structured content")
    text_blocks = [item.get("text") for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
    if len(text_blocks) != 1:
        raise BridgeError("invalid_response", "execute_code response must contain exactly one text result", {"text_block_count": len(text_blocks)})
    try:
        payload = json.loads(text_blocks[0])
    except json.JSONDecodeError as exc:
        raise BridgeError("execute_code_failed", "Unity did not return structured JSON from execute_code", {"message": text_blocks[0][:500]}) from exc
    if not isinstance(payload, dict):
        raise BridgeError("invalid_response", "execute_code JSON result must be an object")
    return _unwrap_execution_payload(payload)


def _unwrap_execution_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is False:
        raise BridgeError("execute_code_failed", str(payload.get("error") or payload.get("message") or "Unity execution failed")[:500], _bounded_details(payload))
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise BridgeError("invalid_response", "execute_code result data must be an object")
    value = data.get("returnValue", data.get("return_value", data))
    if not isinstance(value, dict):
        raise BridgeError("invalid_response", "Unity command return value must be an object")
    return value


def _bounded_details(value: Any) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=True, default=str)
    except (TypeError, ValueError):
        encoded = str(value)
    return {"response": encoded[:2000]}
