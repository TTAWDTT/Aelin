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

- [ ] 1.3 DeepAgents graph 构造与壳层胶水
  - [ ] 复核并更新 `build_chat_agent()` / `build_chat_graph()`：确保所有工具、记忆、中间件配置都符合 DeepAgents 最新推荐（包括 MemoryMiddleware、StateBackend、SkillsBackend 等）。
  - [ ] 将之前散落在 `deepagents_loop.py` / 其它模块中的 DeepAgents 初始化逻辑全部迁移到统一的 graph 构造模块中，后端路由只调用一个入口函数。
  - [ ] 检查并记录任何需要通过 `config` 传入的额外字段（如 `provider`, `workspace`, `attachment_ids`, `device_enabled`），保证它们在 DeepAgents graph 内部被合规使用。

## 2. Aelin 旧壳/协议清理计划（后端）

- [ ] 2.1 标记并隔离旧 Aelin agent loop 壳层
  - [ ] 在 `aelin_core.py` 中标记所有仍在使用的 Aelin 壳层逻辑（包括 `_dispatch_aelin_chat`, `_try_agent_loop_chat`, `AelinAgentLoopResult` 等）。
  - [ ] 确认新 DeepAgents 路由跑通后，这些函数不再作为主链入口，仅保留临时兼容/回退用途。
  - [ ] 在 docs 中添加说明：旧 Aelin agent loop / SSE 协议处于 deprecate 状态，仅存在于过渡期。

- [ ] 2.2 设计 Aelin → DeepAgents 的过渡策略
  - [ ] 确定是短期内同时保留 `/aelin/chat/stream`（内部转发 DeepAgents），还是直接废弃该路由，统一切到 `/deepagents/chat/stream`。
  - [ ] 如果保留兼容层：
    - [ ] 在 `/aelin/chat/stream` 中直接调用新 DeepAgents 路由或内部函数，不再走旧 `_try_agent_loop_chat` 逻辑。
    - [ ] 对返回结果做最小必要的字段映射，确保不新增任何新的 stop_reason / trace 包装。
  - [ ] 计划一个最终清理点（例如若干版本后）完全删除 `/aelin/chat/stream` 与对应壳层。

- [ ] 2.3 删除/收缩旧协议专用代码
  - [ ] 删除或极度精简以下模块中仅为旧协议服务的内容：
    - [ ] `backend/app/services/aelin/core.py` 中的旧 agent loop / stop_reason / tool_trace 逻辑。
    - [ ] `backend/app/services/aelin/loop_types.py` 中的 stop_reason 常量与相关类型。
    - [ ] `backend/app/services/aelin/aelin_tool_policy.py` 与任何旧式 ToolHub 分发/策略实现。
    - [ ] 其它专门为旧 SSE 协议定义的类型、封装函数和测试。
  - [ ] 保留的只有：
    - [ ] 认证/多 workspace/provider 拼装相关的通用工具。
    - [ ] 可复用的日志/trace 打点辅助（如果仍然对 DeepAgents 有价值）。

- [ ] 2.4 后端测试与文档更新
  - [ ] 为新的 DeepAgents 路由增加集成测试：构造简单/复杂聊天请求，消费 SSE 流，断言事件序列与内容大致合理。
  - [ ] 更新/删除旧有只针对 Aelin stop_reason / tool_trace 结构的测试。
  - [ ] 更新 docs 中关于“Agent Loop 实现”的章节，描述现在的架构：Aelin = HTTP 壳 + DeepAgents graph + 能力服务。

## 3. 前端协议适配与聊天链路重建

- [ ] 3.1 替换前端聊天请求入口
  - [ ] 找出前端所有调用 `/api/v1/aelin/chat/stream` 的位置（包括桌面壳，如适用）。
  - [ ] 新增或替换为 `/api/v1/deepagents/chat/stream`（或确定的 DeepAgents 路由）。
  - [ ] 保持请求体中的 messages / images / attachment_ids 等结构不变，除非 DeepAgents 需要更标准的输入格式，再按需调整。

- [ ] 3.2 重写流解析逻辑为 DeepAgents 事件模型
  - [ ] 设计一个前端内部使用的统一事件/步骤结构（例如 `RunStep { id, kind, toolName, input, output, parentId, status }`）。
  - [ ] 根据 DeepAgents streaming 文档，开发一个解析器：将原生 streaming chunk（含 `version`, `type`, `ns`, `data` 等）映射为上述 `RunStep` 列表和最终消息内容。
  - [ ] 替换当前基于 Aelin 自定义 SSE 事件和 `tool_trace` 的解析逻辑，确保聊天主流程在新协议下正常工作。

- [ ] 3.3 重建 Execution Pane / 工具调用展示
  - [ ] 基于新的 `RunStep` 结构设计 Execution Pane：直接展示 DeepAgents run graph / 工具调用列表，而不是旧的阶段型 trace。
  - [ ] 支持：
    - [ ] 展示每个工具调用的名称、入参、出参、耗时（如果事件中有）。
    - [ ] 标识 DeepAgents 内部子图/子 agent（如果事件中提供）。
    - [ ] 以简洁方式渲染运行过程（例如时间线或树状结构）。
  - [ ] 删除旧 Execution Pane 中所有紧耦合 Aelin stop_reason / stage 名称 / tool_trace 字段的代码。

- [ ] 3.4 前端错误与取消语义对齐
  - [ ] 按 DeepAgents streaming 中的错误事件/完成事件设计前端状态机：
    - [ ] 区分“正常完成”“用户取消”“内部错误”“缺少配置”等状态。
    - [ ] 在 UI 中用简洁的状态提示替代当前 Aelin 的固定提示文案（例如“本轮未获得可用结果”）。
  - [ ] 删除任何依赖旧 stop_reason 字符串的前端分支逻辑。

- [ ] 3.5 前端测试与文档
  - [ ] 更新聊天 store / Execution Pane 的单元测试，使其基于 DeepAgents streaming 事件的 mock 数据运行。
  - [ ] 删除旧协议相关的 snapshot / 单测。
  - [ ] 在前端开发文档中新增一节，说明 DeepAgents streaming 协议与前端内部 `RunStep` 模型之间的映射规则。

## 4. 能力服务与工具层接线确认

- [ ] 4.1 附件服务与 DeepAgents 工具
  - [ ] 确认附件上传/索引 API 不需要改变，仅需保证 DeepAgents 工具（file search）能获取 `attachment_ids` / 查询条件。
  - [ ] 在 DeepAgents graph 中确认 file 工具调用路径，确保在新壳下行为不变。

- [ ] 4.2 web_search / device / GWS 工具接线
  - [ ] 为 `web_search` / `device` / `screen_get` / `google_workspace` 等工具检查 DeepAgents 事件输出：确保工具调用信息足够丰富，便于前端展示。
  - [ ] 如有必要，微调工具 wrapper，使其在保持能力不变的前提下，多输出一点结构化数据（例如 URL、选择的 provider、执行结果摘要）。

- [ ] 4.3 skills 与 AGENTS.md 记忆
  - [ ] 复核 DeepAgents skills 挂载方式，确保新的壳层仍然完全遵循 DeepAgents 官方 skills 规范（含 `SKILL.md`、脚本与引用路径）。
  - [ ] 确认记忆仍然完全基于 `/memory/AGENTS.md` + DeepAgents MemoryMiddleware，Aelin 侧不再有任何额外的 DB 记忆或上下文拼装逻辑参与 agent 决策。

## 5. 收尾与清理

- [ ] 5.1 删除所有仅为 Aelin 旧协议存在的代码
  - [ ] 在确认新 DeepAgents 壳 + 前端协议稳定后，删除所有不再被调用的旧模块、类型、辅助函数与测试。
  - [ ] 包括但不限于：旧 agent loop 壳、旧 SSE 协议封装、旧 tool_trace 结构、旧 stop_reason 常量等。

- [ ] 5.2 代码体积与复杂度对比
  - [ ] 对比迁移前后后端服务行数（尤其是 `app/services/aelin/*` 与 `deepagents_*` 模块），记录代码减少量。
  - [ ] 对比前端聊天链路相关代码行数与模块数量，确认整体趋于简化而非增加“协议胶水”。

- [ ] 5.3 最终文档与版本标记
  - [ ] 在 docs 中补充一份“从 Aelin 壳到 DeepAgents 原生壳的迁移记录”，记录关键设计决策与取舍。
  - [ ] 在仓库 README / 版本日志中注明：当前版本 Aelin 后端 = DeepAgents 原生壳 + 能力服务，推荐参考 DeepAgents 官方文档进行二次开发。
