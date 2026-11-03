# 变更日志

## 0.3.0 — 本机构建候选，尚未发布

- 将完整 UI Agent 扩展纳入安装器：22个自有MCP工具（4通用、5 v1、13 v2），包括原生布局测量、可靠选择合并、生成结果诊断和受限Spec修订。
- 安装包自检从旧14工具计数升级为精确22工具名称及8项capability核对，同时检查wheel包含候选页/合并/修订模块。
- 保留Python 3.11部署要求、项目级虚拟环境、独立execute_code超时与写入结果未知时不重放。未实现Python多版本发现或自动升级正在运行的MCP进程。
- UI Agent Package单独提供，首发范围为Package源码、测试和三项Sample；Bridge不内嵌字体、美术或Unity Package。

以下为本版本开发过程的历史检查点，最终安装器验收见 `docs/release-v0.3.0.md` 和 `docs/release-validation.md`。

- 增加只读 Sprite 素材查询，保留 Multiple 子资源的字符串 Int64 ID、Rect、Border、分页快照及 Spec 引用。
- 新增 v2 校验、计划、生成、保存后素材契约审计四个 MCP 工具，复用 Package API 和项目/Editor 守卫。
- v1/v2 分离计划缓存，生成前消费计划，未知结果不重放；v2 支持65536 UTF-16单元数据及受限可信模板传输。
- `unity_bridge_info` 增加能力标记；增加导入检查、源码工具总数此前为15个。尚未构建新安装器或发布新版本。
- 增加 `ui_agent_audit_sprite_imports`，只读调用 Package 导入审计，报告精确Sprite身份、导入设置和Simple/Sliced可用性；不自动修复。2026-10-21完整pytest105/105，独立stdio进程发现15工具并通过真实Unity审计调用。
- 新增 `ui_agent_create_sprite_selection`、`ui_agent_get_sprite_selection`、`ui_agent_cancel_sprite_selection`：候选图片在本机 loopback 页显示，用户提交后由 MCP 工具等待并回传；创建与读取都会核对完整 Unity Catalog 和精确 Sprite 身份。支持图片表 Rect 预览裁切、同源提交检查、15分钟失效和一次提交。
- 新增候选会话后源码共18个自有工具。Bridge 全量测试110/110；真实 Sandbox Catalog、页面和图片服务、提交与指纹复核已通过。未构建 EXE、未改发布版本或 GitHub。
- 候选页增加中文用途槽位说明、新手提示、结构启发式推荐理由与未优先候选原因、目标尺寸 Simple/Sliced 并排预览、Spec 节点映射及写入范围。提交仍只回传素材选择，不会自动修改 Spec 或生成；Agent 必须继续 Validate、Prepare、展示完整计划并等待开发者确认。新增可复用槽位模板；候选身份需由每个 Unity 项目的新鲜 Catalog 填入。Bridge 全量 pytest 为117/117；候选页定向测试为11/11。

## 0.2.0 — 已发布（以下为该版变更）

- 新增五个可选 UI Agent MCP 工具：Spec 校验、准备计划、确认后生成、层级读取、活动场景合并审计。
- 配置支持 Unity 项目绝对根路径，专用调用在 Unity 主线程核对项目身份和 Editor 就绪状态。
- 计划按当前 Bridge 会话缓存，30 分钟过期，生成前消费，超时不自动重放。
- 支持异步审计查询与 finding 分页，保留未完成状态。
- 部署向导增加可选桥名称与 MCP 标识预览，文件名保持固定。
- `execute_code_timeout_seconds` 独立配置，默认 60 秒，上限 300 秒；超时返回 `execution_status_unknown`。
- 构建按元数据版本选择 wheel，自动生成 SHA256；新增安装包临时部署自检。
- 保留四个通用工具和旧配置兼容，未安装 UI Agent 时仍可使用普通 Funplay 桥。

## 0.1.0 — 已发布

首个项目级 stdio-to-HTTP Bridge，包含 Windows 部署向导、四个通用工具、健康检查、配置片段和脱敏审计日志。28 项自动化测试。
