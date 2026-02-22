# Aelin 链路审查（并行记忆草稿改造）

更新时间：2026-02-22

## 1. 本次改造范围

- 在 `chat` 主链路中新增「并行记忆草稿」阶段：`parallel_draft`
- 新增「草稿提交」阶段：`parallel_draft_commit`
- 新增可配置参数：
  - `MERCURYDESK_AELIN_PARALLEL_MEMORY_DRAFT_ENABLED`
  - `MERCURYDESK_AELIN_PARALLEL_MEMORY_DRAFT_WORKERS`
  - `MERCURYDESK_AELIN_PARALLEL_MEMORY_DRAFT_TIMEOUT_SECONDS`
  - `MERCURYDESK_AELIN_PARALLEL_MEMORY_DRAFT_MIN_CONFIDENCE`

## 2. 设计要点

- 采用「并行起草 + 串行提交」：
  - 检索阶段并行构建草稿，不阻塞主回答
  - 只有 `reply_verifier + grounding + coverage` 都通过时才提交正式日记
- 提交内容写入 `entry_kind=chat_parallel_draft`
- 维持现有 `chat_diary` 与 `tracking_insight` 机制不破坏

## 3. 真实测试结果

### 3.1 全量自动化测试

命令：

```bash
pytest -q backend/tests
```

结果：

- `80 passed, 1 warning`

### 3.2 真实链路跑通（本地 TestClient）

场景：`请并发本地检索和联网搜索，告诉我NBA最近如何，先给结论。`

观测到阶段：

- `parallel_draft: completed`
- `parallel_draft_commit: skipped`
- `reply_verifier: failed`

解释：

- 草稿生成成功（有证据、置信度可用）
- 因主回复质量门禁未通过（coverage 缺少硬证据），草稿提交被正确拦截
- 说明「并行构建」和「提交门禁」都按设计生效

## 4. 当前链路判定

- 并行记忆构建：已打通
- 正式记忆提交门禁：已打通
- 与现有日记系统（OpenViking file-memory）兼容：已打通
- 风险控制（避免噪声入库）：已生效

## 5. 下一步建议

- 增加 `parallel_draft_commit` 成功率指标（按 workspace/source_type 统计）
- 对 `coverage_verifier` 引入更细粒度体育场景规则（比分/日期/来源锚点）
- 增加“用户纠错触发记忆修订”链路（纠偏优先级高于普通洞察）
- 增加“草稿池”短期缓存（如 24h），供失败轮次后续补提交流程复用
