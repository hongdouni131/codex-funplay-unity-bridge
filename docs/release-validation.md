# 发布验证

## 0.3.0 安装版与真实 Unity 只读配对（2026-11-03）

**最终复核：** 完整重启客户端后，Bridge常驻进程编号和创建时间已更新；启动脚本指向项目venv，运行模块/元数据均0.3.0、非editable，安装来源为已校验EXE内嵌wheel。本会话22工具/8capability、Funplay180、真实Unity只读诊断及其保存审计均通过（16节点、0finding、0issue、6文字不溢出），Console无error、场景读回不变。以下“进程重启待完成”描述本日中途状态，现已解决；未生成新Prefab或修改全局MCP配置。

- 从已校验的0.3.0 EXE提取内嵌wheel与模板，调用与安装向导相同的部署函数升级已有验证项目；没有执行交互向导点击验收。原URL、项目根路径、名称与10/60秒超时语义保持一致，四个管理文件已在本机备份。
- 升级前是源码可编辑安装：运行模块版本0.3.0，但发行元数据仍0.2.0。升级后独立进程的运行模块与发行元数据均为0.3.0，非editable；16个已安装Python模块与EXE内嵌wheel逐字节一致，源码模块也一致。
- 独立安装版stdio MCP精确发现22工具、8项capability均true；Funplay健康检查180工具。真实Unity2022.3.62f3c1 Edit/ready，守卫核对项目根目录成功。既有16节点Spec校验通过、保存Prefab审计16/16且0finding；诊断complete、0issue、6文字不溢出，Console无error。
- 活动场景读回前后一致，269份预先记录的选定资源/代码/配置文件hash不变；这不是全项目所有文件的完整性证明。没有生成新Prefab、进入Play、截图或硬件测试，没有改Codex全局配置。
- 此证据来自新启动的独立安装版进程；当前聊天常驻MCP的重载仍待操作，不能用同一个0.3.0版本字符串代替重载证据。只读公开摘要见 [installed-unity-pairing](validation/v0.3.0-installed-unity-pairing.json)，已排除本机路径与原始日志。
- 本轮未重跑前一天160项单元测试；没有修改Bridge运行代码、EXE或Package代码。GitHub仍只有v0.1.0/v0.2.0，未提交或正式发布0.3.0。
- 随后开发者报告已重载，当前聊天实际22工具发现、Validate/16节点审计/诊断及Console检查也通过，活动场景读回不变；但操作系统观察到的Bridge进程与创建时间仍未变化。因此仅记录“当前会话只读配对通过”，不能记录“已确认加载安装版的新常驻进程”。开发者选择稍后完整重启客户端，重启检查前不执行提交或正式发布。

## 0.3.0 本轮候选验证（2026-11-02）

- 全量pytest：**160 passed**，结果XML存于本机 `pyinstaller-build/validation-0.3.0/pytest.xml`。
- Python compileall、git diff --check通过；Git提示LF/CRLF转换，是行尾提示，不是内容错误。
- 已构建内嵌`codex_funplay_bridge-0.3.0-py3-none-any.whl`的EXE，23,500,561字节；SHA256 `1631a73504d7f4419185f5033a336a7c295cb0ea58fc1197675192f65f400a95`。
- 安装器实际自检退出0，`frozen=true`、`ok=true`：Tk字段、内嵌0.3.0 wheel/v2模块、临时项目部署、自定义名称和75秒超时、已有管理文件替换均通过；pip check无损坏依赖；安装后stdio精确发现22工具、8项capability均true，临时目录已清除。证据在 `docs/validation/v0.3.0-installer-check.json`；本机原始结果为 `pyinstaller-build/validation-0.3.0/installer-check.json`。
- 这不是当前Sandbox服务升级或真实Unity配对验收；未改已有项目配置和Codex全局配置，当前已运行MCP进程仍需日后部署/重载。未重复此前真实Unity生成或Player/硬件测试。
- 旧0.2.0二进制已保留本地归档，不覆盖GitHub历史附件。本轮尚未上传0.3.0、Tag或Release。

自检命令：

```powershell
$report = Join-Path $env:TEMP 'codex-funplay-bridge-0.3.0-check.json'
$check = Start-Process -FilePath '.\release\Codex-Funplay-Bridge-Setup.exe' -ArgumentList @('--self-check', ('"' + $report + '"')) -WindowStyle Hidden -Wait -PassThru
$check.ExitCode
Get-Content $report
```

新版自检验证Tk字段、内嵌wheel版本和v2模块、临时项目实际部署与管理文件替换、pip check、安装后stdio精确22工具/8项capability。需要Python3.11及依赖下载网络；不连接真实Funplay、不改已有Unity项目。构建日志出现未发现conda-meta的环境判断提示，已保留日志；不由该提示推断部署失败。

## 以下为v0.2.0及中途源码阶段历史记录

**后续源码增量（2026-10-19）**：v2具名工具已在本地实现，Bridge104/104、Unity Package280/280及真实stdio MCP闭环通过，见 [v2工具说明](ui-agent-composition-tools.md)。本轮未重建/复测EXE，也未发布；下方九工具、74测试及安装包证据属于原0.2.0历史记录，不代表当前十四工具源码的安装器验收。

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
