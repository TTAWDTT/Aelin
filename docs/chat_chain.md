# Aelin Chat 实际链路追踪（基于真实运行）

## 1) 追踪样本与数据来源

- 追踪文件：`docs/chat_chain_trace_20260222.json`
- 追踪生成时间：`2026-02-22T12:12:17Z`
- 工作空间：`chat_chain_trace_ws`
- 用户：`user_id=1`
- 选中的主查询：`请并发本地检索和联网搜索，告诉我NBA最近如何，先给结论。`
- 追问查询：`根据你刚才的日记，NBA里谁状态回升？`

> 说明：以下内容全部来自这份真实 trace，不是假设流程。

## 2) 主查询的完整执行链路（真实阶段）

### A. 意图与规划阶段

1. `intent_lens`：识别为 retrieval、freshness 24h（completed）
2. `plan_critic`：规则审查通过（completed）
3. `query_decomposer`：拆出 5 个 web 子查询（completed）
4. `main_agent`：路由决策为 local+web 并发，trace 关闭（completed）
5. `reply_agent` / `reply_dispatch`：进入回复执行（completed）

### B. 本地/网络并发检索阶段

6. `local_search`（completed）  
   - `local_search_subagent_1`：命中 6 条本地证据
7. `web_search`（completed）  
   - 共 5 个 web 子代理：2 个 completed、3 个 failed(no result)  
   - 总 web 命中 12 条

### C. 证据汇聚与生成阶段

8. `message_hub`：合并结果 `local=6, web=12, file=2`（completed）
9. `file_memory_search`：命中文件记忆 2 条（completed）
10. `generation`：规则生成（`rule_based with local evidence`）
11. `grounding_judge`：通过（completed）
12. `coverage_verifier`：失败（`missing_score_evidence`）
13. `reply_verifier`：失败（同上）

### D. 记忆写入阶段

14. `insight_write`：跳过（`llm_not_configured`）
15. `chat_diary_write`：成功写入 1 条  
    - 路径：`data/aelin_memory/users/1/workspaces/chat_chain_trace_ws/diary/与主人的聊天日记/2026/02/22/...md`

---

## 3) 追问链路（验证“先看日记再回答”是否打通）

追问：`根据你刚才的日记，NBA里谁状态回升？`

关键观察（真实）：

- `local_search` 仍命中 6 条
- `web_search` 仍命中 12 条（3 个子查询失败）
- `file_memory_search` 命中从 2 增至 4（说明上一轮写入已可被检索）
- `chat_diary_write` 再次成功写入 1 条新聊天日记

结论：**日记写入 -> 下轮命中 -> 参与回答上下文** 这条链路已真实打通。

---

## 4) “一问一答”内部数据流（按代码与 trace 对齐）

1. 用户问题进入 `/api/v1/aelin/chat`
2. 规划器决定 `need_local_search` 与 `need_web_search`
3. 本地与网络各自子任务并发执行
4. `message_hub` 合并 `local + web + file_memory`
5. 生成回答（rule-based 或 LLM）
6. 质量校验（grounding / coverage / reply verifier）
7. 按策略写入：
   - tracking insight（条件满足才写）
   - chat diary（当前默认每轮写）
8. 下轮请求通过 `file_memory_search` 回收 diary 内容

---

## 5) 当前真实状态与问题点

### 已打通

- local/web 并发执行已生效
- 日记自动写入已生效
- 日记可在后续请求中被检索命中

### 仍存在的问题（trace 已证实）

- NBA 查询的 web 结果相关性偏低（出现大量泛“联网搜索教程”内容）
- `coverage_verifier` 连续失败（缺少比分/战报类硬证据）
- `insight_write` 在该轮被 `llm_not_configured` 跳过

---

## 6) 本次 trace 的链路判定

- **链路完整性**：通过（请求→检索→汇聚→生成→写日记→回读）
- **并发性**：通过（local 与 web 同轮并行）
- **记忆回流性**：通过（追问命中 diary）
- **答案质量稳定性**：未达标（体育时效场景证据相关性不足）

