@echo off
setlocal
set "TOOLS_DIR=%~dp0"
set "UNITY_BRIDGE_CONFIG=%TOOLS_DIR%bridge-project.toml"
set "BRIDGE_VENV=%TOOLS_DIR%..\.unity-mcp-bridge-venv"

if not exist "%BRIDGE_VENV%\Scripts\python.exe" (
  echo Bridge virtual environment was not found: %BRIDGE_VENV%
  exit /b 1
)

"%BRIDGE_VENV%\Scripts\python.exe" -m codex_funplay_bridge.server

