# Goose 作为「Dev plane」的设计草案

> 目的：把 goose 集成到 Aelin 的 plane 体系中，成为负责“开发/工程类任务”的标准 plane。本文只讨论架构与交互，不涉及具体实现细节。

## 一、定位与角色

### 1.1 goose 是什么

按官方介绍，goose 是一个本地优先的多代理开发助手，强调：

- 对代码仓库有上下文理解；
- 能执行命令、跑测试、修改文件；
- 支持多模型、多工具、MCP 等扩展；
- 提供 CLI / 桌面端等运行方式。

对 Aelin 来说，goose 的角色可以理解为一个：

> 「专门负责写代码、改项目、跑测试和命令的外包工程团队」

它内部已经有自己的：

- 多 Agent/子代理体系；
- 工具集（执行 shell、编辑文件、调用 MCP 等）；
- 自己的一套计划/执行 loop。

### 1.2 在 Aelin 分层中的位置

回顾当前 Aelin 能力分层：

1. **基础 LLM 能力**：Aelin 自己的思考、对话与规划。
2. **工具（tools）**：一次调用做一件原子事（device、gws 等）。
3. **planes**：像 pinchtab 一样的完整系统，Aelin 像“用户”一样委派任务并监督。
4. **Aelin 的高层计划能力**：在 1–3 层之上进行跨 plane / 跨工具的编排。

在这套分层里：

- **goose 本体**：应当归入第 3 层 → Dev plane；
- **goose 内部的命令执行、文件编辑、MCP 等工具**：只在 goose 自己内部使用，Aelin 不直接操控；
- Aelin 对 goose 的交互姿势：**像一个开发者/产品经理给 goose 下达开发任务，而不是去驱动 goose 的每一条底层工具命令**。

## 二、目标能力

从用户视角，希望通过 Aelin + goose Dev plane，实现：

1. 用户提出工程类需求，例如：
   - 「帮我在这个仓库里加一个 /healthz 接口并补上测试」
   - 「帮我重构 frontend 的某个组件，让它支持 i18n」
   - 「帮我定位并修掉最新一次 CI 失败的原因」
2. Aelin 判断这是“工程/开发类任务”，适合交给 goose：
   - Aelin 先和用户澄清需求与约束（目录范围、语言、风险级别等）；
   - 整理出一份清晰的任务说明（task spec）。
3. Aelin 将任务 spec 交给 goose Dev plane：
   - goose 接管“如何修改代码/执行命令/跑测试”的细节；
   - 可能进行多轮规划和尝试。
4. Aelin 通过 plane trace 监督 goose 的执行过程：
   - 看到 goose 正在做什么（例如：分析代码、编辑文件、跑 pytest 等）；
   - 在 UI 的 plane 链路中展示步骤列表和关键日志。
5. goose 完成任务后，返回总结与结果：
   - 修改概要（改了哪些文件、做了什么变更）；
   - 测试状态（通过/失败）；
   - 遗留问题或风险提示。
6. Aelin 对 goose 的产出进行审阅：
   - 提炼一份用户友好的总结；
   - 必要时再衔接其它 plane 或工具（例如 pinchtab 做浏览器端验证，gws 更新文档等）。

## 三、Aelin ↔ goose 的交互模型

### 3.1 基本接口（抽象层面）

从 Aelin 的视角，可以抽象出 goose Dev plane 的一个统一接口：

```text
start_dev_task(task_spec) -> task_id
get_task_status(task_id) -> { status, steps[], logs, partial_results }
cancel_task(task_id) -> ack
```

其中：

- `task_spec`：Aelin 整理后的任务描述，包含：
  - 用户自然语言需求；
  - 工作目录 / 项目路径；
  - 编程语言 / 技术栈；
  - 允许改动的范围与禁止改动的区域；
  - 风险级别（是否允许破坏性改动）；
  - 资源限制（时间上限、步骤上限等）。
- `task_id`：对应 goose 那边的一次任务会话。
- `status`：如 `running / completed / failed / cancelled`。
- `steps[]`：goose 任务内部步骤的抽象（用于 plane trace 展示），例如：
  - `分析代码库结构`
  - `编辑 backend/app/services/aelin_core.py`
  - `运行 pytest backend/tests/test_aelin_core.py`
- `logs` / `partial_results`：用于展示给用户的关键信息（片段），同时不泄露过多内部噪音。

具体实现形式可以是：

- 通过 goose CLI，使用命令行参数 + 输出文件/流来完成；
- 或通过 goose 暴露的 HTTP/本地 server API（如果有）。

### 3.2 任务生命周期

1. **任务准备（Aelin 内部）**
   - Aelin 从对话历史中提取任务目标；
   - 询问并固化关键约束；
   - 构造 `task_spec`。

2. **任务发起（Aelin → goose）**
   - 调用 plane 封装的 `start_dev_task`；
   - 得到 `task_id` 与初始状态；
   - 在 chat UI 中插入一个 plane 任务 chip（例如：「已委派给 goose Dev plane」）。

3. **进度监督（goose → Aelin → 用户）**
   - 定时轮询 `get_task_status(task_id)`；
   - 将 `steps[]` 与关键 log 映射到 plane trace 面板；
   - 允许在 UI 中看到 goose 正在做什么，而不打扰它的内部决策。

4. **任务完成或失败**
   - 当 `status` 变为 `completed` 或 `failed`：
     - 收集最终 summary、变更概要、测试结果；
     - 在 chat 窗中以自然语言总结；
     - 在 plane trace 中保留细节链路，供用户需要时展开查看。

5. **任务终止（可选）**
   - 用户或 Aelin 判定任务不再需要，可以调用 `cancel_task(task_id)`。

## 四、与其它 plane / 工具的协作关系

goose Dev plane 是众多 plane 之一，它与现有能力的关系大致如下：

- **与 pinchtab（浏览器 plane）**：
  - goose：偏向“仓库/代码/命令”的工作；
  - pinchtab：偏向“浏览器交互/网页操作”的工作；
  - Aelin 可以先让 goose 完成后端/脚本改动，再通过 pinchtab 去网页上做端到端验证。

- **与 gws 等工具的关系**：
  - gws 属于工具层（访问 Gmail/Drive/Calendar 等）；
  - goose 内部可以自己调用 gws（如果在其工具集中），但在 Aelin 的设计中，更推荐：
    - Aelin 统一协调：goose 负责改代码，gws 负责同步文档/写日历/发通知等；
    - 保持“谁干什么”的边界清晰。

- **与其它未来 plane（例如 CLI-Anything plane）**：
  - CLI-Anything plane：负责“造工具”；
  - goose Dev plane：负责“用工具/用代码真正干活”；
  - Aelin 可以在更高层 orchestrate：当需要一个新工具时先找 CLI-Anything plane，再用 goose 来把它集成进项目。

## 五、能力边界与避免职责混乱

为了保持系统可理解且可维护，需要明确 goose Dev plane 的「能力边界」：

**适合交给 goose 的任务：**

- 读/改项目中的代码、配置、脚本；
- 运行测试、lint、构建命令；
- 执行项目内的 CLI 工具；
- 在项目目录里创建/修改文档（如 README、开发文档、迁移说明等）。

**不应该让 goose 直接做的事情（由 Aelin 或其它 plane/tools 负责）：**

- 直接与用户对话解释高层需求（这部分交给 Aelin）；
- 进行浏览器自动化（属于 pinchtab）；
- 访问外部 API/服务（更适合由 MCP/tool 层统一管理，goose 间接使用即可）；
- 管理 Aelin 自身的 plane 与工具注册/卸载（由 Aelin 自身完成）。

这样的边界有助于避免：

- goose 与 Aelin 互相“抢活”；
- 某个 plane 同时做了太多事，导致难以监督和调试。

## 六、UI 与交互呈现（配合 plane 体系的整体设计）

配合之前的 `chat_plane_ui_design` 思路，goose Dev plane 在前端大致可以这样呈现：

1. **Chat 时间线中的 plane 任务 chip**
   - 当 Aelin 决定把任务委派给 goose 时：
     - 在聊天中插入「已委派给 goose Dev plane：XXX」的任务块；
     - 显示任务简述与状态（等待中/进行中/已完成/失败）。

2. **右侧 Trace 面板中的「goose 链路」tab**
   - 列出 goose 上报的 `steps[]`：
     - 每步有简要说明（例如“编辑文件”、“运行 pytest”）；
     - 重要 log 片段可折叠展开；
     - 失败步骤高亮。

3. **消息完成后的自动折叠**
   - 当 goose 任务完成、Aelin 已给出用户总结后：
     - plane trace 面板默认折叠为简短摘要；
     - 用户若有兴趣，可以展开查看完整链路。

4. **任务取消/重试**
   - UI 可提供「取消任务」按钮：
     - 用户点击后，Aelin 调用 `cancel_task`；
   - 若任务失败，可提供「在当前上下文基础上重试」的按钮：
     - Aelin 根据之前失败信息重构新的 `task_spec` 再次提交。

## 七、安全与控制

goose Dev plane 由于具备“改代码+执行命令”的强大能力，必须有严格的安全控制：

1. **工作目录白名单**
   - 明确指定 goose 只对某些项目目录有权限；
   - 不允许它随意访问系统其他路径。

2. **命令/操作范围限制**
   - 尽量让 goose 专注于“项目内部命令”（如 npm/pnpm、pytest、go test 等）；
   - 避免执行与项目无关的高危命令（删除系统文件、修改系统配置等）。

3. **变更预览与回滚策略（中长期优化）**
   - 提供变更 diff 预览；
   - 支持一键回滚（例如通过 git stash/branch 等）。

4. **配额与超时**
   - 对每个任务设定最大执行时间、最大步骤数；
   - 防止意外长时间占用资源。

## 八、落地路线建议

短期（设计与文档阶段）：

1. 固化 goose Dev plane 的定位与能力边界（本文即为初步设计）。
2. 梳理 goose 提供的接口形态（CLI/本地 server）并选定一种最适合 Aelin 的集成方式。

中期（最小可用集成）：

1. 在 backend 中定义统一的 Dev plane 抽象接口（start/status/cancel）。
2. 提供一个 MVP 版本的 goose 封装：
   - 仅支持在单仓库内执行简单任务；
   - 将关键步骤映射到 plane trace。
3. 在前端按现有 plane UI 方案接出 goose 的基本展示：
   - 任务 chip；
   - 简单的步骤列表。

远期（成熟化与多 plane 协作）：

1. 扩展 goose Dev plane 的能力（更复杂任务、更多语言/框架支持）。
2. 与 pinchtab 等 plane 形成完整链路：
   - goose 负责改代码；
   - pinchtab 做端到端验证；
   - gws 等工具负责同步文档与协作。
3. 在 plane 管理层面抽象出统一的「plane 接入规范」，供后续新 plane 循环复用。

---

本设计文档的目标是：先把 goose 作为 Dev plane 的角色讲清楚，尤其是它与 pinchtab、gws 等现有能力之间的边界与协作方式。  
后续在真正开始实现时，可以按照这里的思路逐步拆解为具体的 PR 和实现任务。 

