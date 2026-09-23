# Troubleshooting

| Health result | Meaning | Action |
| --- | --- | --- |
| `configuration_error` | TOML is missing or invalid | Check the project configuration path and fields. |
| `port_not_listening` | The configured host/port cannot be reached | Start Unity and Funplay; wait for compilation or domain reload to finish. |
| `timeout` | Funplay did not answer in time | Check the Unity Console and retry after the editor is responsive. |
| `http_error` | The endpoint returned an HTTP failure | Copy the precise URL from the Funplay MCP Server window. |
| `invalid_json` | The endpoint is not an MCP JSON service | Verify that the URL belongs to Funplay, not another local server. |
| `protocol_incompatible` | Funplay selected an unsupported MCP protocol | Update the Bridge or the Funplay package. |
| `jsonrpc_error` | Funplay rejected the request | Inspect error details and the Unity Console. |

When Unity recompiles scripts or reloads its domain, the service can briefly
disconnect. Do not assume a prior tool call completed; wait for recovery and
use `unity_health_check` again.

