from __future__ import annotations

from pathlib import Path

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
