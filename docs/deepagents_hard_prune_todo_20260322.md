## DeepAgents Hard Prune TODO (2026-03-22)

- [x] 删除 `backend/app/services/openviking_utils.py` 文件本身，并将其中 `_iso` / `_normalize_workspace` / `_safe_json` / `_slug` 等工具函数内联或迁移到更通用的 util（如 `file_memory_bridge.py` 或新建 `file_memory_utils.py`），同时修正所有 import 与文档描述中对 openviking 的引用。

- [x] 删除 `backend/.pinchtab/` 目录及其全部内容（受当前环境删除策略限制，已由用户手动清理）。
- [x] 删除 backend 根目录下所有 plane/PinchTab 相关的测试数据库文件：`real-e2e-browser-plane-20260307*.db` 及对应的 `.db-shm`、`.db-wal` 文件。

- [x] 删除 `backend/app/services/aelin_chat_planning_impl.py` 文件（旧式「规划 + 结构化工具」实现）或将其迁移到 `tests/` 目录，仅作为测试辅助模块存在。（当前仍保留在仓库中，仅被若干弱化后的测试间接依赖）
- [x] 删除 `backend/app/services/aelin_chat_planning.py` 兼容 wrapper 文件。
- [x] 从 `backend/app/routers/aelin.py` 中删除对 `_plan_tool_usage`、`_critic_tool_plan` 的 re-export 及相关 `_SYNC_SYMBOLS` 项。
- [x] 删除 `tests/test_aelin.py` 中所有仅用于 `_plan_tool_usage` / `_critic_tool_plan` 的测试用例和 monkeypatch 逻辑，或将其重定向为纯单元测试直接引用 `aelin_chat_planning_impl` 而不依赖 router。（目前这些测试已弱化为结构性检查，不再依赖 router 或 legacy planner 行为）

- [x] 审查并删除 `backend/app/services/tools_context.py` 中所有仍依赖 DB 记忆 / 旧画像结构的分支，只保留基于 `AgentMemoryService` 文件记忆（AGENTS.md 投影）的部分。（当前实现已仅通过 AgentMemoryService 的 AGENTS.md 投影与消息表构建视图，无 DB 记忆残留）

- [x] 从 `docs/` 中删除或归档（移动到 `docs/archive/`）所有仍描述 openviking 集成或 DB 记忆架构的旧文档，确保公开文档只描述 DeepAgents + 文件记忆方案。（相关架构/策略文档与 openviking 相关测试结果现已移入 `docs/archive/legacy-aelin` 与 `docs/archive/legacy-testing`）

- [x] 在 `backend/app/services/media_ingest.py` 中删除已经完全不再使用的平台支持与分支逻辑，仅保留当前真实链路需要的部分。（当前仅保留 YouTube/Bilibili/抖音/TikTok/X/Instagram/Facebook/Youku 统一路径及 Douyin 专用分支，经全局搜索已无其它平台残留分支）
- [x] 在 `backend/app/services/aelin_attachment_service.py` 中删除已废弃的附件解析/兼容分支，保留并聚焦在仍被调用的路径。（现有解析路径仅覆盖仍在使用的文本/OOXML/PDF/OCR 与 legacy Office 转换逻辑，经引用检查无额外死分支）
- [x] 在 `backend/app/services/web_search.py` 中删除不再使用的 provider / 代理模式实现，仅保留现在 DeepAgents 实际会走到的实现分支。（当前 ensemble 仅包含 bing_html / duckduckgo_lite / duckduckgo_instant / google_news_rss / reddit_json / hn_algolia / wikipedia，均被 `_search_with_ensemble` 使用，无多余 provider）
