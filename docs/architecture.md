# Architecture

The Bridge runs as a stdio MCP server for Codex Desktop. It loads one
project-level TOML configuration per process and makes HTTP JSON-RPC requests
to the Funplay MCP URL configured for that project.

`FunplayBroker` owns JSON-RPC request IDs and normalizes network, HTTP, JSON,
JSON-RPC, and protocol errors into `BridgeError`. The MCP server translates
those errors into serializable tool responses. No diagnostic output is printed
to stdout; this preserves the stdio MCP protocol stream.

Health checks first open a TCP connection to the configured host and port,
then perform `initialize`, `notifications/initialized`, and `tools/list`.
That sequence identifies common configuration and Unity/Funplay availability
failures before a potentially mutating Unity tool is called.

