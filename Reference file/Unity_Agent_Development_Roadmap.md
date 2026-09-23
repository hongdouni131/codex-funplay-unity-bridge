# Unity Agent 开发路线

- 所有回复使用中文，先说明结论。
- 每次开始前：先列出修改内容和方法，并告诉我如果人工修改的大致内容
- 每次完成列出：修改文件、关键变量、测试结果。

## 项目目标

基于 [Funplay MCP for Unity](https://github.com/FunplayAI/funplay-unity-mcp)，构建一个适合作品集的 Unity 开发 Agent 系统。

本项目不重复实现 Funplay 已经提供的通用 Unity 工具，而是重点解决两个问题：

1. 让 Codex Desktop 可以稳定、可复用地连接新的 Unity 项目。
2. 在现有 MCP 工具之上，增加面向实际游戏开发流程的 Agent 工作流，使 Agent 能够规划、执行、验证并报告 Unity 开发任务。

```text
Codex Desktop
    |
    | stdio MCP
    v
Codex-Funplay Bridge 模板
    |
    | HTTP JSON-RPC
    v
Funplay MCP for Unity
    |
    v
Unity Editor
```

## 总体开发路线

| 阶段 | 项目 | 主要成果 | 难度 |
| --- | --- | --- | --- |
| 1 | Codex-Funplay Bridge 模板 | 新 Unity 项目可以重复使用的 Codex 到 Funplay 连接方案 | 低到中 |
| 2 | UI 可用性检查 Agent | 读取、检查、截图并报告 Unity UI 的可用性问题 | 中 |
| 3 | 敌人配置 Agent | 检查并安全配置指定类型的敌人 Prefab，然后验证结果 | 中到高 |
| 4 | 共享 Agent 框架 | 在多个 Agent 之间复用规划、确认、验证和审计组件 | 高 |

## 第一阶段：Codex-Funplay Bridge 模板

### 目标

Funplay 通常会在 Unity 内提供 HTTP MCP 服务。在当前本地环境中，Codex Desktop 使用 Python stdio-to-HTTP Bridge 连接时更加稳定。

这一阶段的目标是把已经验证过的桥接方案做成可重复使用的项目模板，而不是重新实现 Funplay，也不是修改 Funplay 的核心协议。

### 第一版范围

只支持：

- Windows
- Codex Desktop
- 本机 Unity 项目
- Funplay MCP HTTP 服务
- 每个项目独立的 Python 虚拟环境
- 健康检查和清晰的错误信息

第一版暂不支持：

- 修改 Claude Code 配置
- 集成 Coplay / MCP for Unity
- 远程 Unity 主机
- 自动修改全局 MCP 配置
- 多项目自动路由

### 每个 Unity 项目生成的文件

```text
<Unity项目>/
  tools/
    unity_http_stdio_bridge.py
    start_unity_http_stdio_bridge.cmd
    requirements-unity-http-bridge.txt
    bridge-project.toml
  .unity-mcp-bridge-venv/
```

### 必要能力

| 能力 | 预期行为 |
| --- | --- |
| 初始化 | 创建虚拟环境并安装锁定版本的依赖 |
| 项目配置 | 在一个项目级文件中保存项目名、Unity 根目录、Funplay URL 和端口 |
| 工具发现 | 将 `tools/list` 转发给 Funplay |
| 工具调用 | 将 `tools/call` 转发给 Funplay |
| 健康检查 | 检查端口监听、HTTP 响应、MCP 初始化和工具数量 |
| 故障诊断 | 说明端口错误、Unity 未运行、Funplay 未启动、超时或响应不兼容 |
| 日志 | 写入 JSONL 调用日志，同时不泄露密钥 |
| 隔离 | 不修改 Claude Code 或 Coplay 配置文件 |

### 验收测试

1. 打开 Unity，进入 `Funplay > MCP Server` 启动服务。
2. 记录 Funplay 窗口显示的准确 URL，例如 `http://127.0.0.1:22166/`。
3. 运行 Bridge 健康检查。
4. 确认 `tools/list` 返回非零数量的工具。
5. 从 Codex 调用一个安全的只读 Unity 工具。
6. 确认 Bridge 报告中包含项目、端口和调用结果。

## 共享 Agent 工作模式

后续每个 Agent 都应遵循以下闭环：

```text
自然语言需求
    -> 分析当前 Unity 状态
    -> 生成结构化计划
    -> 对有风险的修改先展示计划
    -> 调用指定的 Funplay 工具执行
    -> 重新读取场景 / Prefab / 组件状态
    -> 检查编译和 Console 错误
    -> 必要时运行 Play Mode 或截图取证
    -> 返回审计报告
```

基本规则：

- 简单操作优先使用 Funplay 已有的专用工具。
- 只有在需要多步编排时才使用 `execute_code`。
- 修改 Unity 对象的代码优先实现 `IFunplayCommand`，使用 `ExecutionContext`，以支持 Undo 和结构化变更记录。
- 如果请求因域重载或重编译中断，在重新读取 Unity 状态确认前，不要假设操作成功。
- 不要用 Shell 工具直接修改 `.unity`、`.prefab` 或 `.asset` YAML 文件。
- 先读取，再修改，最后验证。

## 第二阶段：UI 可用性检查 Agent

### 目标

检查 Unity UI，并生成有证据支持的可用性报告。第一版只检查和报告，不自动修改。

### 输入

- 目标场景或 Prefab 路径
- 目标分辨率和屏幕方向
- 可选的 UI 根对象
- 规则集，例如移动端竖屏 UI 规则

### 检查内容

| 类别 | 示例检查项 |
| --- | --- |
| 布局 | 锚点、Pivot、RectTransform 尺寸、元素是否超出屏幕 |
| 文本 | 文本溢出、字体缺失、过度截断、字体过小难以阅读 |
| 交互 | EventSystem 缺失、按钮未激活、射线检测被遮挡 |
| 层级 | 重复 UI 根节点、Canvas 缺失、Sorting Order 错误 |
| 响应式表现 | Safe Area、安全区、横竖屏切换、不同分辨率下的重叠 |
| 视觉证据 | Scene View / Game View 截图和屏幕坐标映射 |

### 输出示例

```json
{
  "summary": "2 个错误，3 个警告",
  "findings": [
    {
      "severity": "error",
      "objectPath": "Canvas/Menu/StartButton",
      "rule": "ui.element_outside_safe_area",
      "evidence": "屏幕边界超出右侧安全区",
      "recommendedAction": "检查锚点和偏移量"
    }
  ],
  "screenshots": [],
  "verified": true
}
```

### 后续扩展

只有在展示修改计划并获得确认后，才提供自动修复。每次修复都必须限定在已经确认的目标对象上，并在修改后重新截图和读取状态进行验证。

## 第三阶段：敌人配置 Agent

### 目标

第一版只支持一种明确的敌人类型，例如“近战巡逻敌人”，不建议一开始就制作一个可以创建任意敌人的通用工具。

### 支持的输入

- 已确认的 Prefab 路径
- 生命值、移动速度、检测范围、攻击范围
- 巡逻点引用
- 必须满足的 Layer、Tag 和组件契约

### Agent 工作流

1. 检查 Prefab 路径和组件。
2. 报告缺失或冲突的要求。
3. 生成配置变更计划。
4. 修改已有敌人前等待明确确认。
5. 只应用已批准的组件属性。
6. 重新读取准确值。
7. 如果修改了脚本，重新编译、检查 Console 错误，并按需进入 Play Mode 验证运行时行为。

### 最低验证契约

| 类别 | 验证内容 |
| --- | --- |
| 对象身份 | 确认目标是正确的 Prefab 和实例 |
| 物理 | Collider 和 Rigidbody 是否满足要求 |
| 游戏逻辑 | 生命值、速度、检测距离、攻击距离 |
| 导航 | 需要时检查 NavMeshAgent 设置 |
| 动画 | Animator / Controller 引用存在，但默认不修改动画资源 |
| 引用 | 巡逻点和目标引用是否有效 |
| 运行时 | 配置后没有新增编译错误或 Console 错误 |

### 安全边界

- 第一版：检查已有敌人并生成配置计划。
- 修改已有敌人：必须经过明确确认。
- 未经确认，不修改玩家资源或动画资源。
- 每创建一种新敌人，都要建立独立的 Markdown 设计记录。

## 第四阶段：共享 Agent 框架

当 UI Agent 和敌人 Agent 可以独立工作后，再提取共享组件：

| 组件 | 职责 |
| --- | --- |
| Planner / 规划器 | 将用户需求转换为有类型、有顺序的任务 |
| 项目上下文读取器 | 读取场景、选择对象、Console、编译和当前项目状态 |
| 确认门 | 对有破坏性或范围较大的修改要求人工确认 |
| 执行器 | 调用 Funplay 工具并保留结构化响应 |
| 验证器 | 读取准确值、错误、截图和 Play Mode 证据 |
| 审计日志 | 以 JSONL 保存请求、计划、调用、变更和结果 |
| 报告器 | 输出简洁总结、证据和未解决风险 |

## 建议的仓库目录

```text
codex-funplay-unity-agent/
  README.md
  pyproject.toml
  src/
    bridge/
    health/
    config/
    agents/
      ui_audit/
      enemy_config/
    audit/
  templates/
    unity-project-bridge/
  tests/
  docs/
    architecture.md
    setup.md
    demo-scenarios.md
```

## 作品集演示方案

1. 创建一个安装了 Funplay 的全新 Unity 项目。
2. 运行模板初始化和健康检查。
3. 通过生成的 Bridge 连接 Codex。
4. 让 UI Audit Agent 检查一个故意存在问题的 UI Prefab。
5. 展示检查报告、截图和问题证据。
6. 让 Enemy Configuration Agent 检查一个近战敌人 Prefab。
7. 展示配置计划、人工确认步骤、修改后的精确读取结果，以及 Console / Play Mode 验证。

## 简历描述草稿

基于 Funplay MCP 构建可复用的 Codex-to-Unity MCP 接入模板，并实现 UI 可用性检查 Agent 与敌人配置 Agent。系统将自然语言需求转换为结构化 Unity Editor 工作流，通过 MCP 工具执行、人工确认风险修改，并使用状态读取、编译 / Console 检查和视觉 / 运行时证据验证结果。

## 新对话启动提示词

```text
我正在开发一个作品集项目，名称为 Codex-Funplay Unity Agent。
请使用 Funplay MCP for Unity 作为 Unity 执行层，不要修改 Funplay 源码。
第一阶段先开发可复用的 Codex-Funplay Bridge 模板。

约束：
- Windows、本机 Unity、本机 Funplay HTTP 服务。
- 不要修改 Claude Code、Coplay 或它们的配置文件。
- 第一版只支持一个 Unity 项目。
- 实现健康检查、项目级配置、stdio-to-HTTP MCP 转发和 JSONL 审计日志。
- 修改 Unity 场景、Prefab 或已有资源前，先检查目标，并展示准确的修改计划让我确认。

第一步：检查仓库状态，为 Bridge 模板提出一个小而明确的实现计划。
在我确认计划前不要修改文件。
```
