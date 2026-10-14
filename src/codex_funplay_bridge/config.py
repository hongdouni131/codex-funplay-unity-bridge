"""Project-level configuration loading and validation."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .bridge_naming import validate_bridge_name


class ConfigError(ValueError):
    """Raised when the project configuration cannot be used."""


@dataclass(frozen=True)
class BridgeConfig:
    project_name: str
    funplay_url: str
    timeout_seconds: float
    source: Path
    unity_project_root: Path | None = None
    bridge_name: str | None = None
    execute_code_timeout_seconds: float = 60

    @classmethod
    def load(cls, path: Path | None = None) -> "BridgeConfig":
        source = path or Path(os.environ.get("UNITY_BRIDGE_CONFIG", "bridge-project.toml"))
        source = source.expanduser().resolve()
        if not source.is_file():
            raise ConfigError(f"Bridge configuration was not found: {source}")

        try:
            with source.open("rb") as config_file:
                raw = tomllib.load(config_file)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Bridge configuration is not valid TOML: {exc}") from exc

        return cls.from_values(
            raw.get("project_name"),
            raw.get("funplay_url"),
            raw.get("timeout_seconds", 10),
            source,
            raw.get("unity_project_root"),
            raw.get("bridge_name"),
            raw.get("execute_code_timeout_seconds", 60),
        )

    @classmethod
    def from_values(
        cls,
        project_name: object,
        funplay_url: object,
        timeout_seconds: object,
        source: Path,
        unity_project_root: object = None,
        bridge_name: object = None,
        execute_code_timeout_seconds: object = 60,
    ) -> "BridgeConfig":
        if not isinstance(project_name, str) or not project_name.strip():
            raise ConfigError("project_name must be a non-empty string")
        if not isinstance(funplay_url, str):
            raise ConfigError("funplay_url must be a string")

        try:
            parsed = urlsplit(funplay_url)
        except ValueError as exc:
            raise ConfigError("funplay_url is invalid") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConfigError("funplay_url must be an absolute HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise ConfigError("funplay_url must not contain credentials")
        try:
            parsed.port
        except ValueError as exc:
            raise ConfigError("funplay_url contains an invalid port") from exc
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise ConfigError("timeout_seconds must be a positive number")
        if timeout_seconds <= 0:
            raise ConfigError("timeout_seconds must be a positive number")
        if (
            not isinstance(execute_code_timeout_seconds, (int, float))
            or isinstance(execute_code_timeout_seconds, bool)
            or execute_code_timeout_seconds <= 0
            or execute_code_timeout_seconds > 300
        ):
            raise ConfigError("execute_code_timeout_seconds must be a positive number no greater than 300")

        project_root: Path | None = None
        if unity_project_root is not None:
            if isinstance(unity_project_root, Path):
                raw_project_root = unity_project_root
            elif isinstance(unity_project_root, str) and unity_project_root.strip():
                raw_project_root = Path(unity_project_root).expanduser()
            else:
                raise ConfigError("unity_project_root must be an absolute path string")
            project_root = raw_project_root
            if not project_root.is_absolute():
                raise ConfigError("unity_project_root must be an absolute path")
            project_root = project_root.resolve(strict=False)

        if bridge_name is not None:
            if not isinstance(bridge_name, str):
                raise ConfigError("bridge_name must be a string")
            try:
                bridge_name = validate_bridge_name(bridge_name)
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc

        return cls(
            project_name=project_name.strip(),
            funplay_url=funplay_url.rstrip("/") + "/",
            timeout_seconds=float(timeout_seconds),
            source=source,
            unity_project_root=project_root,
            bridge_name=bridge_name,
            execute_code_timeout_seconds=float(execute_code_timeout_seconds),
        )
