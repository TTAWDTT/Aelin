# Aelin 持续追踪能力优化方案（optimize_track）

## 1. 目标与范围

当前 Aelin 的追踪能力更像“手动记录 + 一次性同步”，缺少可持续、可观测、可通知的完整链路。本文目标是把追踪升级为真正的 **持续监控系统**：

- 用户确认追踪后，系统自动按计划轮询/抓取
- 每次抓取形成快照（Snapshot）
- 新旧快照自动计算变化（Diff）
- 变化按规则分级并通知
- 全流程可查询、可重试、可静音、可审计

范围：后端数据库、API、Worker、通知策略、前端联动点。

---

## 2. 总体架构

```text
Track Confirm -> Upsert Target -> Scheduler -> Fetch Snapshot -> Diff -> Change Record -> Notify
                                                  |                |
                                                  v                v
                                            tracking_snapshots   tracking_changes
```

核心原则：

1. **Target/Snapshot/Change 三层分离**（避免状态混杂）
2. **幂等与去重优先**（同一变化不重复轰炸）
3. **弱依赖可降级**（抓取失败不阻塞系统整体）

---

## 3. 数据模型设计（新增）

> 建议在 `backend/app/models.py` 增加以下模型，并配套 Alembic 迁移。

### 3.1 `tracking_targets`

用于保存“追踪对象定义”。

关键字段：

- `id` (pk)
- `user_id` / `workspace_id`
- `source_type`（github/bilibili/x/rss/custom...）
- `source_key`（如 repo full_name、uid、feed_url）
- `display_name`
- `track_mode`（poll/webhook/hybrid）
- `interval_seconds`（默认 600）
- `status`（active/paused/deleted/error）
- `last_run_at`
- `next_run_at`（用于调度）
- `error_count`
- `mute_until`
- `notify_level`（all/important/critical）
- `config_json`（抓取参数、过滤规则）
- `created_at` / `updated_at`

唯一约束建议：`(user_id, source_type, source_key)`。

### 3.2 `tracking_snapshots`

用于保存每次抓取后的标准化结果。

关键字段：

- `id` (pk)
- `target_id` (fk -> tracking_targets.id)
- `version_no`（按 target 递增）
- `raw_payload_json`（原始数据）
- `normalized_payload_json`（标准化后的可对比结构）
- `content_hash`（sha256，用于快速跳过无变化）
- `fetched_at`
- `fetch_status`（ok/partial/failed）
- `fetch_error`

索引建议：`(target_id, version_no desc)`、`(target_id, fetched_at desc)`。

### 3.3 `tracking_changes`

用于记录“快照之间的变化事件”。

关键字段：

- `id` (pk)
- `target_id` (fk)
- `from_snapshot_id` / `to_snapshot_id`
- `change_type`（new_item/updated/removed/metric_spike/status_change）
- `severity`（low/medium/high/critical）
- `title`
- `summary`
- `diff_json`（结构化差异）
- `dedupe_key`（用于通知去重）
- `notified`（bool）
- `acked`（bool）
- `created_at`

索引建议：`(target_id, created_at desc)`、`(notified, severity)`、`dedupe_key unique`。

---

## 4. API 设计（兼容现有并扩展）

## 4.1 兼容改造

- `POST /api/v1/aelin/track/confirm`
  - 现状：更偏“备注/事件”
  - 改造：改为真正 `upsert tracking_target`
  - 返回：`target_id`, `status`, `next_run_at`

## 4.2 新增接口

1. `GET /api/v1/aelin/tracking/targets`
   - 分页返回追踪目标（含 last/next/error）

2. `PATCH /api/v1/aelin/tracking/targets/{id}`
   - 可更新：`status`、`interval_seconds`、`notify_level`、`mute_until`、`config_json`

3. `POST /api/v1/aelin/tracking/targets/{id}/run`
   - 手动触发一次抓取（调试/补偿）

4. `GET /api/v1/aelin/tracking/targets/{id}/changes`
   - 返回变化列表（支持 severity/type 过滤）

5. `POST /api/v1/aelin/tracking/changes/{id}/ack`
   - 用户确认已读

6. `GET /api/v1/aelin/tracking/targets/{id}/snapshots`
   - 快照历史（用于溯源）

---

## 5. Worker 与调度实现

## 5.1 调度器

在 `backend/app/services/sync_jobs.py` 或独立 `tracking_jobs.py` 中增加循环：

1. 查询 `status=active and next_run_at <= now()` 的 targets（按 next_run_at asc，limit 批次）
2. 分发到抓取任务队列（并发受限）
3. 更新 `last_run_at` 与新的 `next_run_at = now + interval`

建议并发：按 source_type 分池（防止单源限流拖垮整体）。

## 5.2 抓取任务

统一入口：`run_tracking_target(target_id)`

流程：

1. 读取 target 配置
2. 调用对应 connector（github/bilibili/x/rss...）
3. 生成 normalized payload
4. 计算 hash，与最新快照 hash 对比
   - 相同：写一条 snapshot（可选）并结束
   - 不同：写新 snapshot，进入 diff
5. 生成 changes 并入库
6. 根据通知策略推送

失败处理：

- `error_count += 1`
- 指数退避：`next_run_at += min(2^error_count * base, max_backoff)`
- 超阈值可自动降级为 `status=error` 并告警一次

---

## 6. Diff 策略（最小可用 + 可扩展）

采用“来源可插拔 diff”，默认通用算法：

1. 先按 item 主键（如 id/url）对齐
2. 计算三类变化：新增 / 删除 / 更新
3. 更新类再做字段白名单比较（标题、状态、时间、计数）
4. 生成 `diff_json`

`severity` 规则建议：

- `critical`：状态异常、重大负向变化
- `high`：关键字段变更（如 release、封禁、下架）
- `medium`：普通内容更新
- `low`：轻量统计波动

去重：`dedupe_key = hash(target_id + change_type + key_fields + day_bucket)`。

---

## 7. 通知策略

通知通道：优先复用 Aelin 现有消息/Telegram 通道。

策略：

- respect `mute_until`
- respect `notify_level`
- 相同 `dedupe_key` 24h 内仅一次
- 支持摘要模式（例如每 30 分钟聚合）

通知内容模板：

- 标题：`[Aelin追踪] {display_name} 有新变化`
- 正文：`变化类型 + 摘要 + 时间 + 快照链接`
- 操作：`ACK / 静音1天 / 查看详情`

---

## 8. 前端联动（Aelin 面板）

在 `frontend/src/components/Aelin.tsx` 增加：

- 追踪目标列表（状态、下次执行、错误数）
- 变化流（按时间倒序，支持 severity 过滤）
- 快速操作（暂停、恢复、手动运行、ACK、静音）

最小交互闭环：

1. 用户在 Chat 中确认追踪
2. 列表立刻出现目标
3. 变化出现红点
4. 用户点开并 ACK

---

## 9. 落地步骤（建议顺序）

1. **DB 迁移**：三张表 + 索引 + 约束
2. **track/confirm 改造**：写入真实 target
3. **worker 最小链路**：跑通 snapshot + hash 比较
4. **diff + changes 入库**
5. **通知与去重**
6. **前端面板接入**
7. **压测与失败注入**（限流、超时、脏数据）

---

## 10. 验收标准（Definition of Done）

- 能创建追踪目标并稳定执行至少 24h
- 无变化不重复通知；有变化可追溯到 diff 与快照
- 单目标失败不会影响全局调度
- 用户可在 UI 完成暂停/恢复/手动运行/ACK
- 关键接口与任务日志可审计

---

## 11. 风险与缓解

- **外部源限流/反爬**：分源限速 + 重试 + 退避
- **变化噪声过多**：字段白名单 + severity + dedupe
- **数据膨胀**：快照分级保留（近7天全量，历史抽样）
- **误报**：引入 source-specific 规则并可灰度发布

---

## 12. 首批推荐实现的 Source 优先级

1. GitHub（仓库 release / issue / notification）
2. RSS/Blog（结构稳定）
3. Bilibili / X（波动较大，后续加强）

这样可以最快拿到“稳定、可解释”的连续追踪体验。