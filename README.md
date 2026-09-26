# Codex-Funplay Unity Bridge Template

This project provides a project-scoped Python MCP server that lets Codex
Desktop communicate with a local Funplay MCP for Unity HTTP server. It does
not replace or modify Funplay.

```text
Codex Desktop -> stdio MCP -> Python Bridge -> HTTP JSON-RPC -> Funplay -> Unity Editor
```

## Features

- Deploy a project-local Bridge from a Windows setup wizard.
- Validate a local Funplay URL, port, MCP initialization, and `tools/list`.
- Expose a small stdio MCP surface for Codex: health check, tool discovery,
  tool forwarding, and Bridge information.
- Generate a copyable Codex configuration snippet after deployment without
  editing global MCP configuration files.
- Record redacted JSONL audit events beside the project configuration.

## Scope

Version 0.1 supports one local Windows Unity project at a time. It provides
configuration validation, connectivity diagnostics, MCP initialization,
`tools/list`, `tools/call`, and redacted JSONL audit logging.

It deliberately does not modify Codex, Claude Code, Coplay, Funplay, Unity
assets, or global MCP configuration files.

## Requirements

- Windows
- Python 3.11 available through the Windows `py` launcher
- Unity 2022.3 or later
- [Funplay MCP for Unity](https://github.com/FunplayAI/funplay-unity-mcp)
- Codex Desktop

## Install for development

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

The release-verified runtime versions are recorded in
`requirements-lock.txt`. Use that file when reproducing the tested runtime in
a fresh environment; keep the version ranges in `pyproject.toml` for package
metadata compatibility.

## Configure a Unity project

For a shareable Windows launcher, use
`release/Codex-Funplay-Bridge-Setup.exe`. It is a single executable with the
Bridge wheel and deployment templates embedded, so recipients do not need a
copy of this repository. The recipient still needs Python 3.11 installed via
the Windows `py` launcher because each Unity project receives its own Python
virtual environment. Windows may show SmartScreen warnings until a public
release is code-signed.

Run `start_bridge_setup_wizard.cmd` from this repository to open the local
setup window. Select the Unity project root and paste the exact URL shown by
`Funplay > MCP Server`. The window checks the Unity directory markers, local
URL format, port, MCP initialization, and tool discovery before it enables
deployment. It asks before replacing any Bridge-managed files, then creates
the Unity project's isolated environment and configures the Bridge.

The wizard does not change Unity assets, Funplay, Codex global configuration,
or any other MCP configuration.

### Manual setup

Copy the files under `templates/unity-project/tools` to the Unity project's
`tools` folder. Set `BRIDGE_PACKAGE_PATH` to this repository's local path and
run `initialize_unity_http_stdio_bridge.cmd`; it creates the project's
`.unity-mcp-bridge-venv` and installs the verified runtime dependencies.
Then set the exact URL displayed by `Funplay > MCP Server` in
`bridge-project.toml`; do not reuse a port from a previous project.

```toml
project_name = "ExampleUnityProject"
funplay_url = "http://127.0.0.1:22166/"
timeout_seconds = 10
```

Install this package into that project's `.unity-mcp-bridge-venv`, then launch
the provided `start_unity_http_stdio_bridge.cmd`. The command requires
`UNITY_BRIDGE_CONFIG` to point to the project configuration, or uses a
`bridge-project.toml` in its current working directory.

## Exposed MCP tools

- `unity_bridge_info`: reports the loaded project configuration and version.
- `unity_health_check`: probes the configured port, HTTP MCP initialization,
  protocol version, and available tool count.
- `unity_list_tools`: forwards `tools/list` to Funplay.
- `unity_call_tool`: forwards `tools/call` with validated arguments.

The server writes protocol traffic only to stdout. Audit events go to
`bridge-audit.jsonl` beside the active configuration (or to
`UNITY_BRIDGE_AUDIT_LOG`) and redact common credential field names.

See `docs/setup.md`, `docs/architecture.md`, and `docs/troubleshooting.md` for
the operational details.

## Add the Codex MCP entry

After successful deployment, the setup wizard asks whether to generate a
copyable Codex MCP configuration snippet. Choosing yes opens a dialog with a
copy button; it never writes a global Codex configuration file. The following
terminal command remains available for manual or scripted use:

```powershell
.\.venv\Scripts\codex-funplay-bridge-config.exe `
  --project-name "ExampleUnityProject" `
  --project-root "D:\path\to\ExampleUnityProject"
```

The command validates the Unity project and the Bridge launcher, shows the
project name and path, and asks for confirmation. Only after confirmation does
it print a TOML snippet such as:

```toml
[mcp_servers.unity_bridge_exampleunityproject]
command = "D:\\path\\to\\ExampleUnityProject\\tools\\start_unity_http_stdio_bridge.cmd"
```

Copy the printed snippet manually into the Codex MCP configuration. The tool
never edits Codex, Claude Code, Coplay, or any other global MCP configuration.

## Verification

Run the automated test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The `0.1.0` release has 28 automated tests covering configuration validation,
HTTP and JSON-RPC failures, health checks, deployment safeguards, audit-log
redaction, and Codex configuration snippet generation.

For a real Unity project, verify in this order:

1. `unity_bridge_info`
2. `unity_health_check`
3. `unity_list_tools`
4. One known read-only Funplay tool

## Limitations

- Version `0.1.0` supports one local Windows Unity project per Bridge process.
- The setup application does not modify any global Codex, Claude Code, or
  Coplay configuration file.
- The setup executable is not code-signed. Windows SmartScreen may display a
  warning for a downloaded release binary.

See `docs/release-v0.1.0.md` for the release notes and checksum.
