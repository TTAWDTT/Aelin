# DeepAgents 纯壳化蓝图 & TODO（Aelin → DeepAgents-only Backend）

> 目标：把 Aelin 从“外面一大圈 Aelin 时代逻辑 + 里面包一颗 DeepAgents”  
> 收缩成“**Aelin = 一个 DeepAgents graph 的 HTTP/SSE 外壳 + 一组工具实现**”。  
> 所有 Agent Loop / 规划 / 记忆决策都由 DeepAgents 自己承担，Aelin 只保留能力层工具。

---

## 1. Backend 结构蓝图（DeepAgents 作为唯一 Agent Loop）

### 1.1 定义统一的 DeepAgents Chat Graph

- [ ] 新建一个专门的 DeepAgents graph 构造模块（例如 `backend/app/services/deepagents_graph.py`）：
  - [ ] 把当前 `run_deepagents_loop` 中的 DeepAgents 初始化逻辑（`create_deep_agent(...)`）迁移到此模块，并命名为清晰的构造函数（如 `build_chat_agent()` 或 `build_chat_graph()`）。
  - [ ] 确认 graph 内部直接挂接以下工具能力：`web_search` / `attachment_search` / `google_workspace` / `device` / `plane` / 媒体 ingest（如适用），而不是通过 Aelin 的 ToolHub 二次包装。
  - [ ] 将 `skills` / `memory` / `backend=StateBackend` 等配置集中在这个构造函数里，便于后续统一调整 DeepAgents 行为。

验收标准：
- [ ] 代码层面有一个清晰的 `build_chat_agent()` 或等价函数，返回已配置好的 DeepAgents agent/graph。
- [ ] 其它模块（包括 `run_deepagents_loop`）只通过这个构造函数获得 DeepAgents 实例，不再自己 scattered 地调用 `create_deep_agent`。

### 1.2 `_try_agent_loop_chat` 收缩为纯“适配层”

- [ ] 梳理并标记 `_try_agent_loop_chat` 中仍属于“旧 Aelin loop”的逻辑分支（媒体 fallback、attachment fallback、planner、web-first answer 等）。
- [ ] 在保持当前 API 行为的大前提下，设计一个“最小化 preflight”的结构：
  - [ ] 保留：auth / workspace 归一化 / history & images 截断 / attachment_ids 归一化；
  - [ ] 保留：必要的媒体 URL 检测（只用于触发专用 ingest graph，而非复杂 fallback）。
  - [ ] 移除或迁移：所有 `_plan_tool_usage` / `_critic_tool_plan` / `_compose_web_first_answer` / `run_aelin_structured_tools` 等决策逻辑。
- [ ] 调整 `_try_agent_loop_chat`：  
  只负责：
  - [ ] 获取 `memory_summary`（AGENTS.md → system prompt），  
  - [ ] 调用 DeepAgents chat graph，  
  - [ ] 将返回的 answer + run graph 映射到 `AelinChatResponse` + `tool_trace`，推送 SSE。

验收标准：
- [ ] `_try_agent_loop_chat` 的代码量明显下降，主要职责可一句话概括为“拼装 payload → 调用 DeepAgents → 转换为 SSE/HTTP 响应”。
- [ ] 所有 Python 层“什么时候搜网/什么时候看附件/怎么规划工具”的决策逻辑不再存在于 `_try_agent_loop_chat` 内，而是迁移到 DeepAgents graph 或 skills。

---

## 2. 工具层收敛：保留能力，去掉 Aelin ToolHub 壳

### 2.1 盘点 Aelin ToolHub 中的工具能力

- [ ] 在 `AelinToolHub.tool_definitions()` 和 `AelinToolHub.execute()` 中标记出纯“能力型”工具：
  - [ ] `web_search`（联网搜索）。
  - [ ] `attachment_search`（文件检索）。
  - [ ] `google_workspace`（GWS）。
  - [ ] `device` / `screen_get`（设备 + 截图）。
  - [ ] `plane` / `pinchtab` 系列（browser plane）。
  - [ ] 媒体 ingest 相关（如果通过工具暴露）。
- [ ] 标记出“已不再适合作为 DeepAgents 决策入口”的旧工具：
  - [ ] `memory`（编辑 `/memory/AGENTS.md` 的 Aelin memory 工具）。
  - [ ] `context_get` / `profile` 等围绕旧记忆/画像模型的读取工具。

验收标准：
- [ ] 有一份简明列表，将 Aelin ToolHub 中的工具分为“保留为 DeepAgents 工具能力”与“待下线/不再暴露给 DeepAgents”的两类。

### 2.2 将能力型工具转为「DeepAgents-native 工具」

- [ ] 为每类能力抽象出最小的工具实现接口（不依赖 Aelin ToolHub 的 heavy wrapper）：
  - [ ] 示例：`deepagents_tools.web_search_tool`, `deepagents_tools.attachment_search_tool` 等。
  - [ ] 工具函数只依赖底层 service（`WebSearchService` / `AelinAttachmentService` / GWS CLI / plane runtime 等），而不是整个 `AelinToolHub`。
- [ ] 在 DeepAgents graph 构造阶段，直接注册这些工具为 LangChain/DeepAgents tools：
  - [ ] 从 `tools=[...]` 列表中移除“通过 AelinToolHub 反射执行”的工具包装。
  - [ ] 改为直接使用上述能力型工具函数作为 tool 实现。

验收标准：
- [ ] DeepAgents 的 `tools` 列表中，不再出现“在 tool 里再调用 `AelinToolHub.execute`”这一层。
- [ ] 典型场景（web_search + attachment_search + google_workspace + plane + device）全部由新的 DeepAgents-native 工具实现，行为与现在保持一致或更好。

### 2.3 下线 Aelin 记忆类工具（从 DeepAgents 视角）

- [ ] 从 DeepAgents 的工具集合中移除 `memory` 工具：
  - [ ] `tool_definitions()` 中不再返回 `memory` 对应 definition。
  - [ ] DeepAgents graph 不再把 `memory` 列入可调用工具列表。
- [ ] `context_get` / `profile`：
  - [ ] 从 DeepAgents tools 中去除（不给 agent 调用），只保留为 REST/API 或 UI 查询接口（如果当前 UI 仍依赖）。
  - [ ] 在文档里注明：记忆/画像的真实来源是 `/memory/AGENTS.md` 与 DeepAgents MemoryMiddleware，这些接口仅作为视图/只读投影，不参与 agent 决策。

验收标准：
- [ ] DeepAgents 在内部不会再看到名为 `memory` 的工具，也不会试图通过工具来更新长期记忆。
- [ ] 所有记忆读写都通过 DeepAgents 的 memory（AGENTS.md 文件 + MemoryMiddleware）完成，Aelin 工具只作为外部 UI/查询接口存在（如有需要）。

---

## 3. 记忆与上下文：完全围绕 AGENTS.md & DeepAgents Memory

### 3.1 记忆写入路径统一到 AGENTS.md

- [ ] 在 `agent_memory.py` / `openviking_bridge.py` 中检查所有记忆写入入口：
  - [ ] 确认所有长期记忆写入最终都汇聚到 `write_agents_memory(user_id, workspace, content)`。
  - [ ] 删除或标记弃用任何“直接写 DB 记忆表”的代码路径（除兼容性恢复场景外）。
- [ ] 约定：  
  所有“写记忆”操作应有且仅有两种合法途径：
  - [ ] DeepAgents graph 内部通过工具/文件操作修改 `/memory/AGENTS.md`（推荐路径）。  
  - [ ] 用户显式编辑 AGENTS.md（或一个 UI 包装），最终仍写入 `AGENTS.md` 文件。

验收标准：
- [ ] 代码级别没有新的 DB-based 记忆写入逻辑；`AGENTS.md` 是唯一的长期记忆真源。
- [ ] 文档中明确声明：DeepAgents 记忆基于虚拟文件 `/memory/AGENTS.md`，Aelin 只负责将其同步到磁盘。

### 3.2 上下文 API 只作为 AGENTS.md 的投影

- [ ] 审视 `aelin_context_service.build_context_bundle` 等上下文组装逻辑：
  - [ ] 确认 `memory_layers` / `layout_cards` / `focus_items` / `todos` 都是从 AGENTS.md + DB 的投影构造出来，而不是反过来驱动 agent loop。
  - [ ] 删除或简化任何仍会“反向影响 DeepAgents 决策逻辑”的上下文策略（例如，曾依赖 memory_layers 的 planner 分支）。
- [ ] 更新文档：  
  把上下文 API 定位为“**读 AGENTS.md + 历史数据的视图**”，用于 UI 展示和侧边栏，不再被 DeepAgents 当成额外的“隐含记忆源”。

验收标准：
- [ ] DeepAgents 的调用路径（从 HTTP 到 graph）只依赖 `/memory/AGENTS.md` 和 chat history，不再显式读取 `memory_layers` / `layout_cards` 之类结构。
- [ ] 即使暂时保留 context API，删掉它们也不会破坏 DeepAgents 的 chat 能力（只影响 UI 辅助信息）。

---

## 4. Legacy Aelin Agent Loop & 配置裁剪

### 4.1 移除 AelinAgentLoop 及相关兼容路径

- [ ] 删除 `aelin_core.AelinAgentLoop` 类，或者将其移动到 `archive/` 并在运行时代码中不再引用。
- [ ] 删除 `_aelin_chat_impl` 及任何直接调用它的代码路径，确保 router 只通过 DeepAgents loop 进行聊天。
- [ ] 更新 tests：
  - [ ] 找出仍 monkeypatch `AelinAgentLoop` 的测试，将其替换为直接 monkeypatch `run_deepagents_loop` 或新的 DeepAgents graph 构造函数。

验收标准：
- [ ] 运行时代码里找不到 `AelinAgentLoop` 的实际实例化或调用路径。
- [ ] 测试集不再依赖 AelinAgentLoop，而是直接针对 DeepAgents loop 进行 stub / monkeypatch。

### 4.2 裁剪旧 agent loop 配置项

- [ ] 清理 `settings.py` 中以 `aelin_agent_loop_...` 为前缀的旧配置：
  - [ ] 保留必要的硬约束（如整体工具次数上限），并直接喂给 DeepAgents graph（作为 graph config，而不是 Python policy）。
  - [ ] 删除与 legacy loop 专属的配置（如 shadow mode / per-round call 限制），或者在文档中标明“仅用于旧分支，待完全删除”并从运行时逻辑中移除。
- [ ] 对 remote_control / router 等地方仍使用 `"agent_loop_no_result"` 等标记的逻辑进行瘦身：
  - [ ] 改为使用 DeepAgents 的 `stop_reason` 或 run graph 状态来判断“是否成功完成”。

验收标准：
- [ ] settings 中仅保留少量与 DeepAgents graph 真正相关的配置项，其余全部删除或移入 archive。
- [ ] remote control / router 逻辑不再依赖 legacy agent loop 的魔法字符串，而是对 DeepAgents 结果进行显式判断。

---

## 5. Trace & Execution Pane 完全对齐 DeepAgents Run Graph

### 5.1 后端对 run graph 的一层映射

- [ ] 当 DeepAgents graph 支持 run graph / event 输出时：
  - [ ] 在 DeepAgents loop 中获取 run graph（节点类型、工具调用、plane 调用、子 agent 等）。
  - [ ] 设计一个简洁的中间结构（例如 `DeepAgentsRunTrace`），包含节点列表及基本元信息。
- [ ] `_try_agent_loop_chat` 中只做一次性映射：
  - [ ] 从 `DeepAgentsRunTrace` 映射到 `AelinToolStep[]` 或直接映射到 RunNode[]（如果准备让前端直接使用 RunNode）。

验收标准：
- [ ] 在典型查询下（纯聊天、多工具混合、plane 浏览等），后端能生成与 DeepAgents run graph 一致的 trace 视图（无额外手工 stage 拼接）。
- [ ] 后端映射逻辑尽量薄，主要工作由 DeepAgents 自己的 run graph 决定。

### 5.2 前端 Execution Pane 只依赖统一 Trace 模型

- [ ] 确保前端 trace 解析（`RunNode` 构造、plane/tool 视图）全部建立在统一的 trace 模型上：
  - [ ] 删除任何针对 `agent_loop_*` 等旧 stage 的硬编码判断。
  - [ ] Plane 链路展示完全基于 `plane_delegate/status/continue/close/catalog` 等节点，以及 DeepAgents 提供的状态信息。
- [ ] 对于未来 DeepAgents run graph 的字段扩展（如子 agent、filesystem 操作等），预留 RunNode 类型扩展能力，而无需再改后端 stage 字符串。

验收标准：
- [ ] Execution Pane 在所有场景下的展示都能在“看图就懂 DeepAgents 在干什么”的程度，不再出现“前端自己编 stage 名字”的情况。
- [ ] 后续 DeepAgents run graph 的 small change 仅需前端轻微适配，无需再引入新的 Aelin-specific stage。

---

> 一旦本 TODO 完成，Aelin backend 将彻底收敛为：  
> 「一颗 DeepAgents agent（graph） + 一组工具实现 + 极薄的 HTTP/SSE 外壳」，  
> Aelin 时代的 agent loop / planner / memory tools 将彻底退场，只留能力与 UI。***
