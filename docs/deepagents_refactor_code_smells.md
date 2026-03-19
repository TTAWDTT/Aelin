# DeepAgents 重构后代码“屎山”雷达图（backend）

> 范围说明：本文件聚焦 `backend/app/services` 下，**在 DeepAgents 重构之后仍然体量巨大或结构不佳的模块**，以及建议的后续精简方向。

## 一、整体行数分布概览

（基于当前分支的粗略统计）

- `app/services/media_ingest.py`：约 2047 行
- `app/services/aelin_chat_planning.py`：约 1993 行
- `app/services/aelin_tools.py`：约 1949 行
- `app/services/aelin_attachment_service.py`：约 1399 行
- `app/services/agent_memory.py`：约 1305 行
- `app/services/aelin_core.py`：约 1178 行
- `app/services/openviking_bridge.py`：约 1007 行
- `app/services/web_search.py`：约 838 行
- `app/services/aelin_planes.py`：约 641 行
- `app/services/aelin_loop_tools.py`：已在 DeepAgents 重构后阶段删除（旧 agent-loop 工具执行层，现为死代码）

在 DeepAgents 重构之前，这几个模块的代码数量更高；现在已经有了显著削减，但仍然存在明显“屎山”特征的模块，需要按优先级进一步处理。

---

## 二、从 DeepAgents 重构开始的整体精简量

以引入 DeepAgents 核心 stub 之前的 commit（`895bb4d feat(pinchtab): allow headed instance mode via settings`）为基线：

- **整个仓库**
  - 变更：`20 files changed, 1171 insertions(+), 3875 deletions(-)`
  - 净减少：约 **2700 行**

- **`backend/` 目录**
  - 变更：`17 files changed, 709 insertions(+), 3875 deletions(-)`
  - 净减少：约 **3160 行**

- **`backend/app/services/` 核心服务层**
  - 变更：`7 files changed, 518 insertions(+), 2868 deletions(-)`
  - 净减少：约 **2350 行**

删除的行数主要来自：

- 旧版 `AelinAgentLoop` 实现文件；
- `aelin_core` 中旧的“本地检索 + web 检索 + reply_agent + reply_verifier”主链及其 glue；
- planner 中直接耦合进 runtime 的 skill 注入 / 多轮规划 glue；
- 一些 rule-based fallback（例如 `_rule_based_answer` 等）。

新增的行数主要来自：

- `deepagents_loop.py`（DeepAgents 桥接层）；
- `skill_loader.py` 与 `backend/skills/*` 目录（skills 系统）；
- plane 工具的 trace 映射与 DeepAgents tool 暴露。

整体方向是：**通过 DeepAgents，把复杂的旧 agent loop 彻底拔掉，新增的桥接代码远少于删除的 legacy glue 代码**。

---

## 三、当前仍然存在的“屎山”模块与问题分级

### A 级：明显屎山 / 高优先级精简对象

#### 1. `app/services/aelin_loop_tools.py`（已删除）

- **状态更新**
  - 该模块在 DeepAgents 重构后已确认为完全未被引用的旧 agent-loop 工具执行层。
  - 在完成引用扫描和测试回归后，已整体从代码库中删除。

- **现状（删除前）**
  - 提供了一整套旧 agent-loop 使用的工具执行层函数：
    - `build_tool_calls_payload`
    - `plan_tool_calls`
    - `execute_tool_call`
    - `append_tool_result`
    - `flush_pending_reads`
    - 以及一堆日志/摘要/屏幕快照相关的 helper。
  - 这些函数的设计是围绕“LLM 原生 tool_calls + 批量 read 工具 + 并行执行”那套旧架构。
  - 在删除前：
    - 没有任何模块导入或调用 `aelin_loop_tools`；
    - DeepAgents 路径完全通过 `deepagents_loop.run_deepagents_loop` + `AelinToolHub.execute` 工作；
    - 对应的旧测试也已经在 `fff58e1 chore(tests): drop legacy agent loop tests` 中移除。

- **结论**
  - 该模块已作为死代码移除，不再参与任何运行或测试路径。

---

#### 2. `app/services/aelin_chat_planning.py`（约 1993 行）

- **现状**
  - 聚合了意图识别、工具规划、critic、web 查询构造、context boundary 分解等各种 planner 逻辑。
  - 同时存在多套实现：
    - `_extract_search_subject_dynamic` / `_extract_search_subject_legacy` + `_extract_search_subject` 包装；
    - `_build_web_query_pack_dynamic` / `_build_web_query_pack_legacy` + `_build_web_query_pack`；
    - `_decompose_web_context_boundaries_dynamic` / `_legacy` + `_decompose_web_context_boundaries`；
    - 以及大量 `_safe_xxx`、`_normalize_xxx`、`_parse_json_object` 等内部 helper。
  - 当前被 runtime 直接使用的部分已经极度收敛：
    - 在 `aelin_core` 中，只重新导入以下函数用于测试 & 工具箱：
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
    - 这些函数只在测试或“纯函数调用”场景中被使用，**agent runtime 已经不再依赖 planner 模块做路由**。

- **问题**
  - 文件体积接近 2000 行，职责混合：
    - 同时处理意图、工具规划、web 检索 query 变换、LLM JSON 解析、fallback 策略等。
  - 动态/legacy 双实现长期共存，即便实际 runtime 只用 dynamic 分支，大量 legacy helper 仍然保留。
  - 对于想阅读“当前 DeepAgents 架构下还需要的 planner 能力”的开发者来说，噪音非常大。

- **结论**
  - 属于“**有用 API 被大块历史遗留包裹着的屎山**”：
    - 需要在保障测试通过的前提下，把未被导出 API 使用的内部 helper 按批次清理；
    - 最终目标是让本文件收缩为“几十到几百行的纯函数工具箱”，只保留上述对外函数。

---

#### 3. `app/services/aelin_tools.py`（约 1949 行）

- **现状**
  - `AelinToolHub` 的集中实现文件，内部实现了所有 Aelin 工具：
    - 传统 read 工具：`context_get`、`profile`、`web_search`、`attachment_search` 等；
    - 设备与屏幕：`device`、`screen_get`；
    - browser plane 家族：`plane` + PinchTab-skill 协同；
    - Google Workspace via `gws` CLI：`google_workspace` 及其子 action；
    - PinchTab agent / session 系列：`pinchtab`、`pinchtab_agent`、`pinchtab_session`；
    - file-memory / ingest / 其他辅助工具。
  - 文件内函数数量（通过 `inspect` 粗数）约 48 个，且很多函数包含内联的“小状态机”和非 trivial 逻辑。
  - DeepAgents 通过 `AelinToolHub.tool_definitions()` + `execute(name, args)` 使用这些工具。

- **问题**
  - 职责极度混杂，几乎所有 tool domain 都塞在一个文件中：
    - browser plane 相关逻辑与 gws CLI、file-memory 工具并存，阅读一个 domain 时不得不扫过其他 domain 的实现。
  - 很多工具实现既做参数校验又包含多阶段调用/状态管理，内联在 `_tool_xxx` 中，难以复用和单独测试。
  - 虽然有一定测试覆盖（`tests/test_aelin_tools.py`、`tests/test_aelin_tool_policy.py` 等），但模块本身的结构对新开发者非常不友好。

- **结论**
  - 这是一个“**有测试兜底但结构上明显屎山**”的模块：
    - 需要按 domain 拆分为多个子模块（web_tools / gws_tools / browser_plane_tools / file_tools / skill_tools 等）；
    - `AelinToolHub` 变成一个协调/路由层，而不是所有逻辑的容器。

---

#### 4. `app/services/aelin_core.py`（约 1178 行）

- **现状**
  - 目前已经经过一轮较大的瘦身：
    - chat 主链统一为 `_try_agent_loop_chat` + `run_deepagents_loop`；
    - legacy `_aelin_chat_impl` 仅保留为 stub（调用即 `RuntimeError`）；
    - 旧时代的一整块“本地检索 + web 检索 + reply_agent + reply_verifier” glue 已删除；
    - `_rule_based_answer` 等 rule-based fallback 已被移除。
  - 同时，这个文件仍然承载了很多职责：
    - `/aelin/context` 相关：context bundle、daily brief、notifications、layout cards；
    - memory summary 与 memory snapshot 构造（虽然 snapshot 已大幅简化）；
    - SSE 流式 chat、trace 映射、附件 fallback 处理；
    - 各类 helper（profile injection、media URL 检测等）。

- **问题**
  - 职责过多：既是“核心服务层”又混合了大量“router 级别”的 glue 和 DTO 构造逻辑。
  - 即便 agent loop 本体已经简单很多，整文件阅读成本仍然偏高。
  - 对于只想了解 DeepAgents chat 流程的开发者来说，需要在单文件中跨大量辅助逻辑跳转。

- **结论**
  - 不再是“乱成一团”的屎山，但仍然是“**职责泛化的巨石**”：
    - 中长期看，应按功能拆成多个 service 文件（chat / context / brief / notifications），router 再组合；
    - 短期内的优先级低于前面三块，但在“整体后端变轻”这条路上值得列入规划。

---

### B 级：体积较大但相对聚焦的模块

这些模块行数多，但职责相对清晰，不算“混乱屎山”，更多是“重业务组件”：

1. `app/services/media_ingest.py`（约 2047 行）
   - 负责多平台媒体 ingest（YouTube / B 站 / 抖音等），涵盖抓取、转录、摘要、fallback。
   - 复杂度来自业务宽度；结构上相对聚焦。
   - 有专门文档与测试支撑（media ingest 相关 docs + `tests/test_media_ingest.py`）。

2. `app/services/aelin_attachment_service.py`（约 1399 行）
   - 负责附件解析、索引、file-memory 写入和 attachment_search 背后的逻辑。
   - 与 `file_memory_bridge` / `AgentMemory` 深度耦合。

3. `app/services/agent_memory.py`（约 1305 行）
   - 长期记忆的核心：summary、notes、todos、daily brief、notifications 等。
   - 代码多但集中在“记忆系统”这一域。

4. `app/services/openviking_bridge.py`（约 1007 行）
   - file-memory / 文档 ingest 与外部引擎（OpenViking）的桥接层。

5. `app/services/web_search.py`（约 838 行）
   - 聚合多搜索提供商、reader/http/browser fallback、search_and_fetch 等。

6. `app/services/aelin_planes.py`（约 641 行）
   - plane runtime 管理、task 状态、task snapshot 复用等。

这些模块可以在后续针对性重构，但优先级低于 A 级屎山。

---

## 四、当前功能是否受精简影响的简要结论

从 DeepAgents 重构开始到当前为止，关键能力通过以下测试/链路验证：

- Chat & agent loop：`tests/test_aelin.py` 中关于 chat endpoint、流式 SSE、loop 开关/硬失败/工具调用的测试全部通过；
- 媒体 ingest：`tests/test_media_ingest.py` 通过，且 `_try_agent_loop_chat` 中的媒体 URL 自动摘要逻辑保持；
- Web 搜索 & planner 工具箱：`tests/test_web_search.py`、`tests/test_aelin.py` 中的 intent/plan/critic 用例均通过；
- 工具与 plane / PinchTab / Google Workspace：`tests/test_aelin_tools.py`、`tests/test_aelin_tool_policy.py`、`tests/test_skill_loader.py`等全部通过；
- Remote control / bot 路径：`tests/test_remote_control.py` 通过，确认 remote_control 仍然路由到新的 `dispatch_aelin_chat`。

唯一明确下线的是：旧版基于多 agent 的 retrieval 主链（包括 reply_agent / reply_verifier 等），相关测试已用 `pytest.mark.skip` 标记为 legacy，不属于当前运行时的一部分。

---

## 五、后续精简优先级建议（概要）

1. **最高优先级（A1）**：删除 `aelin_loop_tools.py` 整个模块（死代码，且依赖已不存在的 helper）。
2. **高优先级（A2）**：对 `aelin_chat_planning.py` 做“API 护城河 + 内部大扫除”，仅保留对外导出的函数及其必要 helper。
3. **中高优先级（A3）**：按照 domain 拆分 `aelin_tools.py`，保持行为不变，仅重构结构。
4. **中期目标（A4）**：拆分 `aelin_core.py`，将 chat/context/brief/notifications 等服务分离。
5. **长期目标（B 级模块）**：在业务稳定后再对 `media_ingest.py`、`aelin_attachment_service.py`、`agent_memory.py` 等进行结构性优化。

详细的待办拆解与验收标准会在单独的 `deepagents_refactor_code_smells_todo.md` 中列出。
