from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from codex_funplay_bridge.config_snippet import ConfigSnippetError, build_config_snippet


def _unity_project(tmp_path: Path) -> Path:
    root = tmp_path / "Demo Project"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    (root / "tools").mkdir()
    (root / "tools" / "start_unity_http_stdio_bridge.cmd").write_text("@echo off\n", encoding="utf-8")
    return root


def test_build_config_snippet_requires_deployed_launcher(tmp_path: Path) -> None:
    root = tmp_path / "Unity"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    with pytest.raises(ConfigSnippetError, match="launcher"):
        build_config_snippet("Demo", root)


def test_build_config_snippet_uses_confirmed_project_path(tmp_path: Path) -> None:
    root = _unity_project(tmp_path)
    snippet = build_config_snippet("Navmesh Study", root)
    assert "[mcp_servers.unity_bridge_navmesh_study]" in snippet
    assert "start_unity_http_stdio_bridge.cmd" in snippet
    assert "command =" in snippet


def test_build_config_snippet_rejects_empty_name(tmp_path: Path) -> None:
    root = _unity_project(tmp_path)
    with pytest.raises(ConfigSnippetError, match="Project name"):
        build_config_snippet("  ", root)


def test_custom_bridge_name_changes_mcp_key_but_preserves_launcher(tmp_path: Path) -> None:
    root = _unity_project(tmp_path)
    data = tomllib.loads(build_config_snippet("Demo Project", root, bridge_name="UI Sandbox"))
    assert data["mcp_servers"]["unity_bridge_ui_sandbox"]["command"] == str(root / "tools" / "start_unity_http_stdio_bridge.cmd")


def test_unicode_bridge_name_produces_portable_distinct_keys(tmp_path: Path) -> None:
    root = _unity_project(tmp_path)
    first = build_config_snippet("Demo", root, bridge_name="界面测试桥")
    second = build_config_snippet("Demo", root, bridge_name="战斗测试桥")
    first_key = next(iter(tomllib.loads(first)["mcp_servers"]))
    second_key = next(iter(tomllib.loads(second)["mcp_servers"]))
    assert first_key.isascii()
    assert first_key != second_key
    assert first == build_config_snippet("Demo", root, bridge_name="界面测试桥")


@pytest.mark.parametrize("name", ["   ", "bad\nname", "x" * 81])
def test_snippet_rejects_invalid_custom_bridge_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigSnippetError, match="Bridge name"):
        build_config_snippet("Demo", _unity_project(tmp_path), bridge_name=name)
