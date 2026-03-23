# DeepAgents 纯壳化蓝图 & TODO（Aelin → DeepAgents-only Backend）

> 目标：把 Aelin 从“外面一大圈 Aelin 时代逻辑 + 里面包一颗 DeepAgents”  
> 收缩成“**Aelin = 一个 DeepAgents graph 的 HTTP/SSE 外壳 + 一组工具实现**”。  
> 所有 Agent Loop / 规划 / 记忆决策都由 DeepAgents 自己承担，Aelin 只保留能力层工具。

---

## 1. Backend 结构蓝图（DeepAgents 作为唯一 Agent Loop）

### 1.1 定义统一的 DeepAgents Chat Graph

- [x] 新建一个专门的 DeepAgents graph 构造模块（例如 `backend/app/services/deepagents_graph.py`）：
  - [x] 把当前 `run_deepagents_loop` 中的 DeepAgents 初始化逻辑（`create_deep_agent(...)`）迁移到此模块，并命名为清晰的构造函数（如 `build_chat_agent()` 或 `build_chat_graph()`）。
  - [x] 确认 graph 内部直接挂接以下工具能力：`web_search` / `attachment_search` / `google_workspace` / `device` / `plane` / 媒体 ingest（如适用），而不是通过 Aelin 的 ToolHub 二次包装。
  - [x] 将 `skills` / `memory` / `backend=StateBackend` 等配置集中在这个构造函数里，便于后续统一调整 DeepAgents 行为。

验收标准：
- [x] 代码层面有一个清晰的 `build_chat_agent()` 或等价函数，返回已配置好的 DeepAgents agent/graph。
- [x] 其它模块（包括 `run_deepagents_loop`）只通过这个构造函数获得 DeepAgents 实例，不再自己 scattered 地调用 `create_deep_agent`。

### 1.2 `_try_agent_loop_chat` 收缩为纯“适配层”

- [x] 梳理并标记 `_try_agent_loop_chat` 中仍属于“旧 Aelin loop”的逻辑分支（媒体 fallback、attachment fallback、planner、web-first answer 等）。
- [x] 在保持当前 API 行为的大前提下，设计一个“最小化 preflight”的结构：
  - [x] 保留：auth / workspace 归一化 / history & images 截断 / attachment_ids 归一化；
  - [x] 保留：必要的媒体 URL 检测（只用于触发专用 ingest graph，而非复杂 fallback）。
  - [x] 移除或迁移：所有 `_plan_tool_usage` / `_critic_tool_plan` / `_compose_web_first_answer` / `run_aelin_structured_tools` 等决策逻辑（现已全部下线，仅 DeepAgents 自身负责规划与工具调用）。
- [x] 调整 `_try_agent_loop_chat`：  
  只负责：
  - [x] 获取 `memory_summary`（AGENTS.md → system prompt），  
  - [x] 调用 DeepAgents chat graph，  
  - [x] 将返回的 answer + run graph 映射到 `AelinChatResponse` + `tool_trace`，推送 SSE。

验收标准：
- [x] `_try_agent_loop_chat` 的代码量明显下降，主要职责可一句话概括为“拼装 payload → 调用 DeepAgents → 转换为 SSE/HTTP 响应”。
- [x] 所有 Python 层“什么时候搜网/什么时候看附件/怎么规划工具”的决策逻辑不再存在于 `_try_agent_loop_chat` 内，而是迁移到 DeepAgents graph 或 skills。

---

## 2. 工具层收敛：保留能力，去掉 Aelin ToolHub 壳

### 2.1 盘点 Aelin ToolHub 中的工具能力

- [x] 在 `AelinToolHub.tool_definitions()` 和 `AelinToolHub.execute()` 中标记出纯“能力型”工具：
  - [x] `web_search`（联网搜索）。
  - [x] `attachment_search`（文件检索）。
  - [x] `google_workspace`（GWS）。
  - [x] `device` / `screen_get`（设备 + 截图）。
  - [x] `plane` / `pinchtab` 系列（browser plane）。
  - [x] 媒体 ingest 相关目前不再通过 ToolHub 暴露，后续仅作为 DeepAgents 内部能力接入。
- [x] 标记出“已不再适合作为 DeepAgents 决策入口”的旧工具：
  - [x] `context_get` / `profile` 等围绕旧记忆/画像模型的读取工具（仅适合作为 UI/只读视图）。
  - [x] `skill`（用于浏览 skill 目录与正文，供人类/外层系统参考，不再作为 DeepAgents 主决策入口）。

验收标准：
- [x] 有一份简明列表，将 Aelin ToolHub 中的工具分为“保留为 DeepAgents 工具能力”与“待下线/不再暴露给 DeepAgents”的两类：
  - 保留为 DeepAgents 工具能力：`web_search` / `attachment_search` / `google_workspace` / `device` / `screen_get` / `plane` / `pinchtab` / `pinchtab_agent` / `pinchtab_session`。
  - 待下线或不再暴露给 DeepAgents：`context_get` / `profile` / `skill`（后续仅通过 REST/UI 使用）。

### 2.2 将能力型工具转为「DeepAgents-native 工具」

- [x] 为每类能力抽象出最小的工具实现接口（不依赖 Aelin ToolHub 的 heavy wrapper）：
  - [x] 已存在按领域拆分的实现：`tools_web.tool_web_search` / `tools_files.tool_attachment_search` / `tools_gws.tool_google_workspace` / `tools_device.tool_device` & `tools_device.tool_screen_get` / `tools_browser_plane.tool_plane`，它们直接操作底层 `WebSearchService` / `AelinAttachmentService` / GWS CLI / plane runtime / device runtime。
  - [x] DeepAgents 侧使用这些函数，而不是再通过 `tool_hub.execute(name, args)` 进行二次分发。
- [x] 在 DeepAgents graph 构造阶段，直接注册这些工具为 LangChain/DeepAgents tools：
  - [x] 从 `tools=[...]` 列表中去掉“通过 AelinToolHub.execute 反射执行”的包装，在 `build_chat_tools` 中根据 name 直接调用对应的 `tool_*` 函数。
  - [x] DeepAgents 工具 wrapper 只负责策略检查（`AelinToolPolicy.evaluate`）和记录 `tool_runs`，实际能力由领域函数承担。

验收标准：
- [x] DeepAgents 的 `tools` 列表中，不再出现“在 tool 里再调用 `AelinToolHub.execute`”这一层（现在是按 name 直连 `tool_web_search` / `tool_attachment_search` / `tool_google_workspace` / `tool_device` / `tool_screen_get` / `tool_plane`）。
- [x] 典型场景（web_search + attachment_search + google_workspace + plane + device）全部由新的 DeepAgents-native 工具实现，现有测试（含浏览器 plane 与 GWS/附件链路）全部通过，行为与之前保持一致。

### 2.3 下线 Aelin 记忆类工具（从 DeepAgents 视角）

- [x] 从 DeepAgents 的工具集合中移除 `memory` 工具：
  - [x] `tool_definitions()` 中不再返回 `memory` 对应 definition（当前 AelinToolHub 仅定义 `context_get` / `profile` 等旧视图工具，不再暴露写记忆的 `memory` 工具）。
  - [x] DeepAgents graph 不再把 `memory` 列入可调用工具列表（`build_chat_tools` 仅 allowlist `web_search` / `attachment_search` / `google_workspace` / `device` / `screen_get` / `plane`）。
- [x] `context_get` / `profile`：
  - [x] 从 DeepAgents tools 中去除（不给 agent 调用），只保留为 REST/API 或 UI 查询接口（通过 AelinToolHub.execute 供侧边栏/调试页面使用）。
  - [x] 在文档里注明：记忆/画像的真实来源是 `/memory/AGENTS.md` 与 DeepAgents MemoryMiddleware，这些接口仅作为视图/只读投影，不参与 agent 决策。

验收标准：
- [x] DeepAgents 在内部不会再看到名为 `memory` 的工具，也不会试图通过工具来更新长期记忆；所有长期记忆均来源于挂载在 `/memory/AGENTS.md` 上的虚拟文件。
- [x] 所有记忆读写都通过 DeepAgents 的 memory（AGENTS.md 文件 + MemoryMiddleware）完成，Aelin 侧的 `context_get` / `profile` 等工具只作为外部 UI/查询接口存在，不再影响 DeepAgents 的决策逻辑。

---

## 3. 记忆与上下文：完全围绕 AGENTS.md & DeepAgents Memory

### 3.1 记忆写入路径统一到 AGENTS.md

- [x] 在 `agent_memory.py` / `openviking_bridge.py` 中检查所有记忆写入入口：
  - [x] 确认所有长期记忆写入最终都汇聚到 `write_agents_memory(user_id, workspace, content)`（AgentMemoryService 的 `append_fact_to_memory` / `append_preference_to_memory` / `add_todo_to_memory` 以及 DeepAgents MemoryMiddleware 都通过 FileMemoryBridge 写入 `/memory/AGENTS.md`）。
  - [x] 删除或标记弃用任何“直接写 DB 记忆表”的代码路径（除兼容性恢复场景外）：`update_after_turn` 已明确为 no-op，layout-based memory 与 pin 推荐等旧表已从公共 API 移除；仅 `AgentConversationMemory.summary` 作为可选的简短摘要缓存保留，且不再回流到 DeepAgents 记忆。
- [x] 约定：  
  所有“写记忆”操作应有且仅有两种合法途径：
  - [x] DeepAgents graph 内部通过文件工具或 MemoryMiddleware 修改 `/memory/AGENTS.md`（推荐路径）。  
  - [x] 用户显式编辑 AGENTS.md（或一个 UI 包装），最终仍写入 `AGENTS.md` 文件（由 FileMemoryBridge 负责落盘和索引）。

验收标准：
- [x] 代码级别没有新的 DB-based 记忆写入逻辑；`AGENTS.md` 是唯一的长期记忆真源，DB 中的 AgentMemoryNote/ConversationMemory 仅作为辅助视图或历史遗留兼容存在。
- [x] 文档中明确声明：DeepAgents 记忆基于虚拟文件 `/memory/AGENTS.md`，Aelin 只负责将其同步到磁盘并在需要时投影为只读视图。

### 3.2 上下文 API 只作为 AGENTS.md 的投影

- [x] 审视 `aelin_context_service.build_context_bundle` 等上下文组装逻辑：
  - [x] 确认 `memory_layers` / `notes` / `todos` 都是从 AGENTS.md 投影出的视图：`get_summary` / `list_notes` / `list_todos` 在 DeepAgents 运行时都只使用 FileMemoryBridge + AGENTS.md（不再写入或依赖 layout-based DB 结构）。
  - [x] 删除或简化任何仍会“反向影响 DeepAgents 决策逻辑”的上下文策略：`build_system_memory_prompt` 只从 `/memory/AGENTS.md` 构造 prompt，不再读取 context API 或 `memory_layers`，planner 与 agent loop 也不再引用这些视图结构。
- [x] 更新文档：  
  把上下文 API 定位为“**读 AGENTS.md + 历史数据的视图**”，用于 UI 展示和侧边栏，不再被 DeepAgents 当成额外的“隐含记忆源”。

验收标准：
- [x] DeepAgents 的调用路径（从 HTTP 到 graph）只依赖 `/memory/AGENTS.md` 和 chat history，不再显式读取 `memory_layers` / `layout_cards` 等结构；这些仅用于 `build_context_bundle` 的 UI 显示。
- [x] 即使暂时保留 context API，删掉它们也不会破坏 DeepAgents 的 chat 能力（只影响 sidebar/调试信息），这在现有 tests 中已得到验证。

---

## 4. Legacy Aelin Agent Loop & 配置裁剪

### 4.1 移除 AelinAgentLoop 及相关兼容路径

- [x] 删除 `aelin_core.AelinAgentLoop` 类，或者将其移动到 `archive/` 并在运行时代码中不再引用（当前实现已从 `aelin_core` 中移除，运行时代码仅依赖 `run_deepagents_loop`）。
- [x] 删除 `_aelin_chat_impl` 及任何直接调用它的代码路径，确保 router 只通过 DeepAgents loop 进行聊天（该函数现在仅保留为抛出异常的 legacy stub，router 始终经由 `_try_agent_loop_chat` → DeepAgents）。
- [x] 更新 tests：
  - [x] 找出仍 monkeypatch `AelinAgentLoop` 的测试，将其替换为直接 monkeypatch `run_deepagents_loop` 或新的 DeepAgents graph 构造函数（`test_aelin_preflight_perf.py` 与 `test_aelin_core_plane_resume.py` 现已改为 stub `run_deepagents_loop` 并断言其入参，如 `plane_snapshot` 行为）。

验收标准：
- [x] 运行时代码里找不到 `AelinAgentLoop` 的实际实例化或调用路径（仅文档/基准脚本中保留历史提及，不在 app.services.* 里存在实现或引用）。
- [x] 测试集不再依赖 AelinAgentLoop，而是直接针对 DeepAgents loop（`run_deepagents_loop`) 进行 stub / monkeypatch。

### 4.2 裁剪旧 agent loop 配置项

- [x] 清理 `settings.py` 中以 `aelin_agent_loop_...` 为前缀的旧配置：
  - [x] 保留必要的硬约束（如整体工具次数上限、超时），并直接喂给 DeepAgents graph 或工具策略（例如 `aelin_agent_loop_max_tool_calls` / `aelin_agent_loop_max_write_calls` 现仅用于构造 `AelinToolPolicy`）。
  - [x] 标记与 legacy loop 行为强绑定的开关（如 `aelin_agent_loop_shadow_enabled`、`aelin_agent_loop_enabled` 等）仅作为兼容 flag，DeepAgents-only 分支在运行时代码中不再分支判断这些值。
- [x] 对 remote_control / router 等地方仍使用 `"agent_loop_no_result"` 等标记的逻辑进行瘦身：
  - [x] `_try_agent_loop_chat` 在 DeepAgents 无有效回答时统一发出一条 `AelinToolStep(stage="agent_loop", status="failed", detail="agent_loop_no_result", ...)`，供 remote_control 识别；成功路径只使用 DeepAgents 的 `stop_reason="completed"`。
  - [x] `remote_control._derive_remote_execution_status` 仅通过 trace 中是否存在该失败标记来区分 `"agent_loop_no_result"` 与 `"completed"`/`"empty_answer"`，不再依赖任何 legacy agent loop 状态机。

验收标准：
- [x] settings 中仅保留少量与 DeepAgents graph 真正相关的配置项，其余 `aelin_agent_loop_*` 开关在运行时代码中均不再驱动旧状态机，而是只作为工具/超时的硬约束或兼容开关存在。
- [x] remote control / router 逻辑不再依赖 legacy agent loop 的魔法字符串，而是对 DeepAgents 结果与统一的 `"agent_loop_no_result"` 失败标记进行显式判断，相关测试 `test_remote_control_execute_reports_agent_loop_failure` 通过验证这一行为。

---

## 5. Trace & Execution Pane 完全对齐 DeepAgents Run Graph

### 5.1 后端对 run graph 的一层映射

- [x] 当 DeepAgents graph 支持 run graph / event 输出时：
  - [x] 在 DeepAgents loop 中聚合工具调用与 plane 调用信息：当前通过 `AelinAgentLoopResult.tool_runs`（含 name/args/status/is_write/latency_ms）和 `plane_snapshot` / plane 相关 tool_runs 构成一条轻量级“执行路径”。
  - [x] 设计一个简洁的中间结构：后端统一输出 `AelinToolStep[]`，其中 stage 粒度约定为 `preflight.*` / `agent_loop` / `agent_loop_tool` / `plane_delegate/status/continue/close/catalog` 等，作为 DeepAgents run graph 的稳定投影。
- [x] `_try_agent_loop_chat` 中只做一次性映射：
  - [x] 从 DeepAgents 返回的 `trace_steps + tool_runs` 映射到 `AelinToolStep[]`（包括 plane/tool 细分 stage），不再自行拼装额外的虚构 stage 名称。

验收标准：
- [x] 在典型查询下（纯聊天、多工具混合、plane 浏览等），后端能生成与 DeepAgents 执行过程一致的 trace 视图：preflight → agent_loop → plane/tool 调用序列，由 `AelinToolStep[]` 描述。
- [x] 后端映射逻辑尽量薄，主要工作由 DeepAgents 自己的工具调用结果决定；一旦 DeepAgents 暴露更完整 run graph，仅需在 `run_deepagents_loop` 内部替换 `AelinToolStep` 的组装方式，而前端与路由无需改动。

### 5.2 前端 Execution Pane 只依赖统一 Trace 模型

- [x] 确保前端 trace 解析（`RunNode` 构造、plane/tool 视图）全部建立在统一的 trace 模型上：
  - [x] `traceUtils.buildRunNodes` 只接收 `AelinToolStep[]`，根据 stage 前缀（`preflight_` / `agent_*` / `plane_*` / `agent_loop_tool` / `attachment_prefetch` 等）推导出 `RunNode.type`，不再直接依赖 legacy agent loop 的内部结构。
  - [x] Plane 链路展示完全基于 `plane_delegate/status/continue/close/catalog` 等节点，以及 `detail` 中编码的 state/task_id/goal 信息（`extractPlaneTaskMeta` / `parsePlaneDetail`）。
- [x] 对于未来 DeepAgents run graph 的字段扩展（如子 agent、filesystem 操作等），预留 RunNode 类型扩展能力，而无需再改后端 stage 字符串：
  - [x] `RunNodeType` 已包含 `tool` / `plane` / `memory` / `fs` / `error` 等扩展位，前端仅需在 `buildRunNodes` 中识别新的 stage 前缀即可，无需动 ExecutionPane 结构。

验收标准：
- [x] Execution Pane 在所有场景下的展示都能在“看图就懂 DeepAgents 在干什么”的程度：Aelin tab 用 `RunNode` 展示 preflight+agent 步骤，Plane tab 展示 plane 任务状态 + 轨迹，Tools tab 展示按轮分组的工具调用明细。
- [x] 后续 DeepAgents run graph 的 small change 仅需在 `run_deepagents_loop` → `AelinToolStep[]` 的映射或 `traceUtils.buildRunNodes` 里做轻微适配，无需再引入新的 Aelin-specific stage 或前端特例。

---

> 一旦本 TODO 完成，Aelin backend 将彻底收敛为：  
> 「一颗 DeepAgents agent（graph） + 一组工具实现 + 极薄的 HTTP/SSE 外壳」，  
> Aelin 时代的 agent loop / planner / memory tools 将彻底退场，只留能力与 UI。***
