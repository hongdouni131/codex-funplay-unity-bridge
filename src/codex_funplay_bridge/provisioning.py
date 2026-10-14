"""Preflight validation and project-local Bridge deployment."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .config import BridgeConfig, ConfigError
from .health import run_health_check


class ProvisioningError(ValueError):
    """Raised when a Unity project cannot safely receive the Bridge files."""


def _resource_root() -> Path:
    """Return source resources normally, or PyInstaller's extracted resources."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).resolve()  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def _default_package_path(resource_root: Path) -> Path:
    if not getattr(sys, "frozen", False):
        return resource_root
    wheels = sorted((resource_root / "package").glob("codex_funplay_bridge-*.whl"))
    if len(wheels) != 1:
        raise ProvisioningError("Bridge package wheel is missing from the setup application")
    return wheels[0]


@dataclass(frozen=True)
class DeploymentPlan:
    project_root: Path
    project_name: str
    funplay_url: str
    timeout_seconds: float
    tools_directory: Path
    config_path: Path
    virtualenv_path: Path
    package_path: Path
    bridge_name: str | None = None
    execute_code_timeout_seconds: float = 60

    @property
    def managed_paths(self) -> tuple[Path, ...]:
        return (
            self.config_path,
            self.tools_directory / "requirements-unity-http-bridge.txt",
            self.tools_directory / "start_unity_http_stdio_bridge.cmd",
            self.tools_directory / "initialize_unity_http_stdio_bridge.cmd",
        )


def create_plan(
    project_root: str | Path,
    funplay_url: str,
    timeout_seconds: float = 10,
    package_path: Path | None = None,
    *,
    bridge_name: str | None = None,
    execute_code_timeout_seconds: float = 60,
) -> DeploymentPlan:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ProvisioningError(f"Unity project directory does not exist: {root}")
    missing_markers = [name for name in ("Assets", "ProjectSettings") if not (root / name).is_dir()]
    if missing_markers:
        raise ProvisioningError(
            "Selected directory is not a Unity project. Missing required directory: " + ", ".join(missing_markers)
        )

    source = root / "tools" / "bridge-project.toml"
    try:
        # Reuse the runtime configuration rules before the deployment writes files.
        candidate = BridgeConfig.from_values(
            root.name, funplay_url, timeout_seconds, source, root, bridge_name, execute_code_timeout_seconds
        )
    except ConfigError as exc:
        raise ProvisioningError(str(exc)) from exc

    parsed = urlsplit(candidate.funplay_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ProvisioningError("funplay_url must point to a local host: 127.0.0.1, localhost, or ::1")
    if parsed.port is None:
        raise ProvisioningError("funplay_url must include the port displayed by Funplay MCP Server")

    resource_root = _resource_root()
    package_source = (package_path or _default_package_path(resource_root)).resolve()
    template_tools = resource_root / "templates" / "unity-project" / "tools"
    if not template_tools.is_dir():
        raise ProvisioningError(f"Bridge template files are unavailable: {template_tools}")
    if package_source.is_dir() and not (package_source / "pyproject.toml").is_file():
        raise ProvisioningError(f"Bridge package metadata is unavailable: {package_source / 'pyproject.toml'}")
    if package_source.is_file() and package_source.suffix != ".whl":
        raise ProvisioningError(f"Bridge package must be a wheel or source directory: {package_source}")
    if not package_source.exists():
        raise ProvisioningError(f"Bridge package is unavailable: {package_source}")

    return DeploymentPlan(
        project_root=root,
        project_name=candidate.project_name,
        funplay_url=candidate.funplay_url,
        timeout_seconds=candidate.timeout_seconds,
        tools_directory=source.parent,
        config_path=source,
        virtualenv_path=root / ".unity-mcp-bridge-venv",
        package_path=package_source,
        bridge_name=candidate.bridge_name,
        execute_code_timeout_seconds=candidate.execute_code_timeout_seconds,
    )


def preflight(plan: DeploymentPlan) -> dict[str, object]:
    """Test the entered settings without creating or changing target files."""
    config = _validate_values(plan.project_name, plan.funplay_url, plan.timeout_seconds, plan.config_path)
    report = run_health_check(config)
    runtime_check = _probe_python_runtime()
    report["checks"].insert(0, runtime_check)  # type: ignore[index]
    if not runtime_check["ok"]:
        report["ok"] = False
        report["diagnosis"] = "Python 3.11 is required to create the Unity project's isolated Bridge environment."
    report["deployment"] = {
        "project_root": str(plan.project_root),
        "tools_directory": str(plan.tools_directory),
        "virtualenv_path": str(plan.virtualenv_path),
        "existing_managed_files": [str(path) for path in plan.managed_paths if path.exists()],
    }
    return report


def deploy(plan: DeploymentPlan, *, replace_existing: bool = False) -> list[Path]:
    """Copy managed files and install the Bridge into the Unity project's venv."""
    existing = [path for path in plan.managed_paths if path.exists()]
    if existing and not replace_existing:
        joined = ", ".join(str(path) for path in existing)
        raise ProvisioningError(f"Managed Bridge files already exist and will not be overwritten: {joined}")

    template_tools = _resource_root() / "templates" / "unity-project" / "tools"
    _install_bridge(plan, template_tools / "requirements-unity-http-bridge.txt")
    plan.tools_directory.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for name in (
        "requirements-unity-http-bridge.txt",
        "start_unity_http_stdio_bridge.cmd",
        "initialize_unity_http_stdio_bridge.cmd",
    ):
        source = template_tools / name
        destination = plan.tools_directory / name
        shutil.copy2(source, destination)
        copied.append(destination)

    _write_config(plan)
    copied.append(plan.config_path)
    return copied


def _validate_values(
    project_name: str,
    funplay_url: str,
    timeout_seconds: float,
    source: Path,
    unity_project_root: Path | None = None,
) -> BridgeConfig:
    return BridgeConfig.from_values(project_name, funplay_url, timeout_seconds, source, unity_project_root)


def _write_config(plan: DeploymentPlan) -> None:
    contents = (
        f"project_name = {json.dumps(plan.project_name)}\n"
        f"unity_project_root = {json.dumps(str(plan.project_root))}\n"
        f"funplay_url = {json.dumps(plan.funplay_url)}\n"
        f'timeout_seconds = {plan.timeout_seconds:g}\n'
        f'execute_code_timeout_seconds = {plan.execute_code_timeout_seconds:g}\n'
    )
    if plan.bridge_name is not None:
        contents += f"bridge_name = {json.dumps(plan.bridge_name, ensure_ascii=False)}\n"
    temporary_path = plan.config_path.with_suffix(".toml.tmp")
    temporary_path.write_text(contents, encoding="utf-8")
    temporary_path.replace(plan.config_path)


def _probe_python_runtime() -> dict[str, object]:
    if not getattr(sys, "frozen", False):
        return {"name": "python", "ok": sys.version_info[:2] == (3, 11), "version": sys.version.split()[0]}
    completed = subprocess.run(["py", "-3.11", "--version"], text=True, capture_output=True, check=False)
    if completed.returncode == 0:
        return {"name": "python", "ok": True, "version": completed.stdout.strip() or completed.stderr.strip()}
    return {"name": "python", "ok": False, "message": "Python 3.11 was not found through the Windows py launcher."}


def _install_bridge(plan: DeploymentPlan, requirements_path: Path) -> None:
    python = plan.virtualenv_path / "Scripts" / "python.exe"
    if not python.is_file():
        venv_python = ["py", "-3.11"] if getattr(sys, "frozen", False) else [sys.executable]
        _run([*venv_python, "-m", "venv", str(plan.virtualenv_path)], plan.project_root, "Failed to create Bridge virtual environment")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], plan.project_root, "Failed to upgrade pip")
    _run(
        [str(python), "-m", "pip", "install", "-r", str(requirements_path)],
        plan.project_root,
        "Failed to install Bridge runtime dependencies",
    )
    _run([str(python), "-m", "pip", "install", str(plan.package_path)], plan.project_root, "Failed to install Bridge package")


def _run(command: list[str], cwd: Path, heading: str) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        output = (completed.stdout + "\n" + completed.stderr).strip()
        raise ProvisioningError(f"{heading}.\n{output[-2000:]}")
