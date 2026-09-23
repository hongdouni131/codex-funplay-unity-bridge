@echo off
setlocal
set "TOOLS_DIR=%~dp0"
set "PROJECT_ROOT=%TOOLS_DIR%.."
set "BRIDGE_VENV=%PROJECT_ROOT%\.unity-mcp-bridge-venv"

if "%BRIDGE_PACKAGE_PATH%"=="" (
  echo Set BRIDGE_PACKAGE_PATH to this Bridge repository before initialization.
  echo Example: set "BRIDGE_PACKAGE_PATH=D:\path\to\codex-funplay-bridge-template"
  exit /b 1
)

py -3.11 -m venv "%BRIDGE_VENV%"
if errorlevel 1 exit /b 1

"%BRIDGE_VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%BRIDGE_VENV%\Scripts\python.exe" -m pip install -r "%TOOLS_DIR%requirements-unity-http-bridge.txt"
if errorlevel 1 exit /b 1

"%BRIDGE_VENV%\Scripts\python.exe" -m pip install "%BRIDGE_PACKAGE_PATH%"
