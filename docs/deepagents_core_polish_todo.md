# DeepAgents Core Polish TODO

本文件只包含 P1 / P2 级的“精修”任务，都是在当前功能正确的前提下进一步统一风格和减少维护成本的改动。

## 1. 取消语义统一（P1）

- [ ] 抽出统一的 `is_cancelled` 帮助函数  
  - 从以下位置移除本地 `_is_cancelled` 实现：  
    - `backend/app/services/aelin/core.py`  
    - `backend/app/services/deepagents/deepagents_loop.py`  
    - `backend/app/services/deepagents/deepagents_graph.py`  
  - 在一个共享模块中提供统一实现（例如 `backend/app/services/deepagents/cancel_utils.py` 或 `backend/app/services/aelin/utils.py`），并让上述三处都依赖同一个函数。

- [ ] 为 stop_reason 引入取消常量  
  - 定义 `STOP_REASON_CANCELLED = "cancelled"` 常量（放在合适的共享模块中，例如 `aelin/loop_types.py` 或新建 `constants` 模块）。  
  - 将以下代码中的 `"cancelled"` 字面量替换为常量：  
    - `deepagents_loop.run_deepagents_loop` 的 `DeepAgentsCancelled` 分支  
    - `_try_agent_loop_chat` 中对 `result.stop_reason == "cancelled"` 的判断  
    - 相关测试中对 stop_reason 的字符串断言（保持语义一致）。

- [ ] 在取消短路前补一条 trace（可选但推荐）  
  - 在 `_try_agent_loop_chat` 中，当检测到 `_is_cancelled(cancel_token)` 或 `stop_reason == STOP_REASON_CANCELLED` 时，调用 `_emit_trace` 写入一条  
    - `stage="agent_loop"`  
    - `status="cancelled"`  
    - `detail="agent_loop_cancelled"` 类似的 trace  
  - 确保前端 Execution Pane 能区分“模型没答出来”和“用户主动取消”的场景。

## 2. stop_reason 常量化（P2）

- [ ] 整理所有 stop_reason 字符串并收敛到枚举/常量  
  - 识别当前代码中的 stop_reason 值，例如：  
    - `"cancelled"`  
    - `"llm_not_configured"`  
    - `"deepagents_unhandled_error"`  
    - `"empty_answer"`  
    - `"claims_opened_without_device_success"`  
    - `"claims_search_without_web_search_success"`  
  - 在一个公共位置定义这些常量或一个轻量枚举（例如 `AelinAgentStopReasons` 或简单的模块级常量）。  
  - 将 `deepagents_loop`、`aelin/core.py`、测试代码中的这些硬编码字符串替换为常量。  
  - 确认 `AelinAgentLoopResult.stop_reason` 的 docstring 或类型注释中同步反映这组可用值。

## 3. AgentMemoryService 语义瘦身（P2）

- [ ] 评估并整理 `_SOURCE_LABELS` / `_SOCIAL_SOURCES` 的必要性  
  - 位置：`backend/app/services/memory/agent_memory.py` 顶部的 `_SOCIAL_SOURCES` 与 `_SOURCE_LABELS`。  
  - 检查这些源是否只用于：  
    - 将 AGENTS.md 里旧数据投影成 context/citation 视图。  
  - 如确认不会再产生新的此类 source（旧 connector 已彻底移除），可以：  
    - 将 `_SOCIAL_SOURCES` 改为注释说明“仅为兼容历史记录而保留”，或  
    - 简化 `_SOURCE_LABELS` 为更通用的映射，例如仅保留几个常见标签，其余走默认 `title()` 规则。

- [ ] 将“UI 视图”职责从 AgentMemoryService 中轻微分层（仅结构调整，不改行为）  
  - 明确在类注释或代码结构中区分：  
    - DeepAgents 主循环相关方法（AGENTS.md 读写 + `build_system_memory_prompt`）  
    - UI/context 视图方法（`build_memory_layers_from_items`、focus_items/todos 系列）。  
  - 选项：  
    - 仅通过注释和分组整理代码块；  
    - 或新建一个轻量 wrapper（例如 `LegacyContextViewService`）来调用 `AgentMemoryService`，将纯 UI 方法挪过去，核心 memory 类只保留 DeepAgents 所需接口。

## 4. 测试 fake 工具/agent 的复用（P2）

- [ ] 抽取共用的 DeepAgents/Aelin 测试辅助模块  
  - 新建 `backend/tests/aelin_deepagents_test_utils.py`（或类似命名），包含：  
    - `_FakeToolHub`  
    - `_FakeRunner` / `_FakeAgent`  
    - 常用的 fake `AelinAgentLoopResult` 构造器等。  
  - 修改以下测试文件，引入并使用共用 helper，而不是各自重复定义：  
    - `backend/tests/test_aelin_preflight_perf.py`  
    - `backend/tests/test_aelin_tools.py`  
    - 如果有其他 DeepAgents 相关测试也定义了类似 fake，可以一并迁移。

- [ ] 在抽取过程中保持测试语义不变  
  - 确认迁移后：  
    - 所有断言仍然针对相同的调用 payload / trace / stop_reason。  
    - 不改变测试覆盖的逻辑路径（尤其是 cancel、images、system history 等关键分支）。  
