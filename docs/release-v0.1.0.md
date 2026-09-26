# Codex-Funplay Unity Bridge Template v0.1.0

## Summary

This is the first usable release of a project-scoped stdio-to-HTTP Bridge for
connecting Codex Desktop to a local Funplay MCP for Unity server.

## Included

- Windows setup wizard for validation and project-local deployment.
- Local URL, port, MCP initialization, protocol, and tool-discovery checks.
- `unity_bridge_info`, `unity_health_check`, `unity_list_tools`, and
  `unity_call_tool` stdio MCP tools.
- A post-deployment dialog that generates a copyable Codex MCP configuration
  snippet without editing global configuration files.
- Project-local Python virtual environment provisioning.
- Redacted JSONL audit logging.
- Locked, release-verified runtime dependencies:
  `mcp==1.30.0` and `httpx==0.28.1`.
- 28 automated tests.

## Requirements

- Windows
- Python 3.11 available through `py -3.11`
- Unity 2022.3 or later with Funplay MCP for Unity installed and running
- Codex Desktop

## Install

1. In Unity, start `Funplay > MCP Server` and copy the exact local URL shown.
2. Run `Codex-Funplay-Bridge-Setup.exe`.
3. Select the Unity project root, paste the Funplay URL, validate, and deploy.
4. When prompted, choose whether to generate a copyable Codex MCP entry.
5. Paste the displayed entry into the intended Codex configuration and reload
   Codex MCP services.
6. Run `unity_health_check` and `unity_list_tools` before any write operation.

## Verification

The release binary SHA256 is recorded in
`release/Codex-Funplay-Bridge-Setup.exe.sha256`.

On Windows, verify a downloaded copy with:

```powershell
Get-FileHash .\Codex-Funplay-Bridge-Setup.exe -Algorithm SHA256
```

## Limitations

- Supports one local Unity project per Bridge process.
- Does not modify Funplay, Unity assets, Codex global configuration, Claude
  Code configuration, or Coplay configuration.
- The executable is not code-signed. Windows SmartScreen may warn on first
  download; verify the checksum and review the source before proceeding.
