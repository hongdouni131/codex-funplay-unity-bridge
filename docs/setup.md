# 部署与配置

## 使用 Release 安装程序

1. 从 GitHub Release 下载 `Codex-Funplay-Bridge-Setup.exe` 和对应 `.sha256` 文件。
2. 校验 SHA256 后运行安装程序。源码开发时，运行仓库根目录的 `start_bridge_setup_wizard.cmd`。
3. 选择 Unity 项目根目录，粘贴 `Funplay > MCP Server` 显示的准确 URL。
4. 点击“验证配置”。它会验证 Unity 项目标识、端口、MCP 初始化与 `tools/list`；失败时不会写入文件。
5. 点击“部署 Bridge”。替换已有 Bridge 管理文件前会请求确认，并创建项目本地虚拟环境。
6. 选择生成 Codex 配置片段，手动粘贴到 Codex 配置，再重新加载 MCP 服务。

新版本部署向导会把选定 Unity 项目的绝对根路径写入 `tools/bridge-project.toml`，供 UI Agent 专用工具核实连接目标。可选的“Bridge 名称”只用于标识这个 MCP 连接，不会改变 Unity 项目目录名；留空时沿用项目目录名。自定义名称会写入 `bridge_name`，并用于生成 Codex MCP 配置中的服务键。旧配置仍能使用通用 Bridge 工具；缺少项目根路径时，UI Agent 专用工具会拒绝执行，需重新部署或手动添加 `unity_project_root = "D:\\path\\to\\UnityProject"`。

Bridge 名称不会重命名 Unity 项目内的文件。`tools/bridge-project.toml`、`tools/start_unity_http_stdio_bridge.cmd`、`tools/initialize_unity_http_stdio_bridge.cmd`、`tools/requirements-unity-http-bridge.txt` 和项目根目录下的 `.unity-mcp-bridge-venv` 均保持固定名称。

向导中的“默认超时秒数”适用于健康检查、初始化、工具发现及普通 Funplay 工具调用。`execute_code` 使用单独的 `execute_code_timeout_seconds`，默认 60 秒，大于 0 且不超过 300 秒。超时只表示 Bridge 没有在时限内收到回复，不表示 Unity 已停止执行；写操作结果未知时，先检查执行历史、目标资源和场景状态，不要直接重试。

## 从 v0.1.0 升级

1. 记录原 `tools/bridge-project.toml` 中的 URL、默认超时和 Codex 服务键，备份配置。
2. 运行 v0.2.0 安装程序，选择同一项目，填入原有 URL 和所需超时；Bridge 名称留空可沿用目录名。
3. 验证成功后部署，确认替换已有 Bridge 管理文件。向导会重新写入配置，不自动保留手动添加的字段；运行日志不在替换列表中。
4. 保持名称不变时可继续使用原 Codex 启动命令；改名时替换旧 MCP 条目。重新加载服务后调用 `unity_bridge_info`，核实版本为 `0.2.0`，再运行健康检查。

旧配置的 `project_name`、`funplay_url` 和 `timeout_seconds` 仍有效；未配置的独立超时默认 60 秒。缺少 `unity_project_root` 只会阻止 UI Agent 专用调用。升级不会安装 Unity Package。

## UI Agent 首次使用

1. 单独取得 UI Agent Tools Package 源码，在 Package Manager 使用 **Add package from disk...** 选择 `com.hongdouni.ui-agent-tools/package.json`。当前验证版本为 Package `0.1.0`、Unity `2022.3.62f3c1`。
2. 等待 Unity 编译结束，确认场景处于 Edit Mode；准备已有 TMP Font Asset 的 Assets 相对路径，检查其字符覆盖范围。
3. 在 Codex 的 MCP 工具列表确认五个 `ui_agent_*` 工具已出现。健康检查只验证 Funplay 通道，不验证 Package 是否安装或具备所需 API。
4. 校验 Spec，调用准备工具，完整展示计划并等待用户明确确认，然后生成、读回并审计。

| 工具 | 参数 |
| --- | --- |
| `ui_agent_validate_spec` | `spec_json: string`（JSON 对象，最多 16384 字符） |
| `ui_agent_prepare_main_menu` | `spec_json`、`font_asset_path: string` |
| `ui_agent_generate_main_menu` | 同一 `spec_json`、`font_asset_path`、`plan_fingerprint: string`、`user_confirmed: boolean` |
| `ui_agent_inspect_hierarchy` | `source: active_scene`；或 `source: prefab` 和 `asset_path: Assets/...prefab` |
| `ui_agent_audit_ui` | 无参数，仅活动场景；返回 `in_progress` 时再次调用以查询同一审计。 |

准备计划只保存在当前 Bridge 进程，最多 32 项，30 分钟后过期；重载服务后需要重新准备和确认。生成调用前消费计划，结果未知也不能重放。输入发生变化时重新准备计划。Prefab 和场景实例都会被创建，保存场景按使用者约定执行；Bridge 不会在生成后自动清理演示资源。

## 手动部署

1. 在 Unity 打开 `Funplay > MCP Server` 并启动服务。
2. 将显示的 URL 写入 `tools/bridge-project.toml`。
3. 将 `templates/unity-project/tools` 复制到 Unity 项目的 `tools` 目录，设置 `BRIDGE_PACKAGE_PATH` 为 Bridge 仓库路径，运行 `tools/initialize_unity_http_stdio_bridge.cmd`。
4. 在 Codex MCP 配置中，将 `tools/start_unity_http_stdio_bridge.cmd` 作为 command。

等效的虚拟环境命令：

```powershell
py -3.11 -m venv .unity-mcp-bridge-venv
.\.unity-mcp-bridge-venv\Scripts\python.exe -m pip install --upgrade pip
.\.unity-mcp-bridge-venv\Scripts\python.exe -m pip install "D:\path\to\codex-funplay-bridge-template"
```

Bridge 不会自动编辑 `C:\Users\<user>\.codex\config.toml`、Claude Code 配置或 Coplay 配置。

## 复现发布依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

当前锁定版本为 `mcp==1.30.0` 与 `httpx==0.28.1`。
