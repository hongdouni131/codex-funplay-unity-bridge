# Codex-Funplay Unity Bridge v0.2.0（发布候选）

这个版本让 Codex 直接发现并调用 UI Agent 的校验、计划、生成、层级读取与审计工具，同时继续支持原有 Funplay 通用桥。当前产物供本地检查，尚未创建 GitHub Release。

## 新增能力

- 五个参数明确的 `ui_agent_*` 工具，调用项目已安装的 UI Agent Tools Package。
- 项目根路径与 Editor 状态守卫；确认后按计划指纹生成，不覆盖既有资源。
- 计划会话缓存与消费，执行超时不自动重试。
- 活动场景本地/原生合并审计，支持异步查询和 finding 分页。
- 可选桥名称和 MCP 标识预览，`execute_code` 独立超时。

## 安装和升级

从对应 Release 下载 `Codex-Funplay-Bridge-Setup.exe` 与 `.sha256`，校验后运行。目标电脑需要 Python 3.11 和依赖下载网络。选择项目、填写准确 Funplay URL、验证并部署，然后将配置片段手动加入 Codex 并重载服务。

v0.1.0 用户记录原配置后在同一项目重新部署；向导会替换四个 Bridge 管理文件，配置使用当前输入值。旧配置仍支持四个通用工具，缺少根路径会阻止 UI Agent 调用。详见 [安装和升级说明](setup.md)。

UI Agent Tools Package 单独安装，EXE 不内嵌该 Unity Package。当前验证组合为 Bridge `0.2.0`、Package `0.1.0`、Unity `2022.3.62f3c1`。未安装 Package 的项目继续使用通用桥。

## 验证与限制

74 项自动化测试通过。阶段四在隔离 Unity 测试项目中验证了五个工具、确认门槛、项目拦截、生成读回和活动场景审计。EXE 的临时部署、自检和 MCP 工具发现通过；Defender 自定义扫描完成。完整记录和 SHA256 见 [发布验证](release-validation.md)。

每个 Bridge 进程对应一个项目。生成器支持受限主菜单，字体需覆盖文案，按钮不绑定游戏逻辑；Prefab 支持层级读取，合并审计只针对活动场景。计划指纹不能独立证明真人确认。安装程序未代码签名，校验文件用于比对下载内容。
