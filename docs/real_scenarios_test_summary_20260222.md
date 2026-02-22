# Real Scenario Test Summary (2026-02-22)

## 1) 链路验证（本地 + 网络并发）

- **通过实例**：`docs/real_scenarios_parallel_bruteforce_20260222.json`
  - Query: `先看日记，再并发本地和网络检索，NBA最近如何，一句话+三条要点。`
  - `local_search.status=completed`，`web_search.status=completed`
  - `message_hub.detail=merged local=6 web=12 file=8`
  - 说明：同一轮中本地证据、联网证据、文件记忆都进入合并流程。

## 2) 日记写入/检索触发

- **通过实例**：`docs/real_scenarios_test_20260222_v4_clean_workspace.json`
  - `chat_diary_write.status=completed`
  - `tracking/file-memory/search` 返回 `entry_kind=chat_diary`
  - `tracking/file-memory/tree` 返回主题树（`与主人的聊天日记`）

## 3) 日记可用性（语义可读 + 可追溯）

- **通过实例（真实文件）**：
  - `data/aelin_memory/users/1/workspaces/real_case_ws_20260222/diary/与主人的聊天日记/2026/02/22/2026-02-22T120441-523393-0000_聊天纪要-结合本地消息和网络最新信息-回答NBA近期变化.md`
- 该条目包含：
  - 自然语言结论（`## 今日对话`）
  - 关键线索列表
  - `source_indices_json` + `message_id` 索引
  - 可用于后续检索与追溯

## 4) Douyin 适配现状

- **验证文件**：`docs/real_scenarios_test_20260222_v4_clean_workspace.json`
- 结果：
  - `off_mode`: `422 auth_required`
  - `browser_mode`: `422 auth_required`
  - `file_mode`: `422 auth_required`
- 结论：
  - 错误链路与提示已正确（不会静默失败）。
  - 当前环境下仍缺“可用的 fresh cookies”，因此**未打通抓取成功**。

