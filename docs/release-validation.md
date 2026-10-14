# v0.2.0 发布验证

状态：阶段五候选构建与本机验证完成，待用户检查。尚未发布 GitHub Release。

## 可复现命令

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
git diff --check
.\build_setup_exe.cmd
$installerReport = Join-Path $env:TEMP 'codex-funplay-bridge-0.2.0-installer-check.json'
$installerCheck = Start-Process -FilePath '.\release\Codex-Funplay-Bridge-Setup.exe' -ArgumentList @('--self-check', $installerReport) -WindowStyle Hidden -Wait -PassThru
$installerCheck.ExitCode
Get-Content $installerReport
Get-FileHash .\release\Codex-Funplay-Bridge-Setup.exe -Algorithm SHA256
Get-Content .\release\Codex-Funplay-Bridge-Setup.exe.sha256
```

`--self-check` 不显示向导，使用临时目录检查 Tk 向导组件、内嵌 wheel 版本、实际部署和已有管理文件替换、`pip check` 和安装后 stdio MCP 注册的 9 个工具。自检需要 Python 3.11 和依赖下载网络，不会连接真实 Funplay 或改动用户 Unity 项目；通过不等于真实 Unity 调用通过，Unity 证据记录于 [阶段四](ui-agent-tools-design.md)。

## 检查记录

2026-10-12：

- Bridge 单元测试：`74 passed`。
- Python `compileall`、`pip check`、`git diff --check`：通过。
- 内嵌 wheel：`codex_funplay_bridge-0.2.0-py3-none-any.whl`。
- EXE 自检：退出码 0；向导字段、wheel 版本、临时项目部署、已有管理文件替换、依赖完整性和 MCP stdio 握手均通过；发现 4 个通用工具与 5 个 UI Agent 工具。临时报告在系统 TEMP 目录，自检项目目录已清除。
- 候选 EXE 的 Defender 自定义扫描已完成，未报告检测。安装程序未做代码签名。
- 构建产物：`release/Codex-Funplay-Bridge-Setup.exe`，16,085,653 bytes。
- SHA256：`4245b29f2d3aefc4d6e35fa65ed3a888b92391f8b5e60443b936d279003ba7a7`，与 `.sha256` 附件一致。
- 初次验收发现的问题已修正；随后重建的安装包通过完整自检。自检覆盖临时项目部署，不代表所有既有虚拟环境升级情形均已验证。

候选包交给用户检查。确认后再准备 GitHub Tag 与 Release 附件上传。
