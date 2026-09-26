# 架构

Bridge 是供 Codex Desktop 使用的 stdio MCP 服务器。每个进程加载一个项目级 TOML 配置，并向该项目的 Funplay MCP URL 发出 HTTP JSON-RPC 请求。

```text
Codex -> stdio MCP -> Bridge -> HTTP JSON-RPC -> Funplay -> Unity Editor
```

`FunplayBroker` 负责 JSON-RPC 请求 ID，并把网络、HTTP、JSON、JSON-RPC 和协议异常统一转换为 `BridgeError`。MCP 服务器再将错误转换为可序列化的工具响应。诊断输出不会写入 stdout，以免破坏 stdio MCP 协议流。

健康检查先连接配置的主机和端口，再按 `initialize`、`notifications/initialized`、`tools/list` 的顺序执行。这能在调用可能修改 Unity 内容的工具前，提前识别配置错误及 Unity/Funplay 暂时不可用的问题。
