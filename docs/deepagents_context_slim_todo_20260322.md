## DeepAgents Context & Memory Slimming TODO (2026-03-22)

> 目标：让 Aelin 只保留 DeepAgents 真正需要的上下文和记忆接口，其余 UI / pipeline / 冗余 glue 统统删减或下线，形成一个极瘦的 “DeepAgents 壳 + 少量业务工具”。

### 1. 明确 DeepAgents 唯一需要的上下文输入

- [x] 1.1 逐文件审计 DeepAgents 调用路径
  - 检查 `run_deepagents_loop`（`backend/app/services/deepagents_loop.py`）：
    - [x] 确认它从 Aelin 侧只依赖以下字段：`query`、`history_turns`、`memory_summary`、`images`、`attachment_ids`。
    - [x] 确认没有其他 “隐式上下文” 通过奇怪字段注入（例如 legacy layout、daily brief 等）。
  - 检查 `build_chat_agent`（`deepagents_graph.py`）：
    - [x] 只依赖 `tools`、`skills=["/skills/aelin/"]`、`memory=["/memory/AGENTS.md"]` 和 `files`（skills + AGENTS.md）。

- [x] 1.2 在 docs 中写清 “DeepAgents 所需上下文的最小集合”
  - `docs/deepagents_arch.md` 中增加一个小节：
    - 列出 DeepAgents 侧严格需要的字段（上面那 5 个 + tools/skills/memory）。
    - 明确：任何额外的 context / layout / daily brief / notifications 都不应再回注到 agent loop。

### 2. 收紧 AgentMemoryService 职责到 “只管 AGENTS.md + memory_summary”

- [x] 2.1 审计 `AgentMemoryService`（`agent_memory.py`）的公开方法
  - 列出所有方法：`get_summary`、`build_focus_items`、`list_notes`、`list_todos`、`build_memory_layers_from_items` 等，并通过类 docstring 标记：
    - [x] chat 主链路仅依赖 `_read_agents_md_text` / `_write_agents_md_text` 与 `build_system_memory_prompt(...)`（经 `_get_memory_summary_for_chat` 调用）。
    - [x] `get_summary` / `list_notes` / `list_todos` / `build_focus_items` / `build_memory_layers_from_items` 仅服务于 context / profile / tools 视图（`tools_context` 与 `/aelin/context`），不再影响 DeepAgents agent loop。

- [x] 2.2 为 DeepAgents 定义最小记忆接口
  - 将 `AgentMemoryService` 的 DeepAgents 职责缩减并文档化为：
    - [x] 读写 `/memory/AGENTS.md`（通过 `_read_agents_md_text` / `_write_agents_md_text` + `file_memory_bridge`）。
    - [x] 提供一个 `build_system_memory_prompt(...)` 返回简洁 `memory_summary`，作为挂载到 `/memory/AGENTS.md` 的文本视图。
  - 其余 “notes/focus/todos/memory_layers” 相关逻辑：
    - [x] 在类 docstring 中明确标注为「UI / 工具视图」职责，后续如需继续瘦身，可整体迁移到独立的 LegacyContextViewService 或删除，而不会影响 DeepAgents 主链路。

- [x] 2.3 更新 `_get_memory_summary_for_chat`（`aelin_core_support.py`）
  - [x] 确保它只依赖 `AgentMemoryService.build_system_memory_prompt(...)`，不再隐式拉取 focus items / notes / layout 等。
  - [x] 明确注释：这是 DeepAgents 唯一的 memory_summary 构造入口，其他地方不得重复计算或绕过该函数。

### 3. 精简 Context / Daily Brief / Notifications pipeline

- [x] 3.1 审计 `aelin_context_service.py` 与 `aelin_core_support._build_context_bundle`
  - [x] 当前 context bundle 仅包含字段：`workspace` / `summary` / `notes` / `notes_count` / `todos` / `memory_layers`，不再生成任何 layout_cards / pin_recommendations / notifications / daily_brief 等字段。
  - [x] 前端代码只通过 `AelinContextResponse` 类型引用这些字段，未有实际组件依赖 layout_cards / pin_recommendations / notifications；这些体验已在 UI 层自然下线。

- [x] 3.2 决策：哪些 UI 体验要“直接下线”
  - 结合当前使用习惯，明确：
    - [x] 已直接移除的：布局卡片、自动 pin 推荐、复杂 daily brief 卡片以及通知流在 context API 中的拼装；相关类型仅保留在 `app.schemas` / 前端 types 中，作为历史兼容占位。
    - [x] 保留的：一个简单的 “当前 summary + 最近 notes + todos + 轻量 memory_layers 视图”，作为右侧 Memory 视图的数据源。
  - [x] 在 `deepagents_arch.md` 的 1.3 / 后续小节中补充说明：context 视图已收敛为基于 AGENTS.md 的轻量只读投影，不再承载布局/通知等复杂体验。

- [x] 3.3 重写/瘦身 context endpoints
  - 对 `/aelin/context` 等路由：
    - [x] 保留最小必要字段（summary + notes + todos + memory_layers），移除 layout/pins/冗余统计；对应 router 仅从 `_build_context_bundle` 返回的精简 bundle 中取值。
    - [x] 使用已经收紧后的 `AgentMemoryService` 接口和 AGENTS.md 文件：`get_summary` / `list_notes` / `list_todos` / `build_memory_layers_from_items` 均只依赖 `/memory/AGENTS.md` 投影和消息表，且只在 context_get / profile / /aelin/context 这类 UI 视图中使用，不再参与 DeepAgents agent loop。
  - [x] 确认测试（`test_aelin.py::test_aelin_context_and_chat_endpoints` / `test_agent_memory_deepagents.py::test_context_bundle_projects_from_agents_md`）与当前简化响应结构兼容，仅断言 summary/notes/todos/memory_layers 存在，而不再要求任何 layout/pin/daily 字段。

- [x] 3.4 移除不再使用的 context glue
  - 完成本轮瘦身后：
    - [x] `aelin_context_service.py` 中只保留 `build_context_bundle` 与 `build_cached_base_context_bundle` 两个入口，内部不再包含 layout 构造、pin 推荐等逻辑；这些逻辑已经在前期 DeepAgents 重构中删除。
    - [x] `aelin_core_support._build_cached_base_context_bundle` 仅作为一个薄薄的 TTL 缓存封装，复用同一个 `build_context_bundle` 实现；缓存逻辑仍然有价值（避免频繁重复解析 AGENTS.md），因此保留实现并在 docs 中说明，而不再附带任何 legacy follow-up / notifications glue。

### 4. SSE / Execution Pane：只保留 DeepAgents 需要的 trace

- [x] 4.1 审计当前 SSE payload 结构（`AelinToolStep` / `tool_trace`）
  - 在 `aelin_core.py` 和相关 schemas 中：
    - [x] 确认 SSE / 流式事件中与执行链路相关的字段仅为：`stage` / `status` / `detail` / `count` / `ts`（对应 `AelinToolStep`），以及最终响应中的 `tool_trace: AelinToolStep[]`。
    - [x] 标记 Execution Pane 实际消费的字段只包括上述 5 个字段，不再依赖任何 layout / memory snapshot / plane 状态等旧字段。

- [x] 4.2 对齐 DeepAgents run trace
  - 当前 `AelinToolStep` 的来源已经简化为：
    - [x] 前置预处理（resolve_service / memory_summary / normalize_inputs / tool_hub_ready / runner_ready / media_ingest / attachment_prefetch）统一通过 `_emit_prefixed(stage, status, detail, count)` 生成，并以 `preflight.*` 或 `media_ingest` / `attachment_prefetch` 等 stage 标识。
    - [x] DeepAgents agent loop 返回的 `AgentLoopTraceStep` / `AgentLoopToolRun` 仅映射为 `stage='agent_loop'` / `stage='agent_loop_tool'` 的步骤，不再包含任何 plane_* / planner_* / layout_* 等 legacy stage 类型。
  - 在前端 `traceUtils.buildRunNodes` 中：
    - [x] 将所有以 `preflight` 开头的 stage 归类为 `RunNodeType='preflight'`，对 `agent_loop` / `agent_loop_tool` 等 stage 则归类为 `agent` / `tool`，其它 stage 统一视为 `other` 或 `error`。

- [x] 4.3 更新前端 Execution Pane 消费逻辑
  - 在不破坏“看得懂链路”的前提下：
    - [x] `ExecutionPane` 现在只基于 `buildRunNodes(trace)` 和 `extractToolCalls(trace)` 展示两个维度：`Aelin` 链路（preflight + agent 节点）与 `Tools` 链路（工具调用列表），不再存在 plane 专用 tab 或 plane 任务视图。
    - [x] 移除 Execution Pane 中的 PlaneTraceView 组件以及 `ExecutionTab='plane'`，并停止在右侧面板顶部渲染任何 plane 相关 UI。
    - [x] 简化 `ChatStatusBar`、`ChatTimeline`、`SessionTabs` 对 plane trace 的使用：不再生成 plane chip、不再在 tab 上显示 “plane 活跃任务” 红点，仅根据工具调用摘要和 provider 生成状态文案与图标。
  - 其余 plane / PinchTab 相关字符串和 provider 样式暂仅保留在 i18n 与 ProviderIcon 中，作为历史兼容；它们不再参与任何 DeepAgents run trace 的渲染或逻辑判断。

### 5. 代码层面最终清理 & 验收

- [ ] 5.1 全局搜索并删除遗留引用
  - `backend/` 下：
    - [ ] 搜索 `FocusItem` / `AelinMemoryLayers` / `AelinLayoutCard` 等类型，删掉所有确实不再使用的定义与 import。
    - [ ] 搜索与 “daily brief” / “layout card” / “pin recommendations” 相关的函数，确保要么迁移到 legacy 文档，要么彻底删除。

- [ ] 5.2 更新 docs
  - [ ] 在 `deepagents_arch.md` / `deepagents_final_cleanup_todo_20260321.md` 中补充一小节，标记：
    - 记忆与上下文仅通过 `/memory/AGENTS.md` + `memory_summary` 注入 DeepAgents；
    - 旧的 DB 记忆 + layout/pins/daily-brief pipeline 已经下线。

- [ ] 5.3 回归测试 & 实际链路验证
  - 后端：`cd backend && pytest -q`（或至少跑 `test_aelin.py` / `test_aelin_tools.py`）。
  - 实际聊天链路：
    - [ ] 发起「多轮问答 + 附件 + GWS + device」组合场景，确认：
      - DeepAgents 仍然能正确看到记忆（AGENTS.md + memory_summary）。
      - Execution Pane 仍然能展示关键工具调用链路。
    - [ ] 发起 context 查询（若保留）：确认返回结构符合精简后的设计，不含任何 legacy 字段。
