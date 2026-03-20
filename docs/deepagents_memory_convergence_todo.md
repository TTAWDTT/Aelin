# DeepAgents 记忆收拢 TODO 列表

> 目标：让 Aelin 的记忆体系尽可能收拢到 DeepAgents 标准用法——
> 以 `/memory/AGENTS.md` 等虚拟文件为唯一权威记忆源，Aelin 只做投影与 UI。

---

## 1. 从 DeepAgents StateBackend 读回 `/memory/AGENTS.md`

- [x] 实现：在 `run_deepagents_loop` 完成一次调用后，将 `/memory/AGENTS.md` 作为虚拟文件挂载给 DeepAgents（通过 `files` + `memory`）。
- [x] 实现：为 DeepAgents agent 增加一个可选的 “memory dump” 接口，暴露当前 memory 文件的文本内容（`AelinAgentLoopResult.memory_snapshot`）。
- [x] 实现：在 `_try_agent_loop_chat` 中接收这份最新的 memory 文本（`latest_memory_snapshot`），为后续持久化预留接入点。

**验收标准：**
- [x] 在无异常情况下，调用 DeepAgents 一轮后可以拿到一份 `/memory/AGENTS.md` 的内存快照（当前实现为本轮挂载的 AGENTS.md 内容）。
- [x] 当 DeepAgents 未写入任何 memory 文件时，读取逻辑稳态返回空字符串，而不会抛错。
- [x] Aelin 核心 `_try_agent_loop_chat` 已经能够接收到并持有该快照，后续可以在此基础上实现持久化逻辑。

---

## 2. 为 `/memory/AGENTS.md` 建立持久化层（文件或 DB 映射）

- [x] 设计：确定单一“权威存储”位置：`FileMemoryBridge` 下的 `users/{user_id}/workspaces/{workspace}/memory/AGENTS.md`。
- [x] 实现：新增读写 API（`read_agents_memory` / `write_agents_memory`），用于按 `user_id + workspace` 读写完整的 `AGENTS.md` 文本。
- [x] 实现：在 DeepAgents loop 结束后，通过 `_try_agent_loop_chat` 使用 `latest_memory_snapshot` / `memory_summary` 将 `/memory/AGENTS.md` 文本覆盖写回该持久层。

**验收标准：**
- [x] 在同一用户 & workspace 下，调用 `_file_memory.read_agents_memory` 能读取到最近一轮对话写入的 `AGENTS.md` 内容。
- [x] Aelin 重启后（进程级），在相同用户 & workspace 下调用 `write_agents_memory` 写入的 `AGENTS.md` 仍可通过 `read_agents_memory` 读回，为 DeepAgents 提供持久化记忆文件的来源。

---

## 3. 让 AgentMemoryService 以 `/memory/AGENTS.md` 为“真相”，DB 只做投影

- [x] 设计：为 `AgentMemoryService` 增加一层适配器，从持久化的 `AGENTS.md` 文本中解析出：summary / notes / todos / memory_layers 所需信息。
- [x] 实现：`get_summary` 优先从持久化的 `AGENTS.md` 中解析「## 会话摘要」段落得到简洁 summary，找不到时再回退到 DB 的 summary 字段。
- [x] 实现：`list_notes` / `list_todos` 优先从 `AGENTS.md` 投影（存在有效 section 时），否则回退到 DB；`build_memory_layers_from_items` 继续消费调用方提供的 items，由上游保证来自同一份 AGENTS.md。
- [x] 实现：保留对旧 DB 字段的兼容（必要时），但作为回退路径，而非主数据源。

**验收标准：**
- [x] 在不开启旧 DB 写入的情况下，只依赖 `/memory/AGENTS.md` 也能返回合理的 summary / notes / todos / memory_layers。
- [x] 修改 `AGENTS.md` 文本后（例如手工编辑或通过工具），调用 `/aelin/context` 即可看到对应变化。

---

## 4. 调整 `/aelin/context` 和 `/agent/memory` 的数据来源

- [x] 实现：`build_context_bundle` 使用新的 AgentMemoryService 适配层，从 `AGENTS.md` 中投影出 context 所需字段（summary / notes / todos / memory_layers 均经由 AGENTS.md 映射）。
- [x] 实现：`/agent/memory` 相关 endpoint（summary / notes / focus_items / todos）在读取侧统一经过 `AgentMemoryService` 的 AGENTS.md 适配层（其中 summary / notes / todos 来自 AGENTS.md，focus_items 仍基于 DB 消息构建）。
- [x] 清理：删掉 context 相关路径上残留的 layout/daily-brief/notifications 注入逻辑（若还有）。

**验收标准：**
- [x] `/aelin/context` 返回的数据在结构上保持兼容（字段不退化），但修改 `AGENTS.md` 就能驱动所有记忆相关字段更新。
- [x] `/agent/memory` 返回的 summary / notes / todos 与 `/aelin/context` 中对应部分内容一致，且都可追溯到同一份 `AGENTS.md` 文本。

---

## 5. 引入 DeepAgents 风格的“记忆写入工具”（编辑 `/memory/AGENTS.md`）

- [x] 设计：定义一个或若干 memory 工具（如 `memory_append_fact` / `memory_update_preference` / `memory_add_todo`），实现对 `/memory/AGENTS.md` 指定 section 的安全修改。
- [x] 实现：在 `deepagents_skills/` 目录下为这些工具补充 README / usage 说明，让 Agent 知道如何规范增删改记忆。
- [x] 实现：将上述工具通过 `AelinToolHub` 暴露给 DeepAgents，并在 policy 中标记为写工具。

**验收标准：**
- [x] 模型可以通过调用 memory 工具在 `/memory/AGENTS.md` 中新增或更新一条事实/偏好/待办条目。
- [x] 更新后的 `AGENTS.md` 能被下一轮对话正确读回，体现为 context / memory_layers 的变化。

---

## 6. 弱化 / 清理旧 DB 记忆结构与逻辑（在确保兼容的前提下）

- [x] 分析：列出当前仍有写入行为的 DB 记忆表字段（`AgentConversationMemory`, `AgentMemoryNote`, todo notes 等），标记哪些可以降级为缓存或废弃。
- [x] 实现：对确认废弃的写入路径打上“no-op”或迁移到 `/memory/AGENTS.md` 的过渡逻辑，避免同一信息写两份。
- [x] 清理：去掉完全不可达的老 helper（旧版 layout-based memory、notifications-based memory 等）。

**验收标准：**
- [x] 新写入行为（facts / preferences / in-progress / todos）只经过“DeepAgents memory 工具 → `/memory/AGENTS.md` → 投影”这条路径，不再直接写 DB 表作为主存。
- [x] 删除/弱化旧逻辑后，现有测试（尤其是 agent memory / aelin context / remote control 相关）全部绿灯。

---

## 7. 测试与验证：确保 DeepAgents 记忆闭环稳定

- [ ] 新增针对 `/memory/AGENTS.md` 的单元测试：
  - [ ] 初始化时无记忆 → 首轮聊天后 AGENTS.md 被创建。
  - [ ] 连续多轮聊天中，记忆内容按预期累积/更新。
- [ ] 为新的 memory 工具增加集成测试，覆盖：写入 → 持久化 → 再次读取 → context 投影。
- [ ] 运行一轮真实链路验证（含 plane / device / web_search），确认 DeepAgents 在有记忆 & 无记忆两种情况下的行为都合理。

**验收标准：**
- [ ] 新增/修改的测试在 CI 和本地均稳定通过。
- [ ] 在实际 UI 中，用同一个 workspace 连续多轮聊天时，能够看到记忆增长（如用户偏好被 agent 记住并在回答中使用），且对应 AGENTS.md 变化可被验证。
