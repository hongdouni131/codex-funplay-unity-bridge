# 部署与配置

## 使用 Release 安装程序

1. 从 GitHub Release 下载 `Codex-Funplay-Bridge-Setup.exe` 和对应 `.sha256` 文件。
2. 校验 SHA256 后运行安装程序。源码开发时，运行仓库根目录的 `start_bridge_setup_wizard.cmd`。
3. 选择 Unity 项目根目录，粘贴 `Funplay > MCP Server` 显示的准确 URL。
4. 点击“验证配置”。它会验证 Unity 项目标识、端口、MCP 初始化与 `tools/list`；失败时不会写入文件。
5. 点击“部署 Bridge”。替换已有 Bridge 管理文件前会请求确认，并创建项目本地虚拟环境。
6. 选择生成 Codex 配置片段，手动粘贴到 Codex 配置，再重新加载 MCP 服务。

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
