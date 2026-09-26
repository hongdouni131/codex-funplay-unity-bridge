# 故障排除

| 健康检查结果 | 含义 | 处理方式 |
| --- | --- | --- |
| `configuration_error` | TOML 缺失或无效 | 检查项目配置路径和字段。 |
| `port_not_listening` | 无法访问配置的主机/端口 | 启动 Unity 与 Funplay；等待编译或域重载完成。 |
| `timeout` | Funplay 未及时响应 | 检查 Unity Console，等待编辑器恢复响应后重试。 |
| `http_error` | 端点返回 HTTP 失败 | 从 Funplay MCP Server 窗口重新复制准确 URL。 |
| `invalid_json` | 端点不是 MCP JSON 服务 | 确认 URL 指向 Funplay，而不是其他本地服务。 |
| `protocol_incompatible` | Funplay 选择了不支持的 MCP 协议 | 更新 Bridge 或 Funplay 包。 |
| `jsonrpc_error` | Funplay 拒绝请求 | 检查错误详情和 Unity Console。 |

Unity 重新编译脚本或重新加载域时，服务可能短暂断开。不要假定先前工具调用已经完成；等待恢复后重新执行 `unity_health_check`。
