from __future__ import annotations

from pathlib import Path

import pytest

from codex_funplay_bridge.config import BridgeConfig, ConfigError


def test_loads_valid_project_configuration(tmp_path: Path) -> None:
    source = tmp_path / "bridge-project.toml"
    source.write_text('project_name = "Demo"\nfunplay_url = "http://127.0.0.1:22166"\ntimeout_seconds = 3\n', encoding="utf-8")

    config = BridgeConfig.load(source)

    assert config.project_name == "Demo"
    assert config.funplay_url == "http://127.0.0.1:22166/"
    assert config.unity_project_root is None
    assert config.execute_code_timeout_seconds == 60


def test_loads_and_resolves_optional_unity_project_root(tmp_path: Path) -> None:
    source = tmp_path / "bridge-project.toml"
    root = tmp_path / "UnityProject"
    source.write_text(
        f'project_name = "Demo"\nfunplay_url = "http://127.0.0.1:22166"\nunity_project_root = {root.as_posix()!r}\n',
        encoding="utf-8",
    )

    config = BridgeConfig.load(source)

    assert config.unity_project_root == root.resolve()


@pytest.mark.parametrize("contents", ["project_name = ''\nfunplay_url = 'http://localhost'", "project_name = 'Demo'\nfunplay_url = 'not a url'", "project_name = 'Demo'\nfunplay_url = 'http://127.0.0.1:not-a-port'", "not valid toml ="])
def test_rejects_invalid_configuration(tmp_path: Path, contents: str) -> None:
    source = tmp_path / "bridge-project.toml"
    source.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError):
        BridgeConfig.load(source)


def test_rejects_relative_unity_project_root(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="absolute"):
        BridgeConfig.from_values("Demo", "http://localhost", 10, tmp_path / "bridge.toml", "relative/project")


@pytest.mark.parametrize("timeout", [0, -1, 301, True, "60"])
def test_rejects_invalid_execute_code_timeout(tmp_path: Path, timeout: object) -> None:
    with pytest.raises(ConfigError, match="execute_code_timeout_seconds"):
        BridgeConfig.from_values("Demo", "http://localhost", 10, tmp_path / "bridge.toml", execute_code_timeout_seconds=timeout)


def test_loads_configured_execute_code_timeout(tmp_path: Path) -> None:
    source = tmp_path / "bridge-project.toml"
    source.write_text(
        'project_name = "Demo"\nfunplay_url = "http://127.0.0.1:22166"\nexecute_code_timeout_seconds = 75\n',
        encoding="utf-8",
    )
    assert BridgeConfig.load(source).execute_code_timeout_seconds == 75
