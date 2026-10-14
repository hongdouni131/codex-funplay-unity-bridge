"""Build the installer from this release's wheel and write its SHA256."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    package_dir = root / "pyinstaller-build" / "package" / version
    package_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(package_dir), str(root)],
        cwd=root, check=True,
    )
    wheel = package_dir / f"codex_funplay_bridge-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise RuntimeError(f"Expected release wheel was not built: {wheel}")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "Codex-Funplay-Bridge-Setup", "--paths", str(root / "src"),
        "--add-data", f"{root / 'templates'};templates", "--add-data", f"{wheel};package",
        "--distpath", str(root / "release"), "--workpath", str(root / "pyinstaller-build" / "work"),
        "--specpath", str(root / "pyinstaller-build" / "spec"), str(root / "scripts" / "setup_wizard_entry.py"),
    ], cwd=root, check=True)
    executable = root / "release" / "Codex-Funplay-Bridge-Setup.exe"
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    executable.with_suffix(".exe.sha256").write_text(f"{digest}  {executable.name}\n", encoding="ascii")
    print(f"Built {version}: {executable}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
