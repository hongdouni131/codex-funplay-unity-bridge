@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PACKAGE_DIR=%ROOT%pyinstaller-build\package"

if not exist "%PYTHON%" (
  echo Project virtual environment was not found: %PYTHON%
  echo Run: py -3.11 -m venv .venv
  echo Then: .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
  exit /b 1
)

"%PYTHON%" -m pip wheel --no-deps --wheel-dir "%PACKAGE_DIR%" "%ROOT%."
if errorlevel 1 exit /b 1

"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Codex-Funplay-Bridge-Setup" ^
  --paths "%ROOT%src" ^
  --add-data "%ROOT%templates;templates" ^
  --add-data "%PACKAGE_DIR%\codex_funplay_bridge-0.1.0-py3-none-any.whl;package" ^
  --distpath "%ROOT%release" ^
  --workpath "%ROOT%pyinstaller-build\work" ^
  --specpath "%ROOT%pyinstaller-build\spec" ^
  "%ROOT%scripts\setup_wizard_entry.py"
