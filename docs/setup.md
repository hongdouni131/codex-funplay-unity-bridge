# Setup

1. Run `release/Codex-Funplay-Bridge-Setup.exe`. For source development, use
   `start_bridge_setup_wizard.cmd` at the Bridge repository root instead.
2. Select the Unity project root and paste the exact URL displayed by
   `Funplay > MCP Server`.
3. Select `Validate configuration`. It checks that the directory is a Unity
   project and that Funplay accepts MCP initialization and `tools/list`.
   No files are written if validation fails.
4. Select `Deploy Bridge`. The wizard requires confirmation before replacing
   an existing Bridge-managed file, creates the project-local virtual
   environment, installs the package, and runs a follow-up health check.

### Manual setup

1. In the Unity project, open `Funplay > MCP Server` and start its service.
2. Copy the exact URL displayed there into `tools/bridge-project.toml`.
3. Copy the `tools` directory from `templates/unity-project` into the Unity
   project. Set `BRIDGE_PACKAGE_PATH` to this repository's local directory,
   then run `tools/initialize_unity_http_stdio_bridge.cmd`. It creates the
   isolated `.unity-mcp-bridge-venv` and installs the Bridge package.

   The equivalent manual commands are:

```powershell
py -3.11 -m venv .unity-mcp-bridge-venv
.\.unity-mcp-bridge-venv\Scripts\python.exe -m pip install --upgrade pip
.\.unity-mcp-bridge-venv\Scripts\python.exe -m pip install "D:\path\to\codex-funplay-bridge-template"
```

4. Use `tools/start_unity_http_stdio_bridge.cmd` as the stdio command when
configuring the project-specific Codex MCP connection. This repository does
not edit any Codex configuration automatically.
5. Validate in this order: `unity_bridge_info`, `unity_health_check`,
   `unity_list_tools`, then one known read-only Unity tool.

### Generate the Codex entry after deployment

The Bridge can generate a configuration snippet without editing Codex:

```powershell
.\.venv\Scripts\codex-funplay-bridge-config.exe `
  --project-name "ExampleUnityProject" `
  --project-root "D:\path\to\UnityProject"
```

It verifies the project markers and
`tools\start_unity_http_stdio_bridge.cmd`, displays the project name and path,
and asks for confirmation. Only after the user confirms does it print the TOML
entry. Copy that entry manually into the desired Codex MCP configuration.

The command intentionally never edits `C:\Users\<user>\.codex\config.toml`,
Claude Code configuration, or Coplay configuration.

The Bridge is intended to be installed as a package. Do not copy individual
source files into a Unity project.

### Reproducing the verified dependency set

For a development environment that matches the release test run, install the
versions recorded in the repository lock file before installing the editable
package:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The lock file currently records `mcp==1.30.0` and `httpx==0.28.1`.
