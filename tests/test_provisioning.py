from __future__ import annotations

from pathlib import Path

import pytest

from codex_funplay_bridge import provisioning
from codex_funplay_bridge.config import BridgeConfig
from codex_funplay_bridge.provisioning import ProvisioningError, create_plan, deploy, preflight
from conftest import FakeMcpServer


def unity_project(tmp_path: Path) -> Path:
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    return tmp_path


def test_create_plan_requires_unity_markers(tmp_path: Path) -> None:
    with pytest.raises(ProvisioningError, match="not a Unity project"):
        create_plan(tmp_path, "http://127.0.0.1:22166/")


@pytest.mark.parametrize("url", ["https://example.com:443/", "http://127.0.0.1/", "http://user:password@127.0.0.1:22166/", "http://127.0.0.1:not-a-port/"])
def test_create_plan_rejects_non_local_or_incomplete_url(tmp_path: Path, url: str) -> None:
    with pytest.raises(ProvisioningError):
        create_plan(unity_project(tmp_path), url)


def test_preflight_does_not_write_project_files(tmp_path: Path, fake_server: FakeMcpServer) -> None:
    root = unity_project(tmp_path)
    plan = create_plan(root, fake_server.url)

    report = preflight(plan)

    assert report["ok"] is True
    assert not plan.tools_directory.exists()


def test_deploy_refuses_to_overwrite_managed_files(tmp_path: Path, fake_server: FakeMcpServer) -> None:
    root = unity_project(tmp_path)
    plan = create_plan(root, fake_server.url)
    plan.tools_directory.mkdir()
    plan.config_path.write_text("existing", encoding="utf-8")

    with pytest.raises(ProvisioningError, match="will not be overwritten"):
        deploy(plan)


def test_deploy_installs_before_writing_managed_files(tmp_path: Path, fake_server: FakeMcpServer, monkeypatch: pytest.MonkeyPatch) -> None:
    root = unity_project(tmp_path)
    plan = create_plan(root, fake_server.url)
    install_observations: list[bool] = []

    def pretend_install(installed_plan: object, _: Path) -> None:
        install_observations.append(not plan.tools_directory.exists())

    monkeypatch.setattr(provisioning, "_install_bridge", pretend_install)
    files = deploy(plan)

    assert install_observations == [True]
    assert plan.config_path in files
    assert BridgeConfig.load(plan.config_path).funplay_url == fake_server.url
