# UI Agent MCP 工具设计

状态：阶段 1 契约、阶段 2 基础守卫、阶段 3 五个具名工具均已实现；阶段 4 隔离 Unity 测试项目验证已完成。实机验证覆盖 Spec 正反例、活动场景与 Prefab 层级读取、项目身份拦截、确认门槛、菜单生成读回和活动场景审计。验证完成后清理了临时场景对象，确认测试场景未留下未保存的改动。

阶段 5 发布候选已升级至 `0.2.0`，更新用户文档、变更日志及版本化 wheel/EXE 构建流程。最终 EXE 自检在临时 Unity 项目成功部署，`pip check` 正常并发现 4 个通用、5 个 UI Agent MCP 工具；替换已有管理文件也通过。候选 EXE 的安全扫描已完成。Bridge 自动化测试 74 项通过，Python `compileall`、`pip check` 与 `git diff --check` 通过。候选仍待发布检查，尚未创建 GitHub Release。

部署向导支持可选 Bridge 名称和 MCP 标识预览，配置保存独立的 `bridge_name`，项目身份仍按 Unity 项目根路径检查。普通工具超时与 `execute_code` 独立超时分别配置；超时结果不明时不自动重试。

超时方案已在隔离 Unity 测试项目中部署验证：`timeout_seconds` 默认 10 秒，新增 `execute_code_timeout_seconds`（默认 60 秒，上限 300 秒），用于通用 `unity_call_tool(execute_code)` 与 UI Agent 专用调用。超时错误使用 `execution_status_unknown`，不重试。项目身份检查、Editor 就绪检查与安全调用流程均已验证；重载 Bridge 后，新进程会读取更新后的配置和代码。

## 目标与边界

在项目级 Bridge 中增加具名、参数类型明确的 MCP 工具，调用现有 UI Agent Unity Editor Package。继续使用当前 stdio-to-HTTP 通道和 Funplay 服务。不新增 Unity 连接，不修改 Funplay，也不在 Python 中重复实现 UI 生成或审计逻辑。校验、计划、生成、层级读取和 UI 规则的唯一实现仍是已安装在 Unity 项目中的 UI Agent Package。

调用路径：

```text
Codex -> Bridge 具名工具 -> Funplay tools/call(execute_code 或 audit_ui) -> UI Agent Package -> Unity Editor
```

现有通用工具（`unity_bridge_info`、`unity_health_check`、`unity_list_tools`、`unity_call_tool`）继续保留，行为不变。

## 项目与编辑器前置条件

- 扩展项目本地 Bridge 配置，保存预期的 Unity 项目根路径。部署向导已经知道用户选择的项目根路径，应将解析后的路径写入配置。已有配置继续可供通用 Bridge 工具使用；若缺少预期根路径，UI Agent 工具返回 `project_identity_unverified` 并停止。
- 每次 UI 操作在同一个 Unity 主线程命令中，将配置根路径与 `Application.dataPath` 推导的 Editor 项目根路径核对。工具调用者不能通过参数覆盖 Bridge 配置中的项目身份。
- 调用 Package API 前确认 Unity/Funplay 已连接且 Editor 就绪。若 Unity 正在编译、更新、播放或暂不可用，返回结构化的 `editor_not_ready`，不得自动重试写操作。
- 将 `spec_json` 等字符串限制在合理长度内，再嵌入 C#。将输入作为数据进行序列化和转义，不把原始用户文本拼接成可执行 C# 语法。调用前验证 Funplay 的 `execute_code` schema 支持布尔型 `safety_checks`，调用时始终设置 `safety_checks=true`，只生成实现 `IFunplayCommand` 的固定代码模板。
- 连接的 Unity 项目必须已安装 UI Agent Package。若 Package 缺失或 API 不可用，返回 `ui_agent_package_unavailable`；Bridge 不得暗中安装 Package。

## 具名工具

| 工具 | 参数类型 | Package/API 行为 | 副作用 |
| --- | --- | --- | --- |
| `ui_agent_validate_spec` | `spec_json: string` | 调用 `UiSpecValidator.ValidateJson`；返回 Spec 校验、规范化后的 Spec、错误和指纹。 | 无；不读取项目资源。 |
| `ui_agent_prepare_main_menu` | `spec_json: string`、`font_asset_path: string` | 调用 `MainMenuGenerator.PrepareJson`；返回完整的项目计划、`planFingerprint`、就绪检查和错误。在 Bridge 进程内暂存已准备计划，供后续生成调用核对。 | 只读。 |
| `ui_agent_generate_main_menu` | `spec_json: string`、`font_asset_path: string`、`plan_fingerprint: string`、`user_confirmed: boolean` | 必须满足 `user_confirmed=true`、指纹与本 Bridge 进程准备的计划匹配、当前项目身份匹配。使用该指纹调用 `MainMenuGenerator.GenerateJson`；Package 再次核对计划与输出路径。 | 创建计划指定的 Prefab 和场景实例；超时或结果不明时绝不自动重试。 |
| `ui_agent_inspect_hierarchy` | `source: "active_scene" | "prefab"`，可选 `asset_path: string` | 调用 `UiHierarchyInspector.InspectActiveSceneJson` 或 `InspectPrefabJson`。只有 `source="prefab"` 时才要求 `asset_path`，且必须是 Assets 相对路径并以 `.prefab` 结尾。 | 只读。 |
| `ui_agent_audit_ui` | 第一版不接受目标参数，只审计活动场景。 | 调用 `DesktopMenuAuditor.AuditActiveSceneJson`，再调用 Funplay `audit_ui`（`scope="scene"`）；收集同一活动场景的所有结果页后，使用 `MergeFunplayJson` 合并。若原生审计异步执行，则轮询 Funplay task。 | 只读；不修复或保存资源。 |

工具说明必须明确：只有在向用户展示完整计划并取得明确确认后，才调用生成工具。`user_confirmed` 和指纹都是调用方提供的流程数据；Bridge 可以要求它们并检测计划变化，但无法独立证明真人看过或批准了计划。

## 返回与错误契约

返回 JSON 兼容对象，并保留 Package 报告原有字段和状态，不要将信息压平丢失：

```json
{"ok": true, "tool": "ui_agent_prepare_main_menu", "project": {"name": "..."}, "result": {"status": "ready_for_confirmation"}}
```

```json
{"ok": false, "error": {"kind": "editor_not_ready", "message": "...", "details": {}}}
```

为无效参数、项目身份校验失败、Editor 未就绪、Package 不可用、Funplay/JSON-RPC 错误、超时、无效响应和审计未完成定义稳定的错误类型。只读审计仍在运行时，返回操作/任务标识和有上限的轮询说明。生成超时意味着执行结果未知：返回准确的计划路径和指纹供检查，绝不自动重放写操作。

审计返回必须保留 `incomplete`、截断信息、限制条件和原生审计任务状态。除非两个来源都报告成功完成，否则“发现列表为空”不等于完整审计。第一版不声称能合并 Prefab 的本地/原生审计：Package 的报告合并 API 要求两边来自同一个已加载场景；Prefab 层级读取仍受支持。

## 实施阶段与检查点

1. **工具契约**：确认工具名、输入、写入范围、项目校验、确认门槛、错误和返回结构。本文档是第一阶段的检查成果。
2. **基础调用逻辑（已实现并验证）**：增加项目根路径配置、项目身份核验、安全的 `execute_code` 请求/结果处理、就绪检查和针对性单元测试。
3. **具名工具（已实现并验证）**：`ui_agent_validate_spec`、`ui_agent_prepare_main_menu`、`ui_agent_generate_main_menu`、`ui_agent_inspect_hierarchy`、`ui_agent_audit_ui` 已注册。准备计划只缓存在当前 Bridge 进程，最多 32 项、30 分钟过期；生成前消费计划，超时不重放。审计支持异步 `get_task` 轮询和 finding 分页聚合；原始 Spec、用户文案和 C# 代码不会写入 UI Agent 审计日志。
4. **隔离 Unity 测试项目验证（已完成）**：验证了五个具名工具注册、Spec 正反例、活动场景与 Prefab 层级读取、活动场景审计、项目身份拦截、未确认时阻止生成和计划准备。审计报告解析问题已修复。确认计划后，菜单生成、Prefab 层级读回和审计均通过；测试产生的临时场景对象已清理，测试场景恢复为无未保存改动。全套自动化测试 74 项通过，Python `compileall` 与 `git diff --check` 通过。此阶段完成后进入发布准备。
5. **发布准备（本机候选完成，待用户检查）**：README、安装/架构/故障排除文档、变更日志与候选发布说明已更新；版本 `0.2.0` wheel、EXE、SHA256 已构建。74 项测试、EXE 临时部署和九工具发现、`pip check`、`compileall`、`git diff --check` 均通过；候选 EXE 安全扫描完成。自检期间发现的问题已修正，重建后的安装包完整自检通过。交由用户检查后再准备带版本号的 GitHub Release。

每阶段结束时提供实现内容和验证证据，由用户检查后再进入下一阶段。
