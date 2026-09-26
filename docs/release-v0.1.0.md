# Codex-Funplay Unity Bridge 模板 v0.1.0

## 概述

第一个可用版本：一个按项目隔离的 stdio-to-HTTP Bridge，用于连接 Codex Desktop 与本机 Funplay MCP for Unity 服务。

## 包含内容

- Windows 校验与部署向导。
- 本地 URL、端口、MCP 初始化、协议与工具发现检查。
- `unity_bridge_info`、`unity_health_check`、`unity_list_tools`、`unity_call_tool`。
- 部署后生成可复制的 Codex 配置片段，不改写全局配置。
- 项目本地 Python 虚拟环境和已脱敏 JSONL 审计日志。
- 锁定并经测试验证的 `mcp==1.30.0`、`httpx==0.28.1`。
- 28 个自动化测试。

## 安装

1. 在 Unity 启动 `Funplay > MCP Server`，复制准确本地 URL。
2. 从此 Release 下载并运行 `Codex-Funplay-Bridge-Setup.exe`。
3. 选择项目根目录，粘贴 URL，验证并部署。
4. 生成可复制的 Codex MCP 条目，手动粘贴到目标配置并重新加载服务。
5. 在写操作前运行 `unity_health_check` 和 `unity_list_tools`。

## 校验

本 Release 的 SHA256 由附件 `Codex-Funplay-Bridge-Setup.exe.sha256` 提供：

```powershell
Get-FileHash .\Codex-Funplay-Bridge-Setup.exe -Algorithm SHA256
```

## 限制

- 每个 Bridge 进程支持一个本机 Unity 项目。
- 不修改 Funplay、Unity 资源、Codex/Claude Code/Coplay 全局配置。
- 安装程序未代码签名；下载后请校验 SHA256。
