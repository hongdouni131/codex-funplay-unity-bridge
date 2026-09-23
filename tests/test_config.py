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


@pytest.mark.parametrize("contents", ["project_name = ''\nfunplay_url = 'http://localhost'", "project_name = 'Demo'\nfunplay_url = 'not a url'", "project_name = 'Demo'\nfunplay_url = 'http://127.0.0.1:not-a-port'", "not valid toml ="])
def test_rejects_invalid_configuration(tmp_path: Path, contents: str) -> None:
    source = tmp_path / "bridge-project.toml"
    source.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError):
        BridgeConfig.load(source)
