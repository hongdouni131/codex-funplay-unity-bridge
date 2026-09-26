# Codex-Funplay Unity Bridge 模板

本项目提供按 Unity 项目隔离的 Python MCP 服务，使 Codex Desktop 能通过 Funplay MCP for Unity 的 HTTP 服务调用 Unity 工具。它不会替换或修改 Funplay。

```text
Codex Desktop -> stdio MCP -> Python Bridge -> HTTP JSON-RPC -> Funplay -> Unity Editor
```

## 功能

- Windows 安装向导：为指定 Unity 项目部署 Bridge。
- 校验 Funplay URL、端口、MCP 初始化和 `tools/list`。
- 向 Codex 提供 `unity_bridge_info`、`unity_health_check`、`unity_list_tools`、`unity_call_tool`。
- 部署后生成可复制的 Codex TOML 配置片段，不自动修改全局配置。
- 在项目配置旁记录已脱敏的 JSONL 审计日志。

## 环境要求

- Windows
- 可通过 Windows `py` 启动器使用 Python 3.11
- Unity 2022.3 或更新版本
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
  --project-root "D:\path\to\ExampleUnityProject"
```

确认项目名和路径后，它会输出类似：

```toml
[mcp_servers.unity_bridge_exampleunityproject]
command = "D:\\path\\to\\ExampleUnityProject\\tools\\start_unity_http_stdio_bridge.cmd"
```

请手动复制该片段至 Codex MCP 配置。工具不会自动编辑任何全局配置文件。

## 验证顺序

1. `unity_bridge_info`
2. `unity_health_check`
3. `unity_list_tools`
4. 一个已知的只读 Funplay 工具

`0.1.0` 有 28 个自动化测试，覆盖配置校验、HTTP/JSON-RPC 故障、健康检查、部署保护、审计日志脱敏和 Codex 配置片段生成。

## 限制

- 每个 Bridge 进程只支持一个本机 Windows Unity 项目。
- 安装程序未代码签名，Windows SmartScreen 可能提示警告；请校验 SHA256 并审阅源码。
- 详细操作、架构和问题处理分别见 `docs/setup.md`、`docs/architecture.md`、`docs/troubleshooting.md`。
