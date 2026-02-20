# OpenViking 方案尝试（openviking_try）

## 1. 目标与结论

我们希望把 Aelin 的“追踪记忆”从纯数据库读写，升级为：

- **数据库负责稳定调度与状态管理**（可靠）
- **文件系统负责可读、可写、可演化的长期记忆**（可解释）
- **OpenViking 负责 Agent-native 检索**（可下钻）

结论：

> 这是一个 **可写 RAG**（Agent-native RAG）方案。  
> 不是抛弃 RAG，而是抛弃“只读平面向量库”那种传统使用方式。

---

## 2. 为什么要这样做

当前项目已经有完整追踪链路（`tracking_targets / tracking_snapshots / tracking_changes`），但还存在几个天然瓶颈：

1. 记忆可读性不足：用户很难直接理解历史追踪脉络。
2. 记忆可写性不足：LLM 难以结构化沉淀长期洞察。
3. 检索可解释性不足：召回过程对用户接近黑盒。

OpenViking 的文件系统范式、分层摘要（L0/L1/L2）与目录递归检索，刚好对应这三个问题。

---

## 3. 原理：这不是“传统 RAG”，而是“Agent-native 可写 RAG”

## 3.1 与传统 RAG 的区别

| 维度 | 传统 RAG | 本方案（Aelin + OpenViking） |
|---|---|---|
| 存储形态 | 平面 chunk + 向量索引 | 文件系统层级（按工作区/来源/目标/时间组织） |
| 写入能力 | 以离线入库为主，模型写入弱 | 追踪事件与 LLM 洞察可直接写入文件 |
| 检索路径 | top-k 一步召回 | 目录定位 -> 分层摘要 -> 递归下钻 |
| 可解释性 | 低 | 高（可见路径、可见文件） |
| 用户可控性 | 低 | 高（用户可直接查看/迁移/清理） |

## 3.2 一句话定义

> **DB 是运行时事实层，文件是长期语义层，OpenViking 是检索编排层。**

---

## 4. 与现有 Aelin 架构的对接点

当前后端已具备：

- 追踪目标：`TrackingTarget`
- 追踪快照：`TrackingSnapshot`
- 追踪变化：`TrackingChange`
- 调度与并发执行：`backend/app/services/tracking_autonomy.py`
- 对话规划中已有 tracking snapshot 注入：`backend/app/routers/aelin.py`

这意味着我们不需要推翻现有系统，只需要加一个“文件投影 + OpenViking 检索桥接层”。

---

## 5. 目标架构

```text
Track Scheduler (DB)
  -> Snapshot/Change 生成
  -> Memory Projector 写入文件树
  -> OpenViking 索引/分层摘要
  -> Chat Planner 检索（OpenViking find + read）
  -> LLM 回答 + 可选写回洞察文件
```

## 5.1 双层设计（推荐）

1. **事实层（DB）**
- 调度、状态机、重试、ACK、通知仍在 DB。
- 任何“可审计状态”都以 DB 为准。

2. **语义层（文件）**
- 把追踪结果投影为可读文件。
- 允许 LLM 写入 `insights`/`hypothesis`/`todo` 等语义文件。
- 用 OpenViking 做分层与递归检索。

---

## 6. 文件组织规范（建议）

建议在仓库外或数据目录下单独维护（避免污染源码），例如：

- `./data/aelin_memory/`

目录结构：

```text
/workspaces/{workspace}/tracking/{source}/{target_key}/
  profile.json
  timeline/
    2026-02-20T11-30-00Z_change.json
    2026-02-20T11-30-00Z_change.md
  snapshots/
    000123.json
  insights/
    daily_2026-02-20.md
    weekly_2026-W08.md
  .abstract
  .overview
```

说明：

- `profile.json`：目标元信息（interval/status/tags/notify_level 等）
- `timeline/*.json|md`：变化事件与自然语言摘要
- `snapshots/*.json`：快照原文（L2 深读）
- `insights/*.md`：LLM 写入的长期洞察（可人工编辑）
- `.abstract/.overview`：由 OpenViking 或辅助流程维护

---

## 7. 关键流程设计

## 7.1 写入流程（追踪 -> 文件）

在 `tracking_autonomy` 每次生成 `snapshot/change` 后触发：

1. 读取目标信息（workspace/source/target）
2. 规范化目标路径（安全文件名）
3. 写入：
- `timeline/<ts>_change.json`
- `timeline/<ts>_change.md`
- `snapshots/<version>.json`
4. 更新 `profile.json`
5. 通知 OpenViking 扫描/处理该目录

## 7.2 检索流程（对话 -> 记忆）

在 planner 阶段补充“文件记忆检索”：

1. 根据用户问题生成检索意图（source/target/time）
2. OpenViking `find` 定位高相关目录
3. 先读 `.abstract/.overview`
4. 必要时下钻 `timeline`/`insights`/`snapshots`
5. 回传证据片段给主回答生成器

## 7.3 写回流程（LLM -> 文件）

当回答结束且满足条件（如高置信总结）：

- 写入 `insights/daily_xxx.md`
- 标注来源：`derived_from`（关联 change/snapshot id）
- 禁止覆盖用户手写文件（仅新增或 append）

---

## 8. 实现计划（分阶段）

## Phase 1（最小可用）

- 新增 `memory_projector.py`（DB -> 文件）
- 仅投影 tracking changes/snapshots/profile
- 不改现有 chat，仅确保文件持续落地

验收：

- 每次追踪更新均有对应文件
- 用户可直接在文件系统查看完整变化历史

## Phase 2（接入检索）

- 新增 `openviking_bridge.py`
- 在 planner 增加 `retrieve_from_viking()`
- 将命中证据拼接到 `tracking_snapshot` 上下文

验收：

- chat 能基于历史追踪文件回答
- 命中证据可追溯到具体文件路径

## Phase 3（可写记忆）

- 引入 `insights` 写回策略（append-only）
- 增加“写回阈值/规则”与人工可见标注

验收：

- 对话后可见新增洞察文档
- 误写回率可控，可回滚

## Phase 4（前端可视化）

- Tracking Detail 增加“文件记忆”分栏
- 展示：路径、摘要、最后更新时间、跳转按钮

验收：

- 用户可从 UI 直接跳转到记忆文件视图/预览

---

## 9. 风险与控制

1. **一致性风险（DB 与文件偏差）**
- 控制：DB 为事实源；文件写入失败重试并告警。

2. **文件膨胀**
- 控制：分层归档（7 天细粒度，30 天聚合摘要）。

3. **LLM 写入污染**
- 控制：写入独立 `insights/`，不覆盖原始 timeline/snapshot。

4. **检索延迟**
- 控制：优先读 `.overview`，必要时再读详情。

---

## 10. 非目标（当前阶段明确不做）

- 不替换现有追踪调度器与 DB 状态机。
- 不做一次性“大迁移重构”。
- 不做复杂多租户权限模型（先个人单用户稳定）。

---

## 11. 对用户价值（最终呈现）

1. Aelin 会“记住并持续成长”，不是临时问答。
2. 记忆可见、可查、可改，不再黑盒。
3. 检索路径可解释，回答可追溯。

---

## 12. 立即可执行的下一步

1. 在 `backend/app/services` 增加 `memory_projector.py`。  
2. 在 `tracking_autonomy.py` 的 snapshot/change 成功分支挂接 projector。  
3. 输出第一版目录：`data/aelin_memory/workspaces/...`。  
4. 完成后再接 OpenViking bridge（避免一次改太多难排错）。

---

## 附：OpenViking 关键能力（用于本方案）

- 文件系统范式（统一上下文组织）
- 分层上下文（`.abstract` / `.overview` / 详情）
- 目录递归检索（先定位目录，再下钻内容）

这三点与 Aelin 的“长期追踪 + 可解释对话”目标高度一致。
