# UI Agent v2 拼图工具（Bridge 0.3.0候选）

本页描述Bridge 0.3.0源码与安装器候选包含的v2扩展。旧GitHub `v0.2.0` 安装器没有这些v2工具；本轮构建与自检，不自动上传Release。Python支持范围仍为3.11。用`unity_bridge_info.bridge_capabilities`和MCP `tools/list`核对当前进程，部署后需重载。22个自有工具为4通用+5 v1+13 v2，Funplay原生工具数量另计。

## 调用流程

### 生成后的定位与新版本修订

先调用 `ui_agent_diagnose_composition(spec_json)`：保存 Prefab 必须与该原 Spec 的资产契约一致；工具在独立参考画布测量矩形、TMP容量和 Simple拉伸，返回 `complete/issues/evidence/suggestedChanges/diagnosisFingerprint`。若有未知组件或缺字，不实例化/动态填充字体。

例如选中 `SIMPLE_SPRITE_STRETCH:StartButton` 后，将原 Spec、诊断指纹、`issue_ids_json='["SIMPLE_SPRITE_STRETCH:StartButton"]'` 与新的 `output_prefab_path` 交给 `ui_agent_revise_composition`。工具重新向Unity诊断，检查新鲜度，只应用支持的定位/九宫格建议，返回新Spec、逐字段diff和Unity Validate。它不写Spec、不更新旧Prefab、不自动生成。布局驱动/拉伸锚点/超大节点的越界不猜测修法，Simple风险也不等于必须改Sliced。

之后仍走 Validate/Prepare→展示完整计划→开发者授权→新路径单次Generate→新旧审计/同条件截图与输入对照。`diagnosis_stale` 要重新检查证据，`diagnosis_incomplete` 要先处理保存资产差异或诊断阻断；没有建议的issue返回 `unsupported_revision`。不接受任意修订脚本或任意JSON Patch。参考UI Agent的 `docs/spec-revision.md` 和 `examples/generation/reports/spec-revision-20261101/`。

下列顺序用于首次创建：

1. 在目标项目安装包含 `UiCompositionSpriteCatalog` 的 UI Agent Package，并部署本地新版 Bridge 源码。每个项目仍使用自己的配置、Funplay 地址与预期项目根路径。
2. 调用 `ui_agent_find_sprites`，限定 `Assets` 文件夹或图片表路径；从候选中选择素材，将 `specReference` 放入 v2 Spec 节点 style。Agent 再明确选择 `imageType`；Sliced 时填写真实 `border`，不得自动编造或修改导入设置。
3. 调用 `ui_agent_validate_composition`，再调用 `ui_agent_prepare_composition`。向开发者展示完整 Spec、节点树、字体、每节点切片身份、Rect/Border、材质、输出路径、限制与 `planFingerprint`。
4. 取得开发者对该计划的确认后，在同一个 Bridge 会话调用 `ui_agent_generate_composition`。只创建新 Prefab 和 Spec 要求的自有文字材质，不实例化到活动场景、不保存场景、不覆盖资源。
5. 用原 Spec 调用 `ui_agent_audit_composition`，必要时再用现有层级读取及 Funplay `audit_ui`、隔离预览和截图验证。素材契约审计通过不证明布局、输入、视觉或业务行为正确。

## 十三个 v2 工具

| 工具 | 参数 | 唯一实现与输出 |
| --- | --- | --- |
| `ui_agent_diagnose_composition` | `spec_json: string` | 先核对保存 Prefab 契约，再在独立参考画布实测越界、TMP文字容量、Simple拉伸；返回节点证据、受限建议与依赖指纹，不写资源。 |
| `ui_agent_revise_composition` | `spec_json`、`diagnosis_fingerprint`、`issue_ids_json`、`output_prefab_path`（均 string） | 重查诊断并拒绝过期，应用选定的位置/九宫格建议与新输出路径，返回 Spec/diff/Unity Validate；不写盘、不自动生成。 |
| `ui_agent_measure_composition_layout` | `spec_json: string` | Package `MeasureLayoutJson`；在隔离预览场景按参考分辨率构建，使用原生 uGUI 布局读取各节点矩形和 PPU。允许输出路径已占用；不创建资源。 |
| `ui_agent_merge_sprite_selection` | `session_id: string`、`spec_json: string` | 只接受本进程已提交、绑定原 Spec 的会话；重查项目、Catalog 和布局快照，返回新 Spec、字段差异及 Unity Validate 结果。无文件写入，仍需 Prepare 和生成确认。 |
| `ui_agent_audit_sprite_imports` | `source_path: string` | Package `UiCompositionSpriteImportAuditor.AuditJson`；只读检查纹理导入模式与 Sprite 的 Simple/Sliced 可用性，输出需人工处理项。 |
| `ui_agent_find_sprites` | `source_path: string`；可选 `name_contains: string=""`、`offset: int=0`、`limit: int=50`、`catalog_fingerprint: string|null` | Package `UiCompositionSpriteCatalog.QueryJson`；支持 Single、Multiple、native 主 Sprite。返回 `sprites`、`totalMatches`、`complete`、`hasMore`、`nextOffset`、`catalogFingerprint`。 |
| `ui_agent_create_sprite_selection` | `source_path: string`、`catalog_fingerprint: string`、`slots_json: string`、可选 `spec_json: string` | 核对完整 Unity Catalog 和候选身份后，在 `127.0.0.1` 创建 15 分钟有效的本地候选页；最多12个用途槽位、30项候选、24 MiB预览图。提供 v2 `spec_json` 时，按每个槽位的 `specNodeId` 获取 Unity 原生布局实测尺寸，覆盖手填提示值并在页面标明来源。 |
| `ui_agent_get_sprite_selection` | `session_id: string`；可选 `wait_seconds: int=120`（0～300） | 等待浏览器提交；提交后重查 Unity Catalog 指纹与每项 Sprite 身份，再返回槽位、精确身份及可合并的 `style`。等待超时返回 `waiting_for_user`。 |
| `ui_agent_cancel_sprite_selection` | `session_id: string` | 取消会话并丢弃尚未提交的选择。 |
| `ui_agent_validate_composition` | `spec_json: string` | `UiCompositionSpecValidator.ValidateJson`；只检查 Spec，资源就绪检查在 Prepare。 |
| `ui_agent_prepare_composition` | `spec_json: string` | `UiCompositionGenerator.PrepareJson`；保留完整 Package 计划及错误。 |
| `ui_agent_generate_composition` | `spec_json: string`、`plan_fingerprint: string`、`user_confirmed: boolean` | `UiCompositionGenerator.GenerateJson`；Package 再预检资源、场景和目标路径。 |
| `ui_agent_audit_composition` | `spec_json: string` | `UiCompositionAssetAuditor.AuditPrefabJson`；路径取自 Spec；不合并活动场景报告。 |

Spec 上限为 65,536 UTF-16 单元，与 Package v2 一致。v1 仍为 16,384。数据编码为 UTF-8/base64 放入固定 C# 模板，不作为 C# 语法。仅这些可信数据模板允许最高 280,000 字符的传输代码；通用调用助手原有 65,536 限制保持不变，Funplay safety checks 始终开启。

## 浏览器候选选择闭环

Agent 先用 `ui_agent_find_sprites` 读取候选和 Catalog 指纹，再按具体界面用途组织少量槽位。创建会话的 `slots_json` 结构如下；每个候选必须传 Unity 查询结果里的完整身份：

```json
[
  {
    "id": "dialog.panel",
    "label": "对话框背景",
    "description": "选择最适合承载文字的面板素材",
    "candidates": [
      {"path":"Assets/MyUI/Art/panel_a.png","guid":"...","localFileId":"21300000"},
      {"path":"Assets/MyUI/Art/panel_b.png","guid":"...","localFileId":"21300000"}
    ]
  }
]
```

`ui_agent_create_sprite_selection` 会用给定指纹重新读取完整 Catalog，只接受 Catalog 中真实存在的候选，再从当前项目 `Assets` 内读取相应图片。返回一次性随机 `sessionId` 和本机 URL。Agent 将 URL 交给开发者打开，然后立即调用 `ui_agent_get_sprite_selection`；该工具最多等待300秒（默认120秒），因此浏览器提交后可自动返回，不再需要下载或手动粘贴 JSON。页面允许为每个用途槽位选一个候选及其实际可用的 Simple/Sliced 类型。

候选页支持 `usageHint`、`beginnerTip`、`specNodeId`、`writeScope` 和 `targetSize`。传入完整 v2 `spec_json` 后，Bridge 调 Unity 原生布局测量，取 LayoutGroup 压缩/扩展、Padding、嵌套锚点之后的实际矩形，覆盖手填提示，标记“Unity 实测 / 参考分辨率”。保留浮点尺寸，不再把 `preferredSize` 当最终尺寸。预览临时调整不写回 Spec。未绑定 Spec 的旧调用仍用手填/角色默认尺寸，明确标为“示意尺寸”，不能使用可靠合并工具。

Simple 按矩形铺满，默认不保持比例。Sliced 使用 `Sprite.pixelsPerUnit / Canvas.referencePixelsPerUnit × Image.pixelsPerUnitMultiplier` 将 Border 像素换算成 UI 单位，包含透明 Padding 和目标尺寸过小时的边框同比压缩。预览不是 Unity 渲染器：纹理压缩、过滤、材质和其他运行分辨率仍须在 Unity 验收。面板/按钮有可用 Border 时默认建议 Sliced，其他用途默认建议 Simple；推荐只是结构规则，不评审美、不代替开发者选择。

Prepare 的计划含 `layout` 和 `visualRisks`。`layout.basis=unity_ugui_reference_resolution`，包含各节点 `targetSize`、Canvas PPU、Image multiplier、参考分辨率、依赖哈希及 `layoutFingerprint`；候选页与 Prepare 共用这套测量。Simple 宽高比变化达到约20%时返回精确 Sprite 身份、实际矩形和变形倍数；不阻断、不修改 Spec。布局与风险都纳入计划指纹。测量需保存且 clean 的普通活动场景、就绪 Edit Mode、无 Prefab Stage；临时对象、材质、预览场景在 finally 清理。

### 可靠合并：提交后到生成前

1. 创建会话时传完整原 `spec_json`，每槽映射唯一图片节点。绑定项目根路径、Catalog、原 Spec 内容指纹和 Unity 布局指纹。
2. 提交后调用 `ui_agent_merge_sprite_selection(session_id, spec_json)`，传原 Spec，不接受外部任意选择 JSON。格式和键顺序变化不影响绑定；文案、颜色、路径等内容变更则拒绝并要求新会话。
3. 重核项目、完整 Catalog、Sprite 身份、布局和依赖；过期、未提交、重复节点映射和状态变化均停止。
4. 仅更新 `style.spritePath/spriteGuid/spriteName/spriteLocalFileId/imageType/border`。保留布局、颜色和文字；Multiple→Single、Sliced→Simple 清除旧选择字段。同一 Sprite 可复用到不同节点，返回 `reusedResources`；多个槽位写同一节点则拒绝。
5. 返回新 `spec`、逐字段 `changes`、新旧内容指纹和 Unity `validation`；`writesPerformed=false`。不保存 JSON，不调用 Prepare/Generate。之后必须另调 Prepare，展示完整计划并取得开发者确认，才能生成。

Bridge Spec 内容指纹、Unity 布局指纹、生成计划指纹用途不同，互不替代。字体/资源变化可能使布局快照失效；未选中的 Catalog 资源变化也会保守拒绝。重载丢失进程内会话，应重建候选页，不重放写入。

提交前页面会逐槽显示候选、Simple/Sliced 选择、目标尺寸、Spec 节点 ID 和拟写入范围。`writeScope` 是给开发者看的映射说明，不是可执行写盘指令；候选选择返回的 `style` 只映射到 Agent 指定的 Spec 节点。提交只确认素材选择，不是生成计划批准。之后仍必须合并到原 Spec、执行 Validate 和 Prepare、展示完整计划，并等待开发者明确确认后才能调用 Generate。**候选页不会自动修改 Spec 或触发生成。**

可复制的槽位骨架见 [`templates/ui-agent-sprite-selection.example.json`](../templates/ui-agent-sprite-selection.example.json)。模板的 `candidates` 有意为空，使用前应通过当前 Unity 的 `ui_agent_find_sprites` 获取新鲜 Catalog，再填入精确 `path`、`guid` 和字符串 `localFileId`；不要复用另一项目的 Sprite 身份。

服务仅绑定 `127.0.0.1` 的临时端口，候选页、Session 和图片都在 Bridge 进程内；页面只可读取会话内已核验的图片，不提供任意路径接口。POST 必须带正确 Host 与同源 Origin，候选页不执行 Unity 写入。每会话15分钟失效，只接受一次提交；最多8个并行会话。素材 Catalog 或 Sprite 身份变化时读取选择会失败并要求重新查询、创建会话。会话提交只表达用户的素材选择，不是 Spec 计划的生成批准；Agent 仍须将结果映射到 Spec，再执行 Validate/Prepare 并按生成流程确认。

当前 v2 节点白名单为 `Panel`、`Text`、`Button` 和受限原生 `Toggle`。Toggle Spec 必须声明 Boolean `initialValue`、`labelId` 和 `indicatorId`，并包含与其 ID 顺序对应的两个直接 Text 子节点。Prefab 持久化 Unity 原生 Toggle 及其 label/indicator Graphic 引用；不生成 C#、业务回调或设置持久化。Unity 项目仍须提供可处理 UI 输入的 EventSystem/Input Module；生成的 Prefab 不擅自修改项目输入设置。详见 UI Agent Package 的 `docs/ui-composition-spec.md`。

## 素材查询与分页

### 导入就绪审计

先用 `ui_agent_audit_sprite_imports` 查询 `Assets` 中的素材文件或目录。它会报告 Texture Type、Single/Multiple 模式、Sprite 身份、源图切片 Rect、Border，以及 `simpleUsable` / `slicedUsable`。每个来源给出 `readiness`：`ready_for_composition` 表示当前已有可引用 Sprite；`requires_manual_action` 表示 Sprite 配置需要人工检查；`not_configured_as_sprite` 表示纹理尚未设为 Sprite，是否转换由开发者决定；`not_applicable` 表示不属于支持的纹理或原生主 Sprite 资源。`requiresManualActionCount` 只计前述两种待人工决定状态；`excludedNonSpriteSourceCount` 计 `not_configured_as_sprite` 与 `not_applicable`，因此两项计数可能重叠，无关资源不会增加人工处理数。Border 为零或不适用于九宫格时，Sprite 仍可用于 Simple；只有计划用 Sliced 时才需要去 Sprite Editor 人工处理 Border。

该审计严格只读，不会改 Texture Type、切片、Border 或重新导入。PPU、滤波、压缩和 mipmaps 会作为现状输出，但项目尚未定义统一策略，因此不会自行判为错误。完整报告带 `catalogFingerprint`，绑定扫描路径、依赖哈希、来源设置与 Sprite 元数据；结果可以用于素材清单，文件或导入设置改变后重新检查。`complete=false` 表示此次没有完整清单，不能把未返回的素材当成不存在。扫描限制为1000源文件/10000 Sprite，超限不会返回局部候选。

`source_path` 必须是规范化 `Assets` 相对文件/文件夹路径，最长240字符；不接受 Packages、绝对路径、通配符或路径穿越。名称过滤是忽略大小写的子串，最多64字符。结果按路径、名称、字符串 local ID 排序。页大小1～100，offset 0～10000。

```json
{"source_path":"Assets/MyUI/Art/menu-sheet.png","limit":25}
```

结果每项给出 `path/guid/name/localFileId/rect/border/importMode/pixelsPerUnit/importSettings`。`localFileId` 与 `specReference.spriteLocalFileId` **始终为字符串**，不可转为 JavaScript Number。Multiple 引用形如：

```json
{"spritePath":"Assets/MyUI/Art/menu-sheet.png","spriteGuid":"0123456789abcdef0123456789abcdef","spriteName":"button_brown","spriteLocalFileId":"-6054090792327852210"}
```

Single/native 的 `specReference` 只含路径和 GUID，不附 Multiple selector。`slicedBorderUsable` 仅表示当前非零边界及边界和未超出 Rect；不证明美术边缘适合拉伸。

候选字段便于并排比较：按 `path/name` 分组，查看 `importMode`、`localFileId`、`rect`、`border`、`pixelsPerUnit`、`importSettings`、`slicedBorderUsable` 和 `specReference`。`preview` 给出源纹理路径、尺寸及左下角原点的像素 Rect，可用于在源图中定位 Multiple 切片；不会生成预览 PNG 或返回打包 SpriteAtlas UV。若一个源图内有多个切片，应按 `name + localFileId` 选定，不使用名字模糊匹配或默认首项。查询结果不是自动推荐，视觉用途仍由开发者判断，素材许可也不在查询范围内。

当 `hasMore=true`，使用 `nextOffset`，并将第一页面的 `catalogFingerprint` 原样传给下一次的 `catalog_fingerprint`。查询路径、过滤条件、素材身份、元数据或依赖变化时返回 `CATALOG_CHANGED`，从第一页重新选择。不能把不同快照的页拼在一起。

扫描上限为1000源文件和10000个 Sprite；超限、异常或身份不可读时 `complete=false` 且不返回部分候选，应缩小目录。`complete=true` 指扫描完成，整组结果是否取完看 `hasMore`。空结果只有在完整扫描范围内才有意义。

## 守卫和错误

所有连接 Unity 的 v2 工具复用项目身份、空闲 Edit Mode、安全代码模板和独立 `execute_code` 超时。候选会话工具不修改 Unity。缺 Package/API 时报告 `ui_agent_package_unavailable`，不自动安装。v1 和 v2 准备计划使用独立缓存，每种最多32项、30分钟过期；v2 缓存绑定精确 Spec 字符串及项目根路径，重启后需要重新 Prepare。生成调用发出前消费计划；任何失败均需核查后重新 Prepare，未知结果绝不自动重试。

外层 `ok=true` 仅代表调用与解包成功。必须同时看 `result.valid/status/errors` 或审计的 `complete/errorCount/findings`，不能把阻断或未完成报告当成功。

| 层级 | 常见错误/状态 | 处理 |
| --- | --- | --- |
| Bridge | `invalid_arguments` | 修正类型、长度、路径或分页参数；尚未调用 Unity。 |
| Bridge | `project_identity_unverified` / `project_identity_mismatch` | 修正目标项目部署/连接。 |
| Bridge | `editor_not_ready` | 核查编译、更新与 Play 状态；不要重放未知写入。 |
| Bridge | `confirmation_required` | 重新 Prepare、展示完整计划并确认。 |
| Bridge | `execution_status_unknown` | 按返回的准确 Prefab 路径及指纹读回，并检查执行历史；不自动重试。 |
| Bridge | `catalog_stale` / `candidate_not_in_catalog` | 素材已变化或候选不属于完整快照；重新查询并建立新的候选页。 |
| Bridge | `session_expired` / `session_limit` | 重新创建候选会话，或读取/取消已有会话。 |
| Package 查询 | `SOURCE_NOT_FOUND` / `SPRITE_SOURCE_REQUIRED` | 选择已导入且受支持的 Sprite 来源。 |
| Package 查询 | `SCAN_LIMIT` / `CATALOG_READ_FAILED` / `SPRITE_IDENTITY_UNAVAILABLE` | 缩小查询范围或检查具体资源；不推断素材不存在。 |
| Package 查询 | `CATALOG_CHANGED` | 重新从 offset=0 查询，重新选择。 |
| Package 计划/生成 | `blocked` / `confirmation_required` 等 | 保留并展示 Package 的具体错误；资源变化需要重做计划。 |

确认参数和指纹是流程控制，不是人工身份认证；Bridge 无法独立证明开发者阅读或批准过计划。通用 `unity_call_tool` 仍可执行其他 Funplay 工具，因此此流程不构成沙箱或对所有调用的授权系统。

## 本地加载与范围

源码部署或重装后需要重启对应项目的Bridge MCP进程；已运行进程不会自动增加工具。重新连接后检查`tools/list`：应有4通用、5 v1、13 v2，共22个本Bridge自有工具。Package与Bridge更新是两件事，二者都需就绪。

本轮不新增 SpriteAtlas 打包、自动切片、模糊匹配、材质/字体发现、批量生成、业务事件绑定、多分辨率适配或独立 UI Agent MCP 服务。
