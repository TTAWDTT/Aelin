# DeepAgents 重构后“屎山”精简待办清单

> 说明：本文件只包含待办项和验收标准，详细背景见：`docs/deepagents_refactor_code_smells.md`。

## A1. 删除 `aelin_loop_tools.py` 死代码模块

- [x] **A1-1 删除模块文件**
  - 操作：
    - 移除 `backend/app/services/aelin_loop_tools.py` 文件。
    - 清理项目中所有对 `aelin_loop_tools` 的导入（理论上当前为 0）。
  - 验收标准：
    - `rg "aelin_loop_tools" backend` 无任何匹配（仅允许在历史文档中出现）。
    - 后端关键测试集（如 `test_aelin.py`、`test_aelin_tools.py`、`test_aelin_tool_policy.py`、`test_media_ingest.py`、`test_web_search.py`、`test_remote_control.py`、`test_skill_loader.py` 等）全部通过。

- [x] **A1-2 更新相关文档**
  - 操作：
    - 在 `docs/deepagents_arch.md` 或相关文档中，补一句说明：旧 agent-loop 工具执行层已完全淘汰。
  - 验收标准：
    - 技术文档中不再将 `aelin_loop_tools` 视为现存运行模块，仅在历史/变更记录中出现。

---

## A2. 精简 `aelin_chat_planning.py` 为纯函数工具箱

- [ ] **A2-1 明确对外 API 列表并锁定**
  - 操作：
    - 在 `aelin_chat_planning.py` 顶部或单独 docs 中，显式列出当前“对外支持”的函数：
      - `_build_intent_contract`
      - `_plan_tool_usage`
      - `_critic_tool_plan`
      - `_build_web_query_pack`
      - `_build_retry_web_queries`
      - `_extract_search_subject`
      - `_decompose_web_context_boundaries`
      - `_normalize_search_mode`
      - `_is_time_sensitive_query`
      - `_is_sports_result_query`
  - 验收标准：
    - `app.routers.aelin` 对应的 tests（`test_time_sensitive_detection_covers_recent_sports_query`、`test_plan_tool_usage_invalid_json_fallback_still_dispatches_web` 等）全部通过。

- [ ] **A2-2 删除未被上述 API 使用的 legacy helper**
  - 操作：
    - 按小批次分析 `_xxx_dynamic` / `_xxx_legacy` 中哪些仅被 legacy 路径调用；
    - 删除完全未被对外 API 引用的 helper 函数（含 `_safe_*`、`_parse_json_object`、旧 route glue 等）；
    - 每次删除一块后运行相关 tests（`tests/test_aelin.py`、`tests/test_web_search.py`、planner 相关用例）。
  - 验收标准：
    - `aelin_chat_planning.py` 中不存在未被引用的私有函数（`python -m pip install vulture` 后，可选用 vulture 或静态分析辅助确认）。
    - 删除过程中新引入的所有变动均被 tests 覆盖，没有新增 `skip`。

- [ ] **A2-3 收缩文件体积并按职责分段**
  - 操作：
    - 将剩余工具函数按职责合理分段（例如 Intent、Plan、Critic、WebQueries、ContextBoundaries 等）；
    - 保持在单文件内，但结构清晰，便于未来（可选）按模块拆分。
  - 验收标准：
    - `aelin_chat_planning.py` 行数显著低于当前 ~2000 行（目标：< 800 行，允许后续迭代达成）。
    - 新开发者阅读该文件时，可以在 5 分钟内理解“每个对外 API 对应哪一段代码”。

---

## A3. 按 domain 拆分 `aelin_tools.py`

- [ ] **A3-1 为 ToolHub 设计模块划分方案**
  - 操作：
    - 在 docs 中写出预期拆分结构，示例：
      - `app/services/tools_web.py`（web_search / crawl4ai 等）
      - `app/services/tools_gws.py`（google_workspace 及子 action）
      - `app/services/tools_browser_plane.py`（plane + PinchTab 协同）
      - `app/services/tools_files.py`（attachment_search / file-memory 工具）
      - `app/services/tools_skill.py`（skill loader / skill 工具）
    - 规划 `AelinToolHub` 如何引用这些子模块（组合或委托）。
  - 验收标准：
    - 设计文档经过人工 review（你本人认可），并与现有 `AelinToolHub` 责任边界一致。

- [ ] **A3-2 把单一 domain 的 `_tool_xxx` 提取到子模块**
  - 操作：
    - 先选择一个相对独立的 domain（例如 Google Workspace 或 web_search）；
    - 将其 `_tool_xxx` 逻辑和相关 helper 移动到新的子模块中；
    - 在 `AelinToolHub` 中通过 import + 委托调用保持行为不变；
    - 运行 `tests/test_aelin_tools.py` 与相关 tests 确认无行为变化。
  - 验收标准：
    - 拆出的子模块没有引用 `AelinToolHub` 内部私有状态（除非通过显式注入）；
    - 对应 domain 的工具行为在 tests 中完全一致（响应字段、错误码等不变）。

- [ ] **A3-3 分阶段完成所有主要 domain 的拆分**
  - 操作：
    - 按 domain 依次迁移 web / gws / plane+PinchTab / files / skill 等；
    - 每完成一个 domain 拆分就运行全套工具相关 tests + 少量 chat 集成 tests。
  - 验收标准：
    - 最终 `aelin_tools.py` 行数显著下降（目标：< 600 行），主要负责：
      - ToolHub 类定义；
      - 子模块注册与统一路由；
      - 少量跨 domain glue（如工具定义列表）。
    - 所有工具相关 tests（`test_aelin_tools.py`、`test_aelin_tool_policy.py`、涉及工具的 chat 用例）继续全绿。

---

## A4. 拆分 `aelin_core.py` 的多重职责

- [ ] **A4-1 梳理 `aelin_core` 所有路由/功能块**
  - 操作：
    - 按功能分类标注当前 `aelin_core.py` 的主要块：
      - Chat 主链（`_try_agent_loop_chat` 等）
      - Context & Daily Brief（`_build_context_bundle`、`_build_cached_base_context_bundle` 等）
      - Memory summary / notifications
      - Media ingest glue（媒体 URL 自动摘要）
      - Attachment fallback 逻辑
    - 在 docs 中记录这些块的边界和依赖。
  - 验收标准：
    - 有一份简明的功能/依赖列表，新人可以用它快速定位具体逻辑位置。

- [ ] **A4-2 将 context/brief/notifications 提取到独立 service 模块**
  - 操作：
    - 新建例如 `app/services/aelin_context_service.py`（命名待定），迁移：
      - context endpoint 所依赖的 `_build_context_bundle` 和相关 helper；
      - daily brief / notifications / layout 相关逻辑；
    - 保持 `app.routers.aelin` 的 API 兼容，只是调用路径从 `aelin_core` 转到新模块。
  - 验收标准：
    - 所有与 context/brief/notifications 相关的 tests 通过（包括 `test_aelin_context_and_chat_endpoints` 等）；
    - `aelin_core.py` 中不再包含大块 context/brief 逻辑，仅保留 chat 主链和少量 glue。

- [ ] **A4-3 清理不再需要的内部 helper**
  - 操作：
    - 在模块拆分完成后，检查 `aelin_core.py` 中仍存在但未被调用的 helper 函数；
    - 逐步删除这些 helper，删除后跑相关 tests。
  - 验收标准：
    - `aelin_core.py` 行数进一步减少（目标：< 800 行，重点是 chat 相关逻辑）；
    - 静态分析工具（可选）报告无明显未引用函数。

---

## B 级模块后续优化（低优先级占位）

> 以下为体积较大但相对聚焦的模块，暂不立刻动，只占位记录，方便未来拉出专门 refactor 计划。

- [ ] **B1 评估 `media_ingest.py` 的可分块重构可能性**
- [ ] **B2 评估 `aelin_attachment_service.py` 的模块切分与依赖梳理**
- [ ] **B3 评估 `agent_memory.py` 中“核心记忆接口”与“派生功能（daily brief / notifications）”的分离**
- [ ] **B4 审视 `openviking_bridge.py`、`web_search.py`、`aelin_planes.py` 的单一职责情况**

每一项在真正执行时，应再拆分为更细致的 TODO + 验收标准。
