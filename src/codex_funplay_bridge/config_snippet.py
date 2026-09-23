"""Generate a user-confirmed Codex MCP configuration snippet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class ConfigSnippetError(ValueError):
    """Raised when a Codex configuration snippet cannot be generated."""


def _validate_project_root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ConfigSnippetError(f"Unity project directory does not exist: {root}")
    markers = (root / "Assets", root / "ProjectSettings")
    missing = [str(path.name) for path in markers if not path.is_dir()]
    if missing:
        raise ConfigSnippetError(
            "Selected directory is not a Unity project. Missing: " + ", ".join(missing)
        )
    launcher = root / "tools" / "start_unity_http_stdio_bridge.cmd"
    if not launcher.is_file():
        raise ConfigSnippetError(
            f"Bridge launcher was not found: {launcher}. Deploy the Bridge first."
        )
    return root


def _validate_name(project_name: str) -> str:
    name = project_name.strip()
    if not name:
        raise ConfigSnippetError("Project name must not be empty")
    if "\n" in name or "\r" in name:
        raise ConfigSnippetError("Project name must be a single line")
    return name


def build_config_snippet(project_name: str, project_root: str | Path) -> str:
    """Return a TOML MCP server entry for a confirmed Bridge deployment."""
    name = _validate_name(project_name)
    root = _validate_project_root(project_root)
    server_name = "unity_bridge_" + "_".join(
        part for part in "".join(character.lower() if character.isalnum() else "_" for character in name).split("_") if part
    )
    launcher = root / "tools" / "start_unity_http_stdio_bridge.cmd"
    return (
        f"[mcp_servers.{server_name}]\n"
        f"command = {json.dumps(str(launcher))}\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-funplay-bridge-config",
        description="Generate a Codex MCP config snippet after user confirmation.",
    )
    parser.add_argument("--project-name", help="The project name to use in the MCP entry.")
    parser.add_argument("--project-root", help="Absolute path to the Unity project root.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_name = args.project_name or input("Unity 项目名称: ").strip()
    project_root = args.project_root or input("Unity 项目根目录: ").strip()
    try:
        snippet = build_config_snippet(project_name, project_root)
    except ConfigSnippetError as exc:
        print(f"配置片段生成失败：{exc}", file=sys.stderr)
        return 2

    print("请确认以下项目名和路径无误：", file=sys.stderr)
    print(f"项目名：{project_name.strip()}", file=sys.stderr)
    print(f"项目路径：{Path(project_root).expanduser().resolve()}", file=sys.stderr)
    answer = input("确认生成 Codex 配置片段？[y/N] ").strip().lower()
    if answer not in {"y", "yes", "是", "确认"}:
        print("已取消；未写入任何 Codex 配置。", file=sys.stderr)
        return 1

    print(snippet, end="")
    print("请复制以上内容，人工粘贴到 Codex 的 MCP 配置中。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
