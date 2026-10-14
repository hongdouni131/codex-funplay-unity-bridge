"""Display names and portable MCP identifiers for project-local bridges."""

from __future__ import annotations

import hashlib
import re


def validate_bridge_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("Bridge name must contain 1-80 characters on a single line")
    return name


def bridge_server_name(value: str) -> str:
    name = validate_bridge_name(value)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not name.isascii() or not slug:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
        slug = (slug[:40] or "custom") + "_" + digest
    return "unity_bridge_" + slug
