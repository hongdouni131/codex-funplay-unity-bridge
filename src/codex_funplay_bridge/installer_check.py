"""Opt-in acceptance check of the built installer, isolated from user projects."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tkinter as tk
import zipfile
from pathlib import Path

from . import __version__
from .config import BridgeConfig
from .provisioning import create_plan, deploy
from .setup_wizard import SetupWizard


_MCP_CHECK = '''
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "codex_funplay_bridge.server"], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            registered = await session.list_tools()
            info = await session.call_tool("unity_bridge_info", {})
            payload = json.loads(info.content[0].text)
            assert payload["ok"] and payload["bridge_version"] == sys.argv[1], payload
            names = sorted(t.name for t in registered.tools)
            assert len(names) == 9 and sum(n.startswith("ui_agent_") for n in names) == 5, names
            print(json.dumps({"version": payload["bridge_version"], "tools": names}))
asyncio.run(main())
'''


def check_installer(report_path: Path) -> int:
    report: dict[str, object] = {"ok": False, "version": __version__, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            wizard = SetupWizard(root)
            wizard.bridge_name.set("验收测试桥")
            root.update_idletasks()
            assert wizard.execute_code_timeout.get() == "60"
            assert "unity_bridge_" in wizard.name_preview.get()
            report["gui_components"] = "passed"
        finally:
            root.destroy()
        with tempfile.TemporaryDirectory(prefix="Bridge release check ") as directory:
            project = Path(directory) / "Temporary Unity Project"
            (project / "Assets").mkdir(parents=True)
            (project / "ProjectSettings").mkdir()
            plan = create_plan(project, "http://127.0.0.1:22166/", bridge_name="验收测试桥", execute_code_timeout_seconds=75)
            if report["frozen"]:
                with zipfile.ZipFile(plan.package_path) as wheel:
                    runtime = wheel.read("codex_funplay_bridge/__init__.py").decode("utf-8")
                    assert f'__version__ = "{__version__}"' in runtime
                report["bundled_wheel"] = plan.package_path.name
            plan.tools_directory.mkdir(parents=True)
            for path in plan.managed_paths:
                path.write_text("previous managed version", encoding="utf-8")
            deployed = deploy(plan, replace_existing=True)
            config = BridgeConfig.load(plan.config_path)
            assert config.unity_project_root == project.resolve()
            assert config.bridge_name == "验收测试桥" and config.execute_code_timeout_seconds == 75
            assert all(path.read_text(encoding="utf-8") != "previous managed version" for path in plan.managed_paths)
            report["deployment"] = {"managed_files": [p.name for p in deployed], "custom_name_and_timeout": "passed"}
            report["replacement_of_existing_managed_files"] = "passed"
            python = plan.virtualenv_path / "Scripts" / "python.exe"
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["UNITY_BRIDGE_CONFIG"] = str(plan.config_path)
            checked = subprocess.run([str(python), "-m", "pip", "check"], cwd=project, env=env, capture_output=True, text=True, check=True)
            report["pip_check"] = checked.stdout.strip()
            mcp = subprocess.run([str(python), "-c", _MCP_CHECK, __version__], cwd=project, env=env, capture_output=True, text=True, check=True, timeout=60)
            report["installed_stdio_mcp"] = json.loads(mcp.stdout)
        report["temporary_directory_removed"] = True
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            report["subprocess_output"] = (str(exc.stdout or "") + str(exc.stderr or ""))[-2000:]
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
