from __future__ import annotations

import json
from pathlib import Path

from codex_funplay_bridge.audit_logging import AuditLogger, redact


def test_redact_hides_sensitive_values_recursively() -> None:
    result = redact({"api_key": "secret", "nested": [{"password": "value"}], "normal": "visible"})

    assert result == {"api_key": "[REDACTED]", "nested": [{"password": "[REDACTED]"}], "normal": "visible"}


def test_audit_logger_writes_jsonl(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path)
    logger.write("call_tool", token="secret", tool_name="read_scene")

    record = json.loads((tmp_path / "bridge-audit.jsonl").read_text(encoding="utf-8"))
    assert record["event"] == "call_tool"
    assert record["token"] == "[REDACTED]"
