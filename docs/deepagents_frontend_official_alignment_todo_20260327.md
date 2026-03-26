# DeepAgents Frontend Official Alignment Todo (2026-03-27)

## Goal

把 Aelin 前端从“DeepAgents 内核 + Aelin 自定义前端壳”继续收敛为更接近官方最佳实践的形态：

- 前端以 `useStream` 为主状态源。
- 消息、工具、subagents、todos 尽量直接来自官方运行时。
- 图展示以 LangGraph 运行态 metadata 为基础，而不是再手搓一层厚协议。
- 后端只保留必要的 HTTP / auth / provider / tool glue。

## Official References

- [Deep Agents Frontend Overview](https://docs.langchain.com/oss/javascript/deepagents/frontend/overview)
- [Message Queues](https://docs.langchain.com/oss/python/langchain/frontend/message-queues)
- [Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [DeepAgents GitHub Repository](https://github.com/langchain-ai/deepagents)

## Key Findings

- 官方前端核心是 `useStream`，并明确建议直接使用 `stream.subagents`、`stream.values.todos`、`filterSubagentMessages` 等运行时能力，而不是重建一套平行协议。
- 官方 DeepAgents 是“agent harness”，强调 `create_deep_agent` 的 planning、filesystem、subagents、memory、streaming 一体化。
- 官方 `message queue`、更完整的 thread / branch / enqueue 体验，需要 LangGraph Agent Server；单纯自定义 SSE 路由吃不满这部分能力。
- Aelin 当前已经用了 `useStream`，但仍保留了明显的自定义壳层：
  - [deepagentsUseStreamTransport.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/deepagentsUseStreamTransport.ts) 仍在手写 SSE 解析与事件翻译。
  - [executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts) 仍在重建 `turns/tools/subagents/topology` 中间层。
  - [ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx) 主要消费的是我们重建后的 execution model，而不是官方 runtime data。
  - 聊天区消息虽然已明显收薄，但还没有彻底做到“只认 `stream.messages` 为唯一真相源”。

## Phase 1: Stream State Single Source

- [x] 把聊天消息的 canonical source 彻底收敛到 `stream.messages`。
- [x] 让 `chatStore` 只保留 UI 偏好、本地草稿、当前 session/workspace、pane 开关，而不再保存 canonical message list。
- [x] 删除 `stream -> chatStore -> timeline` 的双轨同步路径。
- [x] 把当前消息重复、助手拆条、placeholder 等兼容逻辑继续下沉，尽量减少“流后修补”代码。
- [ ] 为“单次 submit 只出现一条 user message / 一条 assistant stream”补前端回归测试。

## Phase 2: Tool Rendering Native-First

- [x] 让消息气泡优先直接使用 `stream.getToolCalls(message)` 渲染工具调用。
- [x] 将 `tool_runs` 自定义 custom event 从“主数据源”降为“补充数据源”或调试数据。
- [x] 删除 execution mapping 中仅为兼容旧 `tool_runs` 而存在的冗余聚合逻辑。
- [x] 将工具状态卡片改为“每条 AI message 关联其 tool calls”，减少全局扁平工具表依赖。
- [x] 检查并收紧对 draft / invalid tool call 的过滤逻辑，避免再次手搓过多契约。

## Phase 3: Subagents / Todos Native-First

- [x] 右侧 pane 直接消费 `stream.subagents`，而不是优先从 `getSubagentsByMessage` + 中间模型重建。
- [x] todo 面板直接消费 `stream.values.todos`，减少额外的 state mapping。
- [x] 将 subagent message / coordinator message 的 UI 区分建立在官方 runtime 数据上，而不是自定义 turns。
- [x] 用 `filterSubagentMessages` 重新梳理主聊天区与子代理区的职责边界。

## Phase 4: Graph Truly LangGraph-Like

- [x] 保留静态拓扑，但将运行时高亮直接建立在 `getMessagesMetadata()`、message namespace、state updates 上。
- [x] 删除 execution graph 中“基于 turns 猜节点运行状态”的逻辑，改为 metadata 驱动。
- [x] 支持更真实的分叉/子图表现，而不只是串行 column board。
- [x] 将工具调用、子代理、节点运行状态统一到同一个 runtime graph 视图中。
- [x] 让 graph 面板成为“运行态视图”，而不是“二次摘要视图”。

## Phase 5: Transport And Protocol Thinning

- [x] 继续收薄 [deepagentsUseStreamTransport.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/deepagentsUseStreamTransport.ts)，减少手写 SSE 契约判断。
- [x] 检查后端 [deepagents_chat.py](/D:/Github/Aelin/backend/app/routers/deepagents_chat.py) 中哪些 `custom` 事件只是为了补前端壳层，能否继续删除或降级。
- [x] 尽量让前端依赖 `messages / updates / values / tasks` 这些原生流事件，而不是 Aelin 专属事件名。
- [x] 清理 execution/runtime 相关不再需要的旧 helper、status summary、重复 normalize 代码。

## Phase 6: Optional Full Official Shape

- [ ] 评估是否迁移到更接近 LangGraph Agent Server 的协议形态。
- [ ] 若迁移，则引入官方 queue / branch / thread history 语义，吃满 `stream.queue` 能力。
- [ ] 将“多条消息排队、跟进消息 enqueue、取消队列项”设计为产品能力，而不是只支持单次当前 run。
- [ ] 再评估前端是否需要为 branch/time-travel 提供 UI，而不是只停留在当前单线程流式聊天。

## Non-Goals For This Round

- [ ] 不为单个查询类型写大量特殊契约来模拟“更聪明的搜索 UI”。
- [ ] 不为了视觉相似而强行复制官方 demo；重点是 runtime data flow 对齐。
- [ ] 不在前端原生化迁移过程中重新引入旧 Aelin 协议层。

## Exit Criteria

- [ ] 聊天区消息完全由 `useStream` 驱动，不再有双轨消息状态。
- [ ] 工具、subagents、todos 展示主要基于官方 runtime data，而不是 Aelin 自定义重建层。
- [ ] Execution Pane 的 graph 高亮与节点状态来自 metadata / state，而不是 turns 猜测。
- [ ] transport / stream adapter 明显变薄，旧 execution mapping 代码体积显著下降。
- [ ] 如不迁 Agent Server，也要明确记录“当前不支持 queue/branch 完整体验”的边界；如迁移，则接入官方 queue 能力。
