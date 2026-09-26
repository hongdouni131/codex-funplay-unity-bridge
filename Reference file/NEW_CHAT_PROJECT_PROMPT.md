# Codex 新对话启动提示词

请将下面内容完整复制到新的 Codex 对话中，作为本项目的第一条消息。

```text
我正在开发一个作品集项目：Codex-Funplay Unity Bridge Template。

项目目标：
构建一个可复用的 Codex Desktop 到 Funplay MCP for Unity 的连接模板，
让新的 Unity 项目可以稳定、可诊断地接入 Codex。项目不重写 Funplay，
也不修改 Funplay 的核心协议，而是提供项目级配置、健康检查、stdio-to-HTTP
转发、错误诊断、日志和测试。

项目工作目录：
<Bridge 项目目录>

已有参考文档：
<Bridge 项目目录>\Reference file\Unity_Agent_Development_Roadmap.md

请先读取并理解这份路线文档，再检查当前项目目录和开发环境。

技术范围：
- Windows
- Python 3.11
- Python MCP SDK
- Codex Desktop
- Funplay MCP for Unity 的本机 HTTP 服务
- stdio MCP 到 HTTP JSON-RPC 的适配
- 单个 Unity 项目优先

第一版明确不做：
- 不修改 Funplay 源码
- 不修改 Claude Code 配置
- 不修改 Coplay / MCP for Unity 配置
- 不连接远程 Unity
- 不实现多项目自动路由
- 不开发 UI 可用性检查 Agent
- 不开发敌人配置 Agent
- 不提交任何 API Key、Token、个人路径、日志、虚拟环境或 Unity Library 文件

推荐架构：

Codex Desktop
    ↓ stdio MCP
Python Bridge
    ↓ HTTP JSON-RPC
Funplay MCP for Unity
    ↓
Unity Editor

第一版需要提供的 Bridge 工具：
1. unity_bridge_info
   返回 Bridge 版本、项目名、目标 Funplay URL 和配置来源。
2. unity_health_check
   检查配置、端口、HTTP、MCP initialize、协议版本和工具数量。
3. unity_list_tools
   转发 Funplay 的 tools/list。
4. unity_call_tool
   转发 Funplay 的 tools/call，并保留结构化错误。

建议项目目录：

codex-funplay-bridge-template/
  README.md
  LICENSE
  pyproject.toml
  .gitignore
  src/
    codex_funplay_bridge/
      __init__.py
      server.py
      broker.py
      health.py
      config.py
      logging.py
  tests/
    test_broker.py
    test_health.py
  templates/
    unity-project/
  docs/
    requirements.md
    architecture.md
    setup.md
    troubleshooting.md
  examples/
    bridge-project.example.toml

项目级配置示例：

project_name = "ExampleUnityProject"
funplay_url = "http://127.0.0.1:22166/"
timeout_seconds = 10

开发顺序：

阶段 1：只读检查
- 检查工作目录、路线文档、Python、Git 和可用依赖。
- 检查是否已有文件或用户修改。
- 不要删除或覆盖已有文件。

阶段 2：提出实现计划
- 列出准备创建和修改的文件。
- 说明每个文件的作用。
- 说明核心函数、配置字段和测试方法。
- 说明人工需要确认的内容。
- 暂时不要修改文件，等待我确认。

阶段 3：创建最小项目骨架
- 创建 Python 包、测试目录、文档目录和示例配置。
- 创建 pyproject.toml、README.md、LICENSE 和 .gitignore。
- 不创建 Unity 项目，不修改任何已有 Unity 项目。

阶段 4：实现 HTTP Broker 客户端
- 实现 initialize、tools/list、tools/call。
- 支持超时、连接拒绝、HTTP 错误、无效 JSON 和 JSON-RPC 错误。
- 返回统一、可读取的结构化结果。

阶段 5：实现 stdio MCP Server
- 使用 Python MCP SDK 的公开装饰器 API。
- 暴露 unity_bridge_info、unity_health_check、unity_list_tools、unity_call_tool。
- 日志写 stderr 或 JSONL 文件，绝不能污染 stdio MCP 的协议输出。

阶段 6：编写自动化测试
- 先使用假的 HTTP MCP 服务测试，不依赖 Unity。
- 覆盖成功响应、超时、端口拒绝、404、无效 JSON 和 JSON-RPC error。
- 测试工具参数校验和错误信息。

阶段 7：连接真实 Funplay
- 由我打开 Unity 并启动 Funplay > MCP Server。
- 使用 Unity 窗口显示的真实 URL，不猜测端口。
- 先执行 tools/list 和只读工具调用。
- 不先创建、删除或覆盖 Unity 资源。

阶段 8：Codex 验证
- 通过生成的启动命令启动 Bridge。
- 按 unity_bridge_info、unity_health_check、unity_list_tools、只读 Unity 工具的顺序验证。
- 记录实际项目、URL、工具数量和响应时间。
- 如果 Unity 编译或域重载导致断连，等待服务恢复后重新验证。

阶段 9：文档和发布准备
- 完善 README 安装、配置、运行和排错说明。
- 添加 architecture.md、setup.md 和 troubleshooting.md。
- 添加成功截图或终端输出示例。
- 检查 Git 状态，确认没有密钥、虚拟环境、日志、个人配置和 Unity 生成目录。

协作与安全规则：
- 所有回复使用中文，先说明结论。
- 每次修改前先读取相关文件，并列出修改文件、修改目的和方法。
- 第一次检查后不要直接写代码，先给我实现计划并等待确认。
- 不要擅自修改 C:\Users\<用户名>\.codex\config.toml。
- 不要修改 C:\Users\<用户名>\.mcp.json、C:\Users\<用户名>\.claude.json 或 .claude 目录。
- 不要连接或修改 Claude Code 使用的 MCP for Unity 端口，例如 8088。
- 不要把 Funplay 端口写死为旧项目端口；必须使用当前 Unity 窗口显示的 URL。
- 不要提交环境变量、API Key、Token、真实用户路径或运行日志。
- 代码修改后运行测试，并说明测试结果。
- 如果无法运行某项测试，明确说明原因，不要声称已验证。

错误诊断要求：
健康检查必须区分以下情况：
- 配置格式错误
- URL 无效
- 端口未监听
- Unity/Funplay 未启动
- HTTP 返回错误
- MCP initialize 失败
- 协议版本不兼容
- tools/list 失败
- 连接到了错误的 Unity 项目
- Unity 正在编译或域重载

GitHub 发布目标：
- 仓库名建议为 codex-funplay-bridge-template。
- 使用清晰的小步提交。
- 首次公开发布前检查 README、许可证、.gitignore、测试和安全信息。
- 不要替我创建远程 GitHub 仓库，除非我明确要求。
- 可以准备本地 Git 提交和推送命令，但执行推送前先让我确认。

现在请执行第一步：
1. 读取 <Bridge 项目目录>\Reference file\Unity_Agent_Development_Roadmap.md。
2. 检查 <Bridge 项目目录> 当前目录状态。
3. 检查 Python 3.11、Git 和基础依赖是否可用。
4. 检查当前是否已经是 Git 仓库。
5. 输出检查结果和第一阶段实现计划。

在我确认计划前，不要创建、删除或修改任何项目文件。
```

## 使用说明

新对话启动后，先让 Codex 完成“只读检查”和“实现计划”。

确认计划时，重点确认：

1. 仓库是否采用单独的 Python 项目，而不是放进 Unity 游戏目录。
2. 第一版是否只支持单个 Unity 项目。
3. 是否保留 `unity_bridge_info`、`unity_health_check`、`unity_list_tools`、`unity_call_tool` 四个工具。
4. 是否先使用模拟 HTTP 服务测试，再连接真实 Unity。
5. 是否同意暂不修改 Codex 全局配置，而是先生成配置建议。

建议的第一条确认消息：

```text
计划已确认。请先创建最小项目骨架和测试配置，不要连接真实 Unity，完成后列出修改文件和测试结果。
```
