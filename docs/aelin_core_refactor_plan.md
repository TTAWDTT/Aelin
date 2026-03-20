# aelin_core.py 职责梳理与拆分规划（draft）

本文件对应 DeepAgents 精简 TODO 中的 A4-1 / A4-2，用于描述 `backend/app/services/aelin_core.py` 当前的功能块与拆分方向。

## 现状功能块概览

按逻辑职责，可以将 `aelin_core.py` 粗分为以下几类：

1. **Chat 主链与 Agent Loop 入口**
   - 基于 DeepAgents 的主循环入口：
     - `_try_agent_loop_chat`
     - `dispatch_aelin_chat`（经由 `app.services.aelin_chat_dispatch` 的封装）
   - 负责 preflight（resolve_service / memory_summary / normalize_inputs / tool_hub_ready / runner_ready）与 DeepAgents 交互：
     - `_build_chat_runner_context`
     - `_build_tool_runner` / `_build_media_ingest_answer`
   - 对外暴露为 `/aelin/chat/stream` 路由。

2. **Context & Daily Brief（已抽离大部分实现）**
   - 仍留在 `aelin_core.py` 中的薄封装：
     - `_build_context_bundle`
     - `_build_cached_base_context_bundle`
   - 核心实现已迁移到独立 service：
     - `app/services/aelin_context_service.py` 中的：
       - `build_context_bundle`
       - `build_cached_base_context_bundle`
       - `_to_layout_cards`
       - `_build_fixed_profile_injection`
       - `_prune_ttl_cache`
   - 负责：
     - 汇总 user summary / notes / focus items / todos / pin recommendations；
     - 构造 `AelinDailyBrief` 与 layout cards；
     - 生成 `AelinMemoryLayers` 与 `AelinNotificationItem` 列表；
     - 提供 context endpoint 与 chat base context 所需的数据结构。

3. **Memory summary / notifications glue**
   - 通过 `AgentMemoryService` 提供：
     - `get_summary`、`list_notes`、`build_focus_items`、`list_todos`、`recommend_pins` 等；
   - `aelin_core.py` 现在只保留 `_memory` 全局实例与部分 glue（采用 `aelin_context_service` 来构造 bundle）。

4. **Media ingest glue**
   - 入口 helpers：
     - `_MEDIA_URL_RE` 及 `_MEDIA_SUMMARY_HINTS_*`；
     - `_extract_media_urls_from_text`
     - `_build_media_ingest_answer`（来自 `aelin_media_pipeline`）；
   - 承担：
     - 从用户文本中检测媒体 URL；
     - 调用 `media_ingest_service` 生成媒体摘要并注入回答。

5. **ToolHub / Plane / PinchTab 协同**
   - 将 `AelinToolHub` 暴露给 DeepAgents / 规划层使用：
     - `run_aelin_structured_tools`
     - `should_attempt_aelin_tools`
     - `should_resume_active_plane_for_query`
     - `summarize_tool_results_for_prompt`
   - 通过 `get_active_plane_task` 与 plane runtime 协作，在 chat 主链中为 browser plane 提供状态与恢复策略。

6. **Proactive / Layout / Notifications（轻量 glue）**
   - 与 `AgentMemoryService` / `sync_jobs` 协同，构建：
     - Proactive state
     - Layout 卡片（通过 `_to_layout_cards`，现已在 context service 中实现）
     - Notifications feed

## 已完成的拆分（A4-2）

- **Context / brief / notifications 核心逻辑已抽至 `aelin_context_service.py`：**
  - 包含：
    - `build_context_bundle`
    - `build_cached_base_context_bundle`
    - 以及相关 layout / brief / notifications / memory layers 构造逻辑。
  - `aelin_core.py` 现在只保留薄封装函数：
    - `_build_context_bundle`：
      - 仅负责 workspace 归一化；
      - 调用 `build_context_bundle(db, user_id, workspace=workspace_norm, query=query, memory_service=_memory)`。
    - `_build_cached_base_context_bundle`：
      - 仅负责 workspace 归一化；
      - 调用 `build_cached_base_context_bundle(..., memory_service=_memory, ttl_seconds=_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS, max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES, cache=_base_context_cache, lock=_base_context_cache_lock)`。

- **对外 API 完全兼容：**
  - `/aelin/context` / chat base context 使用路径未变；
  - `test_aelin.py::test_aelin_context_and_chat_endpoints` 等集成测试全部通过。

## 后续拆分/精简方向（A4-3 草案）

1. **进一步收窄 `aelin_core.py` 职责：**
   - 将与 proactive state / layout cards / notifications 相关的 glue 提炼为独立 service（例如 `aelin_proactive_service`），chat 主链只保留调用入口。
   - 梳理 `_empty_memory_snapshot`、`_build_cached_memory_snapshot` 以及旧 retrieval 相关 helper，确认哪些仍被 DeepAgents 使用，哪些可以安全移除或迁移。

2. **清理未被调用的内部 helper：**
   - 借助简单的静态扫描（或 vulture）辅助，列出 `aelin_core.py` 中未被引用的函数；
   - 在保证测试通过的前提下逐步删除。

3. **目标形态：**
   - `aelin_core.py` 主要负责：
     - FastAPI 路由与请求参数校验；
     - chat 主链 glue（调用 DeepAgents / ToolHub / context/media services）；
     - 少量向后兼容的 helper。
   - 所有重逻辑（context / brief / notifications / media ingest / plane runtime 等）都托管在 `app/services/*` 子模块中。
