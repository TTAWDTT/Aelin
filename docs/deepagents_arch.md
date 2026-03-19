# DeepAgents 核心重构总览（Aelin 集成蓝图）

> 目标：让 Aelin 从「自研 agent loop」彻底切换为「DeepAgents 中心」，自己只做外壳和本地能力；  
> DeepAgents 负责规划、多轮、tool / plane 调用、skills、trace 与 subagents。

---

## 0. 范围与前提

- 仅针对 **agent loop 与工具/plane 集成层**，不改：
  - HTTP API 形状（`/api/v1/aelin/chat/stream` 等）
  - SSE 协议的基本字段（`tool_trace` / `actions` / `expression`）
  - 数据库 schema 与 AgentMemory 行为
- **默认假设 DeepAgents 为唯一 agent 核心**，不再保留旧 loop 的双轨逻辑。

验收标准：
- [ ] 代码中没有任何 `AelinAgentLoop`、`aelin_loop_*`、旧自研状态机残留。
- [ ] 所有「agent loop 行为」的入口都统一指向 `run_deepagents_loop`。
- [ ] 单元测试与 API 形状与当前分支保持兼容或更简洁（见后文各条验收）。

---

## 1. DeepAgents + Skills 一体化

### 1.1 把现有 SKILL 文档映射为 DeepAgents skills

待办：
- [ ] 在 `backend/deepagents_skills/` 下建立统一 skill 根目录。
- [ ] 为每类能力建立子目录，例如：
  - [ ] `google_workspace/README.md`（gws 使用说明与注意事项）
  - [ ] `plane_browser/README.md`（browser plane 行为规范）
  - [ ] `plane_goose/README.md`（goose plane 行为规范）
  - [ ] `file_tools/README.md`（文件工具使用约定）
- [ ] 从已有的 `docs/gws*.md`、`cli_anything_plane.md`、`goose_plane.md` 等文档中抽取「对 LLM 有用的操作说明」，整理到对应 skill 目录。
- [ ] 在 `deepagents_loop.py` 中：
  - [ ] 初始化 `StateBackend` 时挂载 skill 目录（或通过配置传入路径）。
  - [ ] 调用 `create_deep_agent(..., skills=[...])` 把这些 skill 暴露给 DeepAgents。

验收标准：
- [ ] 对于 gws / plane 等工具，agent 在没有 Aelin 手工 prompt 注入的情况下也能稳定调用（尤其写操作）。
- [ ] 移除 `aelin_core` 中依赖的「手写技能 prompt 注入」逻辑后，gws / plane 的行为仍然正确。
- [ ] 所有 skill 文档修改只需要动 `backend/deepagents_skills/` 目录，无需改 Python 代码。

### 1.2 用 skills 替代旧的 tool_skill_bodies 注入

待办：
- [ ] 在 `aelin_core._try_agent_loop_chat` 中：
  - [ ] 标记或删除原先构造 `tool_skill_bodies` 的代码（render_skill_catalog_prompt / plane_catalog_prompt）。
  - [ ] 确保不会再把大段技能说明拼进 system prompt，而是通过 DeepAgents skills 提供。
- [ ] 为未来需要的特定行为（如「优先使用 web_search」）设计独立 skill，而不是再叠加 prompt hack。

验收标准：
- [ ] 删除 `tool_skill_bodies` 相关逻辑后，DeepAgents 能通过 skill 系统获得必要的工具使用说明。
- [ ] gws 写工具调用（如 `docs_create`）在正常配置下成功率与当前相当或更高。

---

## 2. 工具与 Plane：以 DeepAgents 为中心的工具宇宙

### 2.1 AelinToolHub → DeepAgents Tool 的完整接入

待办：
- [ ] 在 `deepagents_loop.py` 中：
  - [ ] 遍历 `tool_hub.tool_definitions()` 时，按工具类型分类（普通工具 / plane 工具）。
  - [ ] 为所有对外暴露的 Aelin 工具建立 LangChain Tool 封装（不仅限于当前的 subset）：
    - [ ] `context_get`
    - [ ] `profile`
    - [ ] `device`
    - [ ] `web_search`
    - [ ] `attachment_search`
    - [ ] `google_workspace`
    - [ ] `plane`（browser / goose / cli-anything 等 plane 都通过此入口）
    - [ ] 其他已有 file/attachment 工具（视实际情况添加）。
  - [ ] 保证每一次调用都通过 `AelinToolPolicy` + `ToolPolicyUsage` 进行权限与次数控制。
- [ ] 为 plane 工具提供更语义化的 description，使 DeepAgents 清楚「这是一个可长时间运行的委派 plane」。

验收标准：
- [ ] 所有曾经可通过 Aelin 调用的工具，在 DeepAgents 环境下也能被调用成功（功能不退步）。
- [ ] 工具调用次数、写操作次数严格受 `AelinToolPolicy` 限制，超限后有可读错误信息。
- [ ] 在不借助 Aelin 旧 prompt 的情况下，DeepAgents 能自然选择合适的工具（如 web_search vs plane）。

### 2.2 Plane 当作「特殊 Tool + Subagent」

待办：
- [ ] 定义 plane 工具的标准 schema（`action=delegate/status/continue`、`plane=browser/goose/...` 等）。
- [ ] 为 plane 工具的 description 中明确指出：
  - [ ] plane 是持久任务（带 `task_id`），需要 status / continue 轮询。
  - [ ] plane 的结果包含 summary / state / user_prompt 等字段。
- [ ] 将 browser plane、goose plane 等现有 plane 全部收敛到一个统一的 `plane` 工具接口下，由参数区分。
- [ ] 确保 DeepAgents 的子 agent / todo 中间件可以围绕 plane 工具生成子任务，而无需在 Aelin 里硬编码。

验收标准：
- [ ] 通过 DeepAgents 调用 browser plane 打开页面并总结内容时，能稳定完成多轮 status / continue 流程。
- [ ] 对同一 plane 多次查询时，可以在 DeepAgents 层面自然地「续上」已有 task，而不依赖 Aelin 旧的强制续上逻辑。

---

## 3. Trace：DeepAgents 原生运行图 → Aelin Execution Pane

### 3.1 从 DeepAgents 获取标准化 run trace

待办：
- [ ] 调研 DeepAgents / LangGraph 提供的 run graph API：
  - [ ] 确定如何在一次 `agent.invoke()` 内部获取完整的节点与边事件（含工具、子 agent、middleware）。
- [ ] 在 `run_deepagents_loop` 中：
  - [ ] 增加一个内部结构，如 `DeepAgentsRunTrace`，用来存储 run graph 的核心信息（节点类型、工具名、plane、阶段等）。
  - [ ] 将 `AgentLoopToolRun` 与 `DeepAgentsRunTrace` 一并返回。

验收标准：
- [ ] 每次 agent loop 调用后，能够在后端打印或序列化出完整 run trace（无需改前端即可人工检查）。
- [ ] run trace 至少包含：
  - [ ] 所有工具调用节点（工具名、参数摘要、状态）。
  - [ ] 所有 plane 委派节点（plane 名、task_id）。
  - [ ] 关键 middleware 步骤（如 todo/subagents/filesystem/summarization 的切入点）。

### 3.2 映射 run trace → Aelin 的 `tool_trace`（SSE）

待办：
- [ ] 在 `aelin_core._try_agent_loop_chat` 中：
  - [ ] 将 `DeepAgentsRunTrace` 转换为当前 SSE 使用的 `AelinToolStep` 列表。
  - [ ] 为不同类型的节点定义合理的 `stage`：
    - [ ] `agent_plan`：内部规划/分析步骤。
    - [ ] `agent_tool`：普通工具调用。
    - [ ] `plane_delegate`：plane 委派开始。
    - [ ] `plane_status` / `plane_continue`：plane 状态查询。
    - [ ] `agent_summary`：最终总结/回答生成步骤。
- [ ] 保证前端 Execution Pane 能用现有协议展示出完整链路。

验收标准：
- [ ] 在你常用的几类测试场景（gws、plane browser、web_search、device）下，右侧链路能看到清晰的阶段与工具调用顺序。
- [ ] 与当前分支的链路感相比，信息更加丰富，但不会出现狂闪/乱跳等 UX 退步。

---

## 4. Subagents：用 DeepAgents 原生多 agent 模型承载 plane / 特殊工具

### 4.1 把 plane 视为「一种子 agent 类型」

待办：
- [ ] 明确定义 plane 的「子 agent」语义：
  - [ ] browser plane：浏览器 + DOM 总结型子 agent。
  - [ ] goose plane：针对特定 API/网站的浏览 +交互子 agent。
  - [ ] CLI-Anything plane：本地 CLI 交互子 agent。
- [ ] 在 skill 文档中向 DeepAgents 描述这些 plane 的适用场景与能力边界。
- [ ] 允许 DeepAgents 在 todo/subagents middleware 中为这些 plane 生成专门的子任务。

验收标准：
- [ ] 在类似「打开某站点并总结要闻」这类任务中，DeepAgents 能自然分解出 plane 子任务，而无需 Aelin 硬编码步骤。
- [ ] 对 plane 任务的中断与恢复（登录/验证码、用户手动操作后「已登录，继续」）能通过子 agent + plane status/continue 协作解决。

---

## 5. Provider / 模型适配与配置整合

### 5.1 统一 Provider 处理

待办：
- [ ] 在 `_build_chat_model(service, provider)` 中：
  - [ ] 按 provider 选择对应 LangChain ChatModel（Anthropic / OpenAI / DeepSeek 等）。
  - [ ] 统一从 `LLMService.config` 里读取 base_url、api_key、model、timeout 等参数。
- [ ] 确保测试路径 `fake-model` 分支仍然可用，用于 unit test。

验收标准：
- [ ] 在配置不同 provider 时，无需改 Aelin 代码，只改配置即可支持切换（如从 Anthropic 换到 DeepSeek）。
- [ ] 所有与 agent loop 相关的测试（特别是 `test_aelin.py`）继续通过。

---

## 6. 渐进迁移与兼容性策略

### 6.1 渐进关闭旧逻辑

待办：
- [ ] 为各个阶段的重构增加 feature flag（如 `AELIN_DEEPAGENTS_SKILLS_ENABLED` 等），方便在本地/分支上逐步打开。
- [ ] 在每个阶段完成后：
  - [ ] 更新相关 docs（包括本文件和已有的 `deepagents_core_todo.md`）。
  - [ ] 移除已不再需要的临时代码与 TODO。

验收标准：
- [ ] 所有深度变更都可以通过开关回退（至少在开发期），不会一次性「炸掉」整条链路。
- [ ] docs 内的 TODO 与实际代码实现保持同步，没有明显过时内容。

---

## 7. 完成度检查（高层验收）

当以下全部完成时，可以认为「Aelin 围绕 DeepAgents 的重构」达到第一版目标：

- [ ] 旧 Aelin agent loop 完全移除，DeepAgents 成为唯一 agent 核心。
- [ ] SKILL 文档完全迁移到 DeepAgents skills 体系，Aelin 不再拼混乱的大段 prompt。
- [ ] 所有工具与 plane 以 DeepAgents Tool 的形式存在，并受统一 policy 控制。
- [ ] 右侧 Execution Pane 直接基于 DeepAgents run trace 展示链路，信息清晰丰富。
- [ ] plane / 子 agent 行为围绕 DeepAgents 的 subagents middleware 来设计，而不是 Aelin 侧状态机。
- [ ] provider 切换和配置仅需改 LLM 配置，不需要动 agent loop 代码。

