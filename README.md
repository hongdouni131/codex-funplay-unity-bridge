# Codex-Funplay Unity Bridge 模板

本项目提供按 Unity 项目隔离的 Python MCP 服务，使 Codex Desktop 能通过 Funplay MCP for Unity 的 HTTP 服务调用 Unity 工具。它不会替换或修改 Funplay。当前版本为 **0.3.0**，新增完整UI Agent v2工具链；安装与升级见 [0.3.0说明](docs/release-v0.3.0.md)。

```text
Codex Desktop -> stdio MCP -> Python Bridge -> HTTP JSON-RPC -> Funplay -> Unity Editor
```

## 功能

- Windows 安装向导：为指定 Unity 项目部署 Bridge。
- 校验 Funplay URL、端口、MCP 初始化和 `tools/list`。
- 向 Codex 提供 `unity_bridge_info`、`unity_health_check`、`unity_list_tools`、`unity_call_tool`。
- 部署后生成可复制的 Codex TOML 配置片段，不自动修改全局配置。
- 在项目配置旁记录已脱敏的 JSONL 审计日志。
- 可选 [UI Agent Package](https://github.com/hongdouni131/ui-agent-tools) 集成：提供v1/v2的Spec校验、计划准备、确认后生成、层级读取及审计等18个具名工具。通用桥不要求安装UI Agent Package。
- 自定义 Bridge 名称，区分多个项目连接；UI Agent 操作按配置的 Unity 根路径核验项目身份。
- `execute_code` 独立超时默认 60 秒；执行结果未知时不自动重试。
- 0.3.0安装器包含完整22个自有工具（4通用+5 v1+13 v2），支持素材导入检查/精确查询、候选页、布局测量、选择合并、v2校验/计划/生成/审计、结果诊断与受限Spec修订。候选页提供中文用途提示、推荐与风险理由、并排预览、Spec映射和写入范围；提交后仍需Validate、Prepare、完整计划和开发者授权。槽位骨架见[候选页模板](templates/ui-agent-sprite-selection.example.json)，完整说明见[工具文档](docs/ui-agent-composition-tools.md)。旧公开0.2.0安装器只有4通用+5 v1工具，不含v2扩展。

## 环境要求

- Windows
- 可通过 Windows `py` 启动器使用 Python 3.11
- Unity 2022.3（UI Agent配对实测2022.3.62f3c1；其他版本未作本次承诺）
- [Funplay MCP for Unity](https://github.com/FunplayAI/funplay-unity-mcp)
- Codex Desktop

## 用户安装与运行

普通用户不必下载本仓库全部源码。请在 GitHub 的 **Releases** 页面下载两个附件：

- `Codex-Funplay-Bridge-Setup.exe`：安装向导。
- `Codex-Funplay-Bridge-Setup.exe.sha256`：安装程序的完整性校验值。

下载后先在同一文件夹校验安装程序：

```powershell
Get-FileHash .\Codex-Funplay-Bridge-Setup.exe -Algorithm SHA256
Get-Content .\Codex-Funplay-Bridge-Setup.exe.sha256
```

两者显示的 SHA256 应一致。之后双击运行 `.exe`，选择 Unity 项目根目录，填写 Unity 中 `Funplay > MCP Server` 显示的准确 URL，执行“验证配置”和“部署 Bridge”。部署成功后，选择生成 Codex 配置片段，将显示的 TOML 手动复制到 Codex MCP 配置，重新加载 MCP 服务，并依次调用 `unity_health_check`、`unity_list_tools` 验证。

安装程序内含 Bridge wheel 与部署模板，因此用户无需先下载源码；但目标电脑必须有 Python 3.11，供每个 Unity 项目创建独立的 `.unity-mcp-bridge-venv`。

## 开发环境安装

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

发布验证过的依赖版本记录在 `requirements-lock.txt`。需要复现测试环境时，先执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 从源码部署

在仓库根目录运行 `start_bridge_setup_wizard.cmd`。选择 Unity 项目根目录，并粘贴 `Funplay > MCP Server` 中显示的准确 URL。向导先检查 Unity 项目标识、URL、端口、MCP 初始化和工具发现；校验通过后才能部署。替换已有 Bridge 管理的文件前会询问确认。

向导不会修改 Unity 资源、Funplay、Codex 全局配置、Claude Code、Coplay 或其他 MCP 配置。

## Codex MCP 条目

部署成功后，向导可显示可复制的配置内容。也可以手动生成：

```powershell
.\.venv\Scripts\codex-funplay-bridge-config.exe `
  --project-name "ExampleUnityProject" `
  --bridge-name "Example UI Sandbox" `
  --project-root "D:\path\to\ExampleUnityProject"
```

确认项目名和路径后，它会输出类似：

```toml
[mcp_servers.unity_bridge_example_ui_sandbox]
command = "D:\\path\\to\\ExampleUnityProject\\tools\\start_unity_http_stdio_bridge.cmd"
```

请手动复制该片段至 Codex MCP 配置。工具不会自动编辑任何全局配置文件。

向导新增可选的“Bridge 名称”及 MCP 标识预览。留空时使用项目目录名，填写时会在项目配置中保存 `bridge_name`，并以该名称生成 MCP 服务键；配置文件和启动脚本的文件名不变。名称支持中文，生成的服务键使用 ASCII 标识和稳定摘要。请在 Codex 中使用不同服务键区分各项目；向导不会读取全局配置来检查重名。更名已有服务时，请替换旧 MCP 条目并重新加载，避免同时保留两个指向同一项目的连接。

## 验证顺序

1. `unity_bridge_info`
2. `unity_health_check`
3. `unity_list_tools`
4. 一个已知的只读 Funplay 工具

0.3.0的验证包括完整pytest回归、EXE内嵌wheel检查、临时项目部署、pip check及安装后精确22工具发现；实际本轮结果以[发布验证](docs/release-validation.md)为准。`unity_list_tools`列出Funplay工具，MCP客户端的`tools/list`才列出Bridge自有工具，两者数量不同。

历史源码检查点：2026-10-21为105/105；布局/合并/诊断/修订完成后为160/160。它们不自动等于新EXE验收。运行中的MCP进程必须重新加载才使用部署后的代码。

候选页七项体验扩展当时为117/117、定向11/11，是历史结果。HTML预览是选择辅助，最终尺寸/引用以Unity测量和读回为准。

## 使用 UI Agent（可选）

在 Unity 2022.3 项目中，先通过 Package Manager 的 **Add package from disk...** 选择 UI Agent Tools 源码目录中的 `package.json`，等待编译结束。该 Package 单独获取，Bridge 安装程序不会携带或安装它。当前实测 Package 为 `com.hongdouni.ui-agent-tools` `0.1.0`。

连接 Bridge 后，Codex 的 MCP 工具列表会显示以下五个v1工具，另有下方13个v2工具；`unity_list_tools`列出的是Funplay原生工具，不能用于判断这些Bridge专用工具是否注册。

| 工具 | 用途 |
| --- | --- |
| `ui_agent_validate_spec` | 只读校验 JSON Spec。 |
| `ui_agent_prepare_main_menu` | 只读准备完整创建计划。 |
| `ui_agent_generate_main_menu` | 按明确确认的计划创建 Prefab 和场景实例。 |
| `ui_agent_inspect_hierarchy` | 读取活动场景或 Prefab 层级。 |
| `ui_agent_audit_ui` | 合并 UI Agent 与 Funplay 的活动场景审计。 |

使用者可以对 Codex 说：“用 UI Agent 准备一个深色主菜单，先展示计划给我确认。”Codex 整理 Spec 和 TMP 字体路径，先校验与准备，再展示计划；取得用户明确确认后传入同一 Spec、字体和指纹生成，最后读回及审计。计划指纹能发现计划变化，不能证明批准来自真人。按钮暂不绑定游戏逻辑；文本必须由所选字体支持。

v2工具：`ui_agent_find_sprites`、`ui_agent_audit_sprite_imports`、`ui_agent_create_sprite_selection`、`ui_agent_get_sprite_selection`、`ui_agent_cancel_sprite_selection`、`ui_agent_measure_composition_layout`、`ui_agent_merge_sprite_selection`、`ui_agent_validate_composition`、`ui_agent_prepare_composition`、`ui_agent_generate_composition`、`ui_agent_audit_composition`、`ui_agent_diagnose_composition`、`ui_agent_revise_composition`。

未安装Package时，注册仍存在，依赖Unity Package API的调用会返回不可用；四个通用工具仍可使用。详细参数、错误处理和升级步骤见[安装说明](docs/setup.md)、[故障排除](docs/troubleshooting.md)和[工具契约](docs/ui-agent-tools-design.md)。

## 构建与版本

当前源码版本为 `0.3.0`，本轮准备安装器，不自动发布。版本变化见[变更日志](CHANGELOG.md)，候选说明见[v0.3.0](docs/release-v0.3.0.md)。运行`build_setup_exe.cmd`构建对应版本wheel、EXE和SHA256；安装包自检方法见[发布验证](docs/release-validation.md)。旧0.2.0历史附件不以新代码重新发布或覆盖。

## 限制

- 每个 Bridge 进程只支持一个本机 Windows Unity 项目。
- 多个项目可各自部署 Bridge；各连接需使用对应的 Funplay URL 和不同 MCP 服务键。
- UI Agent 合并审计第一版只支持活动场景；支持 Prefab 层级读取，但不提供 Prefab 合并审计。
- 安装程序未代码签名，Windows SmartScreen 可能提示警告；请校验 SHA256 并审阅源码。
- 详细操作、架构和问题处理分别见 `docs/setup.md`、`docs/architecture.md`、`docs/troubleshooting.md`。
