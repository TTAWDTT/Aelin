# DeepAgents 核心重构总览（Aelin 集成蓝图）

> 目标：让 Aelin 从「自研 agent loop」彻底切换为「DeepAgents 中心」，自己只做外壳和本地能力；  
> DeepAgents 负责规划、多轮、tool / plane 调用、skills、trace 与 subagents。

---

## 0. 范围与前提

- 仅针对 **agent loop 与工具集成层**，不改：
  - HTTP API 形状（`/api/v1/aelin/chat/stream` 等）
  - SSE 协议的基本字段（`tool_trace` / `actions` / `expression`）
- **默认假设 DeepAgents 为唯一 agent 核心**，不再保留旧 loop 的双轨逻辑。
- 浏览器 plane / PinchTab 相关能力已在本分支中下线，相关文档迁移到 `docs/archive/`，仅作为历史参考。
- **记忆的唯一权威来源已收敛为 DeepAgents 虚拟文件体系：**
  - 长期记忆、会话摘要、待办等全部只写入 `/memory/AGENTS.md`（按 workspace 分隔）。
  - 不再使用任何 DB 表（如 `AgentConversationMemory` / `AgentMemoryNote`）作为记忆源，旧表仅作为历史数据（可选保留或迁移，不再读写。

验收标准：
- [ ] 代码中没有任何 `AelinAgentLoop`、`aelin_loop_*`、旧自研状态机残留。
- [ ] 所有「agent loop 行为」的入口都统一指向 `run_deepagents_loop`。
- [ ] 单元测试与 API 形状与当前分支保持兼容或更简洁（见后文各条验收）。

---

## 1. DeepAgents + Skills 一体化

### 1.1 把现有 SKILL 文档映射为 DeepAgents skills（当前状态：已完成第一轮收敛）

当前实现：
- DeepAgents 运行时的技能根目录为 `backend/deepagents_skills/`，对应虚拟路径 `/skills/aelin/`。
- 该目录下的每个子目录表示一个技能主题（slug），例如：
  - `backend/deepagents_skills/google_workspace/` → `/skills/aelin/google-workspace/`
  - `backend/deepagents_skills/file_tools/` → `/skills/aelin/file-tools/`
- 每个子目录中包含一个 `SKILL.md`（DeepAgents / Agent Skills 规范），可选附带 `README.md` 等辅助文档。
- `app/services/deepagents_graph.build_chat_agent()` 会：
  - 将所有 `.md` 文件挂载为 DeepAgents `StateBackend` 的文件，例如 `/skills/aelin/google-workspace/SKILL.md`。
  - 统一传入 `skills=["/skills/aelin/"]` 给 `create_deep_agent(...)`，由 DeepAgents 的 `SkillsMiddleware` 负责枚举技能目录并解析 `SKILL.md`。

效果：
- 对于 GWS / 文件工具等能力，DeepAgents 在没有 Aelin 手工 prompt 注入的情况下就能看到完整的技能列表与说明。
- 旧的「tool_skill_bodies 注入」逻辑已经从 Agent Loop 中移除，技能知识的唯一来源就是 DeepAgents skills + 虚拟文件系统。
- 所有 DeepAgents skill 文档修改只需编辑 `backend/deepagents_skills/*/SKILL.md`，无需改 Python 代码。

### 1.2 用 skills 替代旧的 tool_skill_bodies 注入

待办：
- [ ] 在 `aelin_core._try_agent_loop_chat` 中：
  - [ ] 标记或删除原先构造 `tool_skill_bodies` 的代码（render_skill_catalog_prompt / plane_catalog_prompt）。
  - [ ] 确保不会再把大段技能说明拼进 system prompt，而是通过 DeepAgents skills 提供。
- [ ] 为未来需要的特定行为（如「优先使用 web_search」）设计独立 skill，而不是再叠加 prompt hack。

验收标准：
- [ ] 删除 `tool_skill_bodies` 相关逻辑后，DeepAgents 能通过 skill 系统获得必要的工具使用说明。
- [ ] gws 写工具调用（如 `docs_create`）在正常配置下成功率与当前相当或更高。

> 代码约定：围绕 Agent / 工具 / 记忆 的 service 文件（例如 `aelin_core.py`、
> `aelin_chat_planning.py`、`agent_memory.py` 等）应尽量保持在 600 行以内，
> 如需继续扩展，请优先拆分到职责单一的 `*_support.py` / `tools_*.py` 等
> 子模块，而不是继续向单一大文件堆叠逻辑。

---

## 2. 工具与 Plane（历史/草案）：以 DeepAgents 为中心的工具宇宙

### 2.1 AelinToolHub → DeepAgents Tool 的完整接入

当前状态：
- `AelinToolHub` 只承担「把 db/user/workspace 等上下文注入到工具实现」+「提供 OpenAI-style tool_definitions」两件事。  
- 所有能力型工具的实现都拆分在 `backend/app/services/tools_*.py` 中：
  - `tools_web.py`（`web_search`）
  - `tools_files.py`（`attachment_search`）
  - `tools_gws.py`（`google_workspace`）
  - `tools_device.py`（`device` / `screen_get`）
  - `tools_skill.py`（`skill`）
  - `tools_context.py`（`context_get` / `profile`，用于上下文/画像视图）
- `deepagents_graph.build_chat_tools()` 只从 `AelinToolHub.tool_definitions()` 中挑选核心能力型工具（`web_search` / `attachment_search` / `google_workspace` / `device` / `screen_get`），为它们构建 LangChain Tool，并通过 `AelinToolPolicy` + `ToolPolicyUsage` 统一做次数与写操作控制。

工具契约：
- 工具的正式契约（参数、错误语义）以 `deepagents_graph.build_chat_tools()` 中的 Tool 描述为准，Aelin 不再单独维护第二套 planner 或签名。  
- 上层如果需要结构化工具信息（前端 Execution Pane / 调试），统一从 `AelinToolHub.tool_definitions()` 读取，而不是再从散落的 prompt 片段中拼接。

### 2.2 Plane 当作「特殊 Tool + Subagent」

> 提示：当前 DeepAgents 纯壳分支中并未启用 plane 工具，browser plane /
> PinchTab 相关实现也已下线。本小节保留作为未来如果再次引入 plane 概念时
> 的设计草案，而非当前实现的要求。

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

### 2.3 Web / Plane 工具契约与策略上限（当前实现状态）

> 本小节对应 `deepagents_tool_contract_todo_20260321.md` 中的工具契约与上限调整，记录当前约定，方便后续维护。

- `web_search` 工具（通过 `AelinToolHub` 暴露给 DeepAgents）：
  - `action` 仅允许 `"search"` 或 `"search_and_fetch"` 两种取值。
  - 必须提供非空的 `query` 字段（中文或英文均可）；缺失时工具会返回 `missing query` 错误。
  - `max_results` 建议范围为 `1–15`，`fetch_top_k` 范围为 `0–6`，且不得大于 `max_results`。
  - DeepAgents 收到 `missing query` / `unsupported action` 一类错误时，应视为参数错误并在下一次调用中修正参数，而不是放弃工具。

- `plane` 工具（browser plane）：
  - 支持的 `action` 枚举为：`"delegate"`, `"status"`, `"continue"`, `"close"`, `"catalog"`。
  - 首次启动浏览任务时必须使用 `{"action": "delegate", "plane": "browser", "goal": "..."}` 形式。
  - 只有在已有合法 `task_id` 的情况下才允许使用 `status` / `continue` / `close`，否则会返回 `missing task_id`。
  - 任意未在枚举中的 `action` 都会返回 `unsupported plane action` 错误，错误消息中会带上允许的 action 列表。

- 工具调用策略上限（Aelin → DeepAgents）：
  - `settings.aelin_agent_loop_max_calls_per_round = 32`
  - `settings.aelin_agent_loop_max_tool_calls = 128`
  - `settings.aelin_agent_loop_max_write_calls = 32`
  - `settings.aelin_agent_loop_allow_write_tools = True`
  - `_try_agent_loop_chat` 仅使用这些配置构造 `AelinToolPolicy`，不再有额外的硬编码上限。  
    在常规对话和典型工具场景下，DeepAgents 几乎不受限地尝试工具，只有在极端多轮调用下才会触发总次数保护。

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

> 提示：这里的 plane 同样是“未来可能的扩展方向”。在当前分支中，Aelin 只
> 通过 DeepAgents 的常规工具与记忆能力工作，不再存在浏览器 plane / PinchTab
> 这类长期托管子系统。

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
