@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Project virtual environment was not found: %PYTHON%
  echo Run: py -3.11 -m venv .venv
  echo Then: .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
  exit /b 1
)

"%PYTHON%" -m codex_funplay_bridge.setup_wizard
