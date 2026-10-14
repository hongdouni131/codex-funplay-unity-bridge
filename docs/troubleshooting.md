# 故障排除

| 健康检查结果 | 含义 | 处理方式 |
| --- | --- | --- |
| `configuration_error` | TOML 缺失或无效 | 检查项目配置路径和字段。 |
| `port_not_listening` | 无法访问配置的主机/端口 | 启动 Unity 与 Funplay；等待编译或域重载完成。 |
| `timeout` | Funplay 未及时响应 | 检查 Unity Console 和操作状态；只读查询可在恢复后重试，写操作先核实结果。 |
| `http_error` | 端点返回 HTTP 失败 | 从 Funplay MCP Server 窗口重新复制准确 URL。 |
| `invalid_json` | 端点不是 MCP JSON 服务 | 确认 URL 指向 Funplay，而不是其他本地服务。 |
| `protocol_incompatible` | Funplay 选择了不支持的 MCP 协议 | 更新 Bridge 或 Funplay 包。 |
| `jsonrpc_error` | Funplay 拒绝请求 | 检查错误详情和 Unity Console。 |

Unity 重新编译脚本或重新加载域时，服务可能短暂断开。不要假定先前工具调用已经完成；等待恢复后重新执行 `unity_health_check`。

## UI Agent 专用调用

| 错误或状态 | 含义与处理 |
| --- | --- |
| `project_identity_unverified` | 配置缺少绝对根路径；重新部署或补充 `unity_project_root`。 |
| `project_identity_mismatch` | URL 连接的 Unity 项目与配置根路径不同；核对窗口、URL 和配置，不能通过工具参数绕过校验。 |
| `editor_not_ready` | Editor 正在编译、更新或播放；回到就绪 Edit Mode 后重新检查。 |
| `ui_agent_package_unavailable` | 未安装 Package 或 API 不兼容；安装验证版本并检查编译错误。通用桥仍可使用。 |
| `confirmation_required` | 未确认、计划过期、服务重载、输入变化或计划已消费；先排除此前生成已经完成，再重新准备并展示计划。 |
| `execution_status_unknown` | `execute_code` 超时，Unity 可能已执行；先读执行历史、目标 Prefab 和场景，禁止直接重复生成。 |
| `execute_code_unsafe` | Funplay 未提供预期的安全检查布尔参数；核对 Funplay 版本和工具 schema。 |
| `audit_scene_changed` | 审计期间切换了活动场景；结果不合并，稳定场景后重新审计。 |
| `in_progress` / `incomplete` | 审计未完整完成，不能据此声称通过；保留 task 信息，按响应继续查询或检查限制。 |

UI Agent 工具出现在 Codex 的 MCP 工具列表中，不在 Funplay 的 `unity_list_tools` 返回列表里。部署后仍看不到时，重载对应 MCP 服务，再检查 `unity_bridge_info` 的版本、配置来源和项目路径。

`ok=true` 表示 Bridge 成功取得报告，仍需读取 Package 报告的 `status` 和错误列表；它不保证 Spec 合法或 UI 审计通过。字体缺字、输出路径已占用等原因会阻止生成，应根据准备报告修正并重新确认。

## 安装与更新

安装向导需要本机 Python 3.11 和下载 Python 依赖的网络；内嵌 wheel 不包含全部依赖，不能视为离线安装包。升级前记录旧配置，重新部署后重载服务；可用 `--self-check` 验证内嵌资源和临时部署，见 [发布验证](release-validation.md)。
