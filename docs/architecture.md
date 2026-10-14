# 架构

Bridge 是供 Codex Desktop 使用的 stdio MCP 服务器。每个进程加载一个项目级 TOML 配置，并向该项目的 Funplay MCP URL 发出 HTTP JSON-RPC 请求。

```text
Codex -> stdio MCP -> Bridge -> HTTP JSON-RPC -> Funplay -> Unity Editor
```

`FunplayBroker` 负责 JSON-RPC 请求 ID，并把网络、HTTP、JSON、JSON-RPC 和协议异常统一转换为 `BridgeError`。MCP 服务器再将错误转换为可序列化的工具响应。诊断输出不会写入 stdout，以免破坏 stdio MCP 协议流。

网络等待时间由项目配置中的 `timeout_seconds` 控制，默认 10 秒。`execute_code` 调用单独使用 `execute_code_timeout_seconds`，默认 60 秒，上限 300 秒。若该调用超时，Bridge 返回 `execution_status_unknown`，提醒调用方检查 Funplay 执行历史；Bridge 不会自动重试。

UI Agent 专用调用使用项目配置中的 `unity_project_root`。固定的 `IFunplayCommand` 模板在 Unity 主线程内先核对 `Application.dataPath` 推导出的项目根路径及编译、更新、播放状态，全部通过后才调用 Package API。外部输入只能作为经过 C# 字符串编码的数据进入模板；Bridge 要求 Funplay `execute_code` schema 提供 `safety_checks` 布尔参数，并在每次调用中显式启用。缺失项目根路径、项目不符或 Editor 未就绪时，不进入 Package 操作。

健康检查先连接配置的主机和端口，再按 `initialize`、`notifications/initialized`、`tools/list` 的顺序执行。这能在调用可能修改 Unity 内容的工具前，提前识别配置错误及 Unity/Funplay 暂时不可用的问题。

## 可选 UI Agent 通道

MCP 服务器同时注册四个通用 Bridge 工具与五个 UI Agent 具名工具。通用工具继续转发 Funplay；具名工具把操作映射到已安装的 Unity Editor Package API。UI 规则、布局和资源生成仍由 Package 实现，Python 不复制这些规则。Package 未安装时专用调用失败，不影响通用工具。

`UiAgentTools` 在进程内缓存最多 32 份准备计划，30 分钟过期。生成时检查确认字段、原始 Spec、字体路径、项目根路径与指纹，并在执行前消费计划；Package 再准备、核对指纹和输出路径。指纹是计划一致性检查，真人确认由调用方对话流程负责。

活动场景审计先收集 Package 报告和根对象 ID，再启动 Funplay 只读审计，查询任务并收齐 finding 分页；合并前复核活动场景路径。`incomplete` 和分页限制会保留，不把空结果当作完整通过。第一版不提供 Prefab 合并审计。

UI Agent 专用日志只记录工具、状态等摘要，不记录 Spec 文案或固定模板的 C# 代码。日志是调用诊断，不能作为真人批准凭证。

安装向导的 EXE 内嵌对应版本 wheel 与部署模板，目标项目独立 venv 安装 wheel 和运行依赖。构建脚本读取 `pyproject.toml` 版本，隔离不同版本 wheel，只把当次 wheel 放入 EXE；安装包自检用临时目录运行向导组件、实际部署、MCP 握手与工具发现。
