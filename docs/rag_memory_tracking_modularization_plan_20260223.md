# Aelin RAG / 记忆 / 追踪 模块化改造路线图（2026-02-23）

## 目标
- 降低 `backend/app/routers/aelin.py` 的编排复杂度，避免单文件持续膨胀。
- 将 RAG、记忆写入、追踪自治流程解耦成可独立测试与演进的模块。
- 统一前后端契约，减少 UI 因字段漂移导致的“有数据但渲染异常”。

## 当前主要问题
- 聊天主链路过长，意图、规划、检索、质检、写入都耦合在 `_aelin_chat_impl`。
- 追踪/文件记忆接口演进后，前端字段与 ack 路径容易漂移。
- 日记页过去只渲染 `preview`，缺少“按路径读取全文”能力。

## 目标架构（建议）
1. `app/services/aelin_orchestrator/intent.py`
- 只负责 Intent Lens、契约归一化、时间范围判定。

2. `app/services/aelin_orchestrator/planning.py`
- 只负责 Planner/Critic/Plan Patch 与 context boundaries。

3. `app/services/aelin_orchestrator/retrieval.py`
- 只负责 local/web/file-memory 并行检索与证据合并。

4. `app/services/aelin_orchestrator/quality.py`
- 只负责 grounding / coverage / reply verifier 与 retry 查询构建。

5. `app/services/aelin_orchestrator/memory_write.py`
- 只负责 update_after_turn、chat diary、insight、parallel draft 写入。

6. `app/services/aelin_contracts/`
- 集中维护前后端共享字段映射与兼容策略（例如 ack、snapshot 字段）。

## 分阶段执行

### Phase 1（低风险拆分）
- 抽离 `_build_intent_contract`、`_plan_tool_usage`、`_critic_tool_plan` 到独立模块。
- 保持原行为与返回结构不变。
- 验收：`test_aelin.py` 相关用例全绿；SSE 事件结构无变化。

### Phase 2（检索与质检拆分）
- 抽离 local/web 并行检索器与 evidence merge。
- 抽离 grounding/coverage/reply 三重校验与 retry 策略。
- 验收：关键回归测试 + 对比日志中 `tool_trace` 阶段数量一致。

### Phase 3（记忆写入与文件记忆统一）
- 抽离 chat diary / insight / parallel draft 写入策略。
- 标准化 file-memory API：`search/tree/content` 三件套。
- 验收：日记页能稳定展示全文，写入失败时有可观测原因。

### Phase 4（契约治理）
- 建立前后端契约快照测试（TrackingChange/Snapshot/FileMemory）。
- 建立接口兼容窗口策略（新路由上线后保留旧路由一段周期）。
- 验收：CI 中新增 contract test，避免字段漂移回归。

## 指标
- 编排文件最大函数长度：目标 < 250 行。
- 单测覆盖：RAG 编排主链路 + tracking API 契约用例稳定通过。
- 缺陷指标：tracking/detail 与 diary 页面“空渲染”类问题归零。

## 建议优先级
1. 先做 Phase 1 + Phase 4（先稳契约，再拆编排）。
2. 再做 Phase 2（检索和质检最容易回归，需测试护栏）。
3. 最后做 Phase 3（写入策略多，适合在稳定期推进）。
