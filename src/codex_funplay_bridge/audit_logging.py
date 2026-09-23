"""JSONL audit logging that keeps credentials out of log files."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "authorization", "api_key", "apikey")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, config_directory: Path) -> None:
        configured_path = os.environ.get("UNITY_BRIDGE_AUDIT_LOG")
        self.path = Path(configured_path).expanduser() if configured_path else config_directory / "bridge-audit.jsonl"

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **redact(fields),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

