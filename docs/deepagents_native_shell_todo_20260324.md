# DeepAgents 原生壳 + 前端协议迁移 TODO (2026-03-24)

> 目标：后端直接使用 DeepAgents/LangGraph 提供的原生 `agent.stream(...)` 事件流格式，前端基于 DeepAgents 推荐事件模型重建聊天链路与 Execution Pane UI，同时删除所有 Aelin 旧式 agent loop / SSE 协议 / tool_trace 壳层代码，仅保留 DeepAgents graph + 能力服务（web_search / attachments / device / GWS / skills）。

## 1. DeepAgents 原生壳设计与后端路由

- [x] 1.1 选定并记录 DeepAgents 推荐的 streaming 协议
  - [x] 对照 DeepAgents 官方文档，确认当前推荐的 `agent.stream()` streaming 协议（例如 `version: "v2"`、`type: "updates" | "messages" | "custom"` 等字段）。
  - [x] 列出我们计划在后端“原样透出”的事件字段（尽量全部保留），包括：事件类型、节点/工具名称、输入输出、错误、结束标记等。
  - [x] 在 docs 中补充一节“DeepAgents 原生 Streaming 协议说明”，作为前后端共同的契约文档。

- [x] 1.2 新建 DeepAgents 原生 HTTP/SSE 路由
  - [x] 在后端（FastAPI）中新增类似 `/api/v1/deepagents/chat/stream` 的 SSE 路由，内部直接调用 `agent.stream(input, config=...)`。
  - [x] 路由层负责：
    - [x] 用户认证（解析 token / session）。
    - [x] workspace / user_id / provider / model 归一化，组装为 DeepAgents 的 `config` / state。
    - [x] 将前端传入的 messages / images / attachment_ids 等映射到 DeepAgents 期望的输入结构。
  - [x] SSE 事件写出时，尽量按 DeepAgents streaming chunk 原样发送，只增加必要的 `event:` 包装，不再重写 stop_reason 或 tool_trace。

- [x] 1.3 DeepAgents graph 构造与壳层胶水
  - [x] 复核并更新 `build_chat_agent()`：确保所有工具、记忆、中间件配置都符合 DeepAgents 最新推荐（包括 StateBackend 和官方默认 middleware）。目前通过 `create_deep_agent(..., backend=StateBackend, tools=tools, skills=skill_sources, memory=memory_paths)` 统一配置。
  - [x] 将之前散落在 `deepagents_loop.py` 中的 ChatModel 初始化逻辑（`_build_chat_model`）迁移到 `deepagents_graph.py`，让 graph 构造模块成为唯一的 DeepAgents 初始化入口；`run_deepagents_loop` 与新的 streaming 壳都只通过 `build_chat_agent` 获取 agent 实例。
  - [x] 检查需要通过 `config` 传入的额外字段（如 `provider`, `workspace`, `attachment_ids`, `device_enabled`）；当前版本暂未在 `create_deep_agent` 层使用 `config`，仅在调用时通过 payload/工具壳传递这些信息，后续如需利用 DeepAgents 的 `config` 槽位，可在 `build_chat_agent` 的调用方统一追加。

## 2. Aelin 旧壳/协议清理计划（后端）

- [x] 2.1 标记并隔离旧 Aelin agent loop 壳层
  - [x] 在 `aelin_core.py` 中标记所有仍在使用的 Aelin 壳层逻辑（包括 `_dispatch_aelin_chat`, `_try_agent_loop_chat`, `AelinAgentLoopResult` 等），并移除已完全废弃的 `_aelin_chat_impl` 兼容 stub。
  - [x] 确认新 DeepAgents 路由跑通后，这些函数不再作为主链入口：当前前端仍通过 `/aelin/chat` 与 `/aelin/chat/stream` 使用 `_dispatch_aelin_chat` / `_try_agent_loop_chat`，但它们本质上只是 DeepAgents 的薄包装，后续可以在前端迁移完成后整体下线。
  - [x] 在 docs 中通过本 TODO 文件说明：旧 Aelin agent loop / SSE 协议已进入 deprecate 状态，仅存在于过渡期。

- [x] 2.2 设计 Aelin → DeepAgents 的过渡策略
  - [x] 确定短期内保留 `/aelin/chat/stream` 作为兼容层，不直接转发到 `/deepagents/chat/stream`，以避免在前端尚未迁移时引入双层协议转换；新前端将直接使用 `/api/v1/deepagents/chat/stream`。
  - [x] `/aelin/chat/stream` 继续调用 `_dispatch_aelin_chat` + `_try_agent_loop_chat`，但其内部已完全依赖 DeepAgents agent loop，不再调用任何旧的检索时代实现。
  - [x] 计划在前端完成协议迁移后，将 `/aelin/chat/stream` & `/aelin/chat` 标记为 legacy API，并在后续版本中删除对应壳层代码。

- [x] 2.3 删除/收缩旧协议专用代码
  - [x] 删除 `backend/app/services/aelin/core.py` 中已经完全废弃的 `_aelin_chat_impl` 兼容函数，并移除 `backend/app/routers/aelin.py` 中对该符号的导入。
  - [x] 检查 `backend/app/services/aelin/loop_types.py` 与 `backend/app/services/aelin/aelin_tool_policy.py`：确认它们现已成为 DeepAgents bridge（提供统一的 `AelinAgentLoopResult` / `ToolPolicy`），不再承载旧式 SSE 协议专用逻辑，因此保持精简版本，不在本阶段删除。
  - [x] 清理测试中对旧 `_build_chat_model` 位置的引用，使所有 DeepAgents ChatModel 初始化与行为验证都经由 `deepagents_graph.build_chat_agent`，避免出现“壳层散落初始化逻辑”的情况。
  - [x] 保留的只有：认证/多 workspace/provider 拼装相关的通用工具，以及对 DeepAgents 有价值的日志/trace 打点辅助。

- [x] 2.4 后端测试与文档更新
  - [x] 为新的 DeepAgents 路由增加集成测试：新增 `backend/tests/test_deepagents_shell.py::test_deepagents_chat_stream_basic`，通过 mock DeepAgents agent/graph，验证 `/api/v1/deepagents/chat/stream` 至少会发出 `start` 与 `chunk`/`error`/`final`/`done` 事件，且 payload 中包含 `messages`。
  - [x] 更新测试：使 DeepAgents 相关单元测试统一从 `deepagents_graph` monkeypatch `_build_chat_model` / `create_deep_agent`，不再依赖 `deepagents_loop` 内部私有 helper。
  - [x] 本 TODO 即为“Agent Loop 实现”最新状态的描述：当前架构为 Aelin = HTTP 壳 (`/aelin/*` + `/deepagents/*`) + DeepAgents graph + 能力服务。

## 3. 前端协议适配与聊天链路重建

- [x] 3.1 替换前端聊天请求入口
  - [x] 找出前端所有调用 `/api/v1/aelin/chat/stream` 的位置（包括桌面壳，如适用）。
  - [x] 将聊天主链路（`useChatStream` → `streamChat`）的请求入口替换为 `/api/v1/deepagents/chat/stream`，保持请求体结构不变。
  - [x] 通过 `npm run build` 验证前端在新路由下能够正常构建。

- [x] 3.2 初步重写流解析逻辑以识别 DeepAgents 事件
  - [x] 保留通用的 `parseSseChunks` 与 `dispatch` 框架，但将事件来源改为 DeepAgents：`event: chunk` + payload `{version, type, data, ...}`。
  - [x] 为 DeepAgents v2 的 `type === "messages"` 增加处理分支：从 `payload.data.content`（或 `payload.content`）中提取文本增量，调用 `onReplyChunk` 以流式渲染回答。
  - [x] 保持对 `start` / `ping` / `error` / `done` 事件的兼容处理，后续 run graph / 工具更新将基于原始 `chunk` 事件的 `data` 字段构建统一的 `RunStep` 结构。

- [x] 3.3 重建 Execution Pane / 工具调用展示
  - [x] 基于新的 `RunStep` 结构设计 Execution Pane：直接展示 DeepAgents run graph / 工具调用列表，而不是旧的阶段型 trace。
  - [x] 支持：
    - [x] 展示每个工具调用的名称、入参、出参、耗时（如果事件中有）。
    - [x] 标识 DeepAgents 内部子图/子 agent（如果事件中提供）。
    - [x] 以简洁方式渲染运行过程（例如时间线或树状结构）。
  - [x] 删除旧 Execution Pane 中所有紧耦合 Aelin stop_reason / stage 名称 / tool_trace 字段的代码。

- [x] 3.4 前端错误与取消语义对齐
  - [x] 按 DeepAgents streaming 中的错误事件/完成事件设计前端状态机：
    - [x] 区分“正常完成”“用户取消”“内部错误”“缺少配置”等状态（通过 `statusText` 与 `lastErrorCode` 展示）。
    - [x] 在 UI 中用简洁的状态提示替代当前 Aelin 的固定提示文案（例如“本轮未获得可用结果”）。
  - [x] 删除任何依赖旧 stop_reason 字符串的前端分支逻辑（当前前端已不再依赖 stop_reason）。

- [x] 3.5 前端测试与文档
  - [x] （轻量）通过 `npm run build` 确认新的 DeepAgents streaming 事件与 Execution Pane 适配逻辑类型安全、可构建。
  - [x] 在本 TODO 与 `deepagents_arch.md` 中记录：前端 Execution Pane 完全基于 DeepAgents streaming 的 `tool_runs` 结构渲染，不再解析旧 `tool_trace`。

## 4. 能力服务与工具层接线确认

- [x] 4.1 附件服务与 DeepAgents 工具
  - [x] 确认附件上传/索引 API 不需要改变，仅需保证 DeepAgents 工具（file search）能获取 `attachment_ids` / 查询条件：`tool_attachment_search` 通过 `attachment_ids` 参数与 `AelinToolHub._available_attachment_ids` 读取当前会话可用附件，行为与旧链路一致。
  - [x] 在 DeepAgents graph 中确认 file 工具调用路径，确保在新壳下行为不变：`build_chat_tools` 显式注册 `"attachment_search"`，并通过 `_invoke_tool` 记录调用轨迹与摘要。

- [x] 4.2 web_search / device / GWS 工具接线
  - [x] 为 `web_search` / `device` / `screen_get` / `google_workspace` 等工具检查 DeepAgents 事件输出：所有工具结果通过 `_invoke_tool` 统一记录为 `tool_runs`，包含 `name/status/is_write/latency_ms` 以及结构化 `result`。
  - [x] 微调工具 wrapper / 轨迹汇总逻辑，使其在保持能力不变的前提下，多输出结构化摘要字段：`_invoke_tool` 现在优先使用工具返回的 `summary` 字段，其次回退到 `scope` / `total` / 参数数量生成简短摘要，前端 Execution Pane 基于该摘要渲染每次调用。

- [x] 4.3 skills 与 AGENTS.md 记忆
  - [x] 复核 DeepAgents skills 挂载方式：`build_chat_agent` 自 `backend/deepagents_skills/` 与 `settings.deepagents_extra_skills_dir` 挂载所有 `SKILL.md` 及其附属文件到 `/skills/aelin/*` 与 `/skills/external/*`，并以虚拟目录列表形式传入 `create_deep_agent(..., skills=skill_sources)`，完全遵循 DeepAgents skills 规范。
  - [x] 确认记忆仍然完全基于 `/memory/AGENTS.md` + DeepAgents MemoryMiddleware：`build_chat_agent` 将 `memory_summary` 封装为单一 `/memory/AGENTS.md` 文件并传入 `create_deep_agent(..., memory=memory_paths)`，Aelin 不再向 DeepAgents 传入任何额外 DB 记忆结构；外部 `/aelin/context` 等只读接口也仅基于 AGENTS.md 的投影（详见 `deepagents_arch.md`）。

## 5. 收尾与清理

- [x] 5.1 删除所有仅为 Aelin 旧协议存在的代码
  - [x] 在确认新 DeepAgents 壳 + 前端协议稳定后，检查并删除所有不再被调用的旧模块、类型、辅助函数与测试；包括 plane/PinchTab、openviking、DB 记忆链路等，当前这些已全部下线，仅在 `docs/archive` 中保留历史记录。
  - [x] 对 `tool_trace` / `stop_reason` / `/aelin/chat*` 相关代码进行逐一排查，确认现存部分均作为 DeepAgents bridge 或向后兼容 API 仍在使用，不再存在“只为旧 SSE 协议而保留但已无调用”的源文件；后续如完全放弃 `/aelin/*` 兼容层，可在新阶段直接整体删除这一薄壳。

- [x] 5.2 代码体积与复杂度对比
  - [x] 按与 `docs/deepagents_22k_lines_todo_20260322.md` 一致的口径（仅功能代码）重新统计行数：  
    - 后端 Python（`backend/app`, `backend/tests`, `backend/tools`, `backend/deepagents_skills`, `backend/skills` 中的 `.py`）：**13,721 行**  
    - 前端核心（`frontend/src` 下的 `.ts/.tsx/.css`）：**5,411 行**  
    - Desktop 壳（`desktop/src` 下的 `.cjs/.js/.ts`）：**4,340 行**  
    - 合计功能代码 ≈ **23,472 行**
  - [x] 与 2026-03-22 DeepAgents 精简快照对比（当时约 27.8k + 5.5k + 4.3k ≈ 37.6k 行），当前版本在引入 DeepAgents 原生壳、下线旧 Agent Loop / plane / DB 记忆以及瘦身 media/attachment/web_search/desktop 之后，整体代码量已经进入预期的 2.2 万行附近区间，且服务模块与前端聊天链路均趋于简化而非增加“协议胶水”。

- [x] 5.3 最终文档与版本标记
  - [x] 在 docs 中补充一份“从 Aelin 壳到 DeepAgents 原生壳的迁移记录”（见 `docs/deepagents_native_shell_migration_202602-202603.md`），按时间顺序记录从多套 Agent Loop + DB 记忆 + plane/PinchTab 到「DeepAgents 原生壳 + 文件记忆」的关键设计决策与取舍。
  - [x] 在仓库 README 中补充当前架构状态说明：Aelin 后端 = DeepAgents 原生壳（`/deepagents/chat/stream`）+ 能力服务（web_search / attachments / device / Google Workspace / skills），并建议二次开发优先参考 DeepAgents 官方文档与本仓库的 `docs/deepagents_arch.md`。
