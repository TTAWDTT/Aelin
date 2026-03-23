# DeepAgents 核心重构 TODO（一次性替换 Aelin Agent Loop）

> 目标：在当前分支中 **完全移除自研 AelinAgentLoop**，用 DeepAgents + LangGraph 搭建新的唯一 Agent Loop，实现与当前 Aelin 等价或更强的能力，同时让代码结构更简洁、易维护。

---

## Phase 1：接 DeepAgents 骨架，保持对外行为不变

- [ ] **完成 DeepAgents Loop 骨架（`run_deepagents_loop`）**
  - 验收标准：
    - 存在 `backend/app/services/deepagents_loop.py`，导出 `run_deepagents_loop(...) -> AelinAgentLoopResult`。
    - 在不暴露任何工具的情况下，能够调用 DeepAgents graph 并返回一个非空回答。
    - 错误路径（LLM 未配置 / DeepAgents 异常）会返回 `AelinAgentLoopResult(ok=False, stop_reason=...)`，同时附带至少 1 条 `AgentLoopTraceStep(stage="agent_loop", status="failed", detail=...)`。

- [ ] **在 `aelin_core._try_agent_loop_chat` 中用 DeepAgents 替换 AelinAgentLoop**
  - 验收标准：
    - `backend/app/services/aelin_core.py` 中不再 import 或实例化 `AelinAgentLoop`。
    - `_try_agent_loop_chat` 在 preflight 结束后只调用 `run_deepagents_loop(...)`。
    - `/api/v1/aelin/chat` 与 `/api/v1/aelin/chat/stream` 接口签名、SSE 事件格式保持不变（前端无需改动即可正常工作）。

- [ ] **保证现有集成测试基本通过（允许工具相关测试暂时失败 / 调整）**
  - 验收标准：
    - `backend/tests/test_aelin.py` 中的「基础聊天」用例通过（不要求立即执行工具）。
    - 以 DeepAgents 为核心的路径不会触发 `_aelin_chat_impl` 旧路径（除非 loop 明确返回 no result）。

---

## Phase 2：将 Aelin 工具挂到 DeepAgents Graph

- [ ] **设计 AelinToolHub → DeepAgents Tool 的适配层**
  - 验收标准：
    - 有一个清晰的工具适配模块或函数（可以放在 `deepagents_loop.py` 或独立文件），负责：
      - 接收 `AelinToolHub`、provider 等上下文；
      - 返回一组 DeepAgents / LangChain Tool 对象（每个工具包含名称、描述、参数 schema）。
    - 明确哪些工具在第一批接入：至少包括 `web_search`、`crawl4ai_fetch`、`google_workspace`（只读）、`device`、`plane`（browser）。

- [ ] **在 DeepAgents config 中挂载这些工具**
  - 验收标准：
    - `create_deep_agent(...)` 调用中不再使用空 `tools=[]`，而是使用适配层返回的工具列表。
    - DeepAgents 通过 tool-calling 能够调用至少一个 Aelin 工具，并在 `AelinAgentLoopResult.tool_runs` 中体现（name / args / status / latency）。

- [ ] **把 `AelinToolPolicy` 的写操作限制移植到工具 wrapper**
  - 验收标准：
    - 写类工具（gmail_send、docs_create、calendar_create_event、plane delegate 等）在 DeepAgents Tool wrapper 中会：
      - 检查当前调用计数是否超过 `aelin_agent_loop_max_write_calls` 等配置；
      - 超限时返回清晰的错误信息，而不是静默失败。
    - `AelinAgentLoopResult.write_calls` 统计正确反映 DeepAgents 期间的写工具调用次数。

---

## Phase 3：Trace 与前端 Execution Pane 对齐

- [ ] **将 DeepAgents 的工具调用映射到 `AgentLoopToolRun`**
  - 验收标准：
    - 对于每次 DeepAgents 工具调用，都会在 `AelinAgentLoopResult.tool_runs` 中追加一条 `AgentLoopToolRun`，包含：
      - `round_index`（可简单从调用顺序推导）；
      - `name`（工具名，与前端和技能文档一致）；
      - `args`（JSON 反序列化后的参数字典，敏感信息可按现有规则做脱敏）；
      - `status`（`completed`/`failed` 等）；
      - `latency_ms`（粗略时间也可）。

- [ ] **将 DeepAgents 中间阶段映射到 `AgentLoopTraceStep`**
  - 验收标准：
    - 至少包含以下几个 trace 阶段：
      - `stage="agent_loop.plan"`：DeepAgents 内部规划 / todo 拆分阶段；
      - `stage="agent_loop.tools"`：一轮或多轮工具调用阶段；
      - `stage="agent_loop.final_answer"`：最终回答生成阶段。
    - 前端右侧 Execution Pane 在新的 DeepAgents loop 下仍能展示：
      - Aelin 链路（预处理 + DeepAgents 核心阶段）；
      - 工具调用链（tools tab）；
      - plane 链路（当涉及 plane 工具时）。

- [ ] **保持 SSE trace 事件格式不变**
  - 验收标准：
    - `aelin_chat_stream` 中 `trace` 事件的 payload 仍然是 `{ "step": AelinToolStep }`。
    - 流式聊天中 trace 步骤的时序大致正确：preflight → DeepAgents 核心 → final / done。

---

## Phase 4：文件工具与 DeepAgents FS 集成

- [ ] **选定 DeepAgents 文件后端使用策略**
  - 验收标准：
    - 文档中明确：DeepAgents 的 `StateBackend` 被视为「Aelin agent 的临时工作目录」。
    - 说明 Aelin 现有附件 / OCR 管道如何与 DeepAgents FS 交互（例如：将附件转存到工作目录，再由 DeepAgents 文件工具访问）。

- [ ] **替换旧的“文件工具”为 DeepAgents 内置 FS 工具**
  - 验收标准：
    - 旧的 file 相关工具（若存在）从 `AelinToolHub` 的工具列表中移除或标记为 deprecated。
    - DeepAgents 文件工具 (`ls/read_file/write_file/edit_file/glob/grep`) 对 agent 可见，并可在 tool trace 中看到对应调用。
    - 至少一个用户场景验证：让 agent 基于文件内容进行分析 /总结时，会使用 DeepAgents FS 工具，而不是旧的文件工具路径。

---

## Phase 5：彻底移除旧 AelinAgentLoop 及相关代码

- [ ] **删除 `AelinAgentLoop` 实现文件**
  - 验收标准：
    - `backend/app/services/aelin_agent_loop.py` 文件被移除，不再被任何模块 import。
    - 相关辅助模块（`aelin_loop_round.py`、`aelin_loop_tools.py`、`aelin_loop_message.py`、`aelin_loop_logging.py`、`aelin_loop_actions.py`）如若仅服务旧 loop，也一并删除或合并到新实现中。

- [ ] **更新 / 删除与旧 loop 强耦合的测试**
  - 验收标准：
    - `backend/tests/test_aelin_agent_loop.py`、`backend/tests/test_aelin_preflight_perf.py` 等旧 loop 专用测试被删除或改写为 DeepAgents 版本。
    - `backend/tests/test_aelin.py` 中与 agent loop 行为强绑定的断言（例如工具调用次数、特定错误消息）更新为 DeepAgents 新语义。

---

## Phase 6：功能对齐与回归验证

- [ ] **列出当前 Aelin loop 的关键能力清单，并逐项对齐**
  - 验收标准：
    - 文档中有一张 checklist，至少包括：
      - 普通对话（无工具）；
      - web_search / crawl4ai 读取网页并总结；
      - gws 读操作（gmail list、calendar list 等）；
      - gws 写操作（docs_create、calendar_create_event、gmail_send 等）；
      - device 工具（open_url 等）；
      - plane 工具（browser plane delegate/status/continue）； 
      - memory 使用（AgentMemoryService）；
      - SSE / Execution Pane 展示。
    - 每一项都有“DeepAgents 版本已覆盖 / 待覆盖 / 明确不支持”的标记。

- [ ] **在当前分支内跑一轮端到端手动测试**
  - 验收标准：
    - 使用本地 Aelin UI，从 Chat 页执行上述关键能力，确认：
      - DeepAgents loop 正常工作，未走 `_aelin_chat_impl` 旧路径；
      - 右侧 Execution Pane 能显示合理的链路与工具调用；
      - 无明显回归（例如 SSE 断流、trace 缺失导致前端报错）。

