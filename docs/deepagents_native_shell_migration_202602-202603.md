# 从 Aelin 壳到 DeepAgents 原生壳（2026-02 ～ 2026-03 小记）

> 这份文档只聚焦一件事：  
> **Aelin 后端如何从“自研 Agent Loop + DB 记忆 + plane/pinchtab”一路收敛到 “DeepAgents 原生壳 + 文件记忆 + 轻量能力服务”。**  
> 如果想看更长的情绪版回顾，可以翻 `docs/aelin_deepagents_journey_202602.md`。

---

## 1. 起点：多套 Agent Loop 与厚重记忆（2026-02 上旬）

- Aelin 一开始有自己的一整套 Agent Loop：
  - DB 表承载 conversation memory / notes / todos / tracking evidence；
  - 追踪调度器 + 通知中心负责“主动提醒”；
  - `/aelin/chat/stream` SSE 协议里塞满了 stop_reason / stage / tool_trace。
- 这套体系可以工作，但代价是：
  - agent loop + 记忆 + 追踪 + plane/pinchtab 各自有胶水代码；
  - service 层和测试一起长成了典型“屎山”。

这一阶段的关键词是：**“什么都要自己写”**。

---

## 2. DeepAgents 接管 Agent Loop（2026-03-19 ～ 03-20）

这一小段是决定性的转折：

1. **DeepAgents 作为唯一 Agent Loop**
   - 在 `app/services/deepagents/deepagents_graph.py` 里建立统一的 `build_chat_agent()` 出入口：
     - `_build_chat_model(...)` 通过 `LLMService` 封装任意 OpenAI-compatible provider；
     - `build_chat_tools(...)` 注册 `web_search` / `attachment_search` / `google_workspace` / `device` / `screen_get` 等工具；
     - `create_deep_agent(...)` 组合 model + tools + skills + memory + middleware。
   - `run_deepagents_loop(...)` 成为唯一的“拉一次 DeepAgents Agent Loop 并给出结果”的函数。

2. **Aelin 退居壳层**
   - `app/services/aelin/core.py` 不再实现 Agent Loop，而是：
     - 做 preflight：resolve provider、归一化 workspace、整理 history / images / attachments；
     - 调用 `run_deepagents_loop(...)`；
     - 把 DeepAgents 的结果包装成 `AelinChatResponse`（answer + actions + tool_trace）。
   - `/aelin/chat` 与 `/aelin/chat/stream` 变成这一包装层的 HTTP/SSE 壳，方便兼容现有调用方。

3. **AGENTS.md 作为唯一长期记忆**
   - 通过 `AgentMemoryService` + `file_memory_bridge`：
     - 把 DeepAgents 的 `memory_snapshot` 写入 `/memory/AGENTS.md`；
     - `/aelin/context` 只读 AGENTS.md，投影 summary / notes / todos；
     - 不再依赖 DB 记忆表和 openviking runtime。

这一阶段结束时，**Agent Loop 已经完全是 DeepAgents**，Aelin 只负责把本地世界塞给 DeepAgents、再把结果还原成自己的 API 结构。

---

## 3. 原生壳：直接透出 DeepAgents Streaming 协议（2026-03-21 ～ 03-23）

为了摆脱旧 SSE 协议和 stop_reason/tool_trace 绑定，我们又做了三件事：

1. **新增 `/api/v1/deepagents/chat/stream`**
   - `app/routers/deepagents_chat.py`：
     - 做认证、解析 provider/model/workspace；
     - 调用 `build_chat_agent(...)` 构造 DeepAgents Agent；
     - 直接使用 `agent.stream(input, config=...)`，把 streaming chunk 原样包进 SSE `event: chunk`。
   - 事件中只保留 DeepAgents 自己的字段（`version/type/data/...`），不再伪造 stop_reason 或 stage。

2. **前端 Chat 链路改挂 DeepAgents 壳**
   - `frontend/src/shared/api/sse.ts`：
     - 请求目标改为 `/api/v1/deepagents/chat/stream`；
     - 识别 DeepAgents `type === "messages"` / `"updates"` 事件，拼装回答；
     - 在 `final` 事件上读取后端附加的 `tool_runs`，作为工具调用列表。
   - `ExecutionPane` / `AgentTracePanel`：
     - 不再尝试还原旧的阶段型 trace；
     - 只消费 `DeepAgentsToolRun[]`，用最小的信息（name/args/status/latency/summary）重建一条简洁的执行时间线。

3. **Aelin 壳与 DeepAgents 壳并存（过渡期）**
   - `/aelin/chat*` 继续存在，供旧调用方使用；
   - 新前端与未来的 SDK 客户端都推荐直接使用 `/deepagents/chat/stream`；
   - `docs/deepagents_native_shell_todo_20260324.md` 里把 `/aelin/*` 明确标记为“兼容层”，而不是主链路。

这一阶段完成后，可以说：**DeepAgents 自己的事件模型已经直接对外暴露，Aelin 不再发明第二套 streaming 协议。**

---

## 4. 最后一公里：删掉“只为旧协议活着”的代码（2026-03-23 ～ 03-24）

在这一波里，我们做的是“扫尾”而不是“加功能”：

1. **后端服务目录瘦身**
   - `app/services/aelin/*` 只保留：
     - `core.py`：/aelin/chat* 兼容壳 + preflight glue；
     - `context_service.py` / `core_support.py`：上下文与缓存辅助；
     - `tool_hub.py` / `tool_policy.py` / `loop_types.py`：DeepAgents bridge；
     - `attachment_service.py` 等真正 domain service。
   - plane/pinchtab、openviking、DB 记忆 runtime 的源文件已全部删除，只在 `docs/archive/legacy-aelin/` 中保留历史说明。

2. **测试与脚本的整理**
   - `backend/tests/` 仅保留：
     - DeepAgents 壳、工具、记忆、web_search、remote_control 等现存能力的测试；
     - 一小部分 `/aelin/chat*` 测试，用于保证兼容壳仍然工作。
   - 调试脚本（如 `debug_deepagents_probe.py`）也只围绕 DeepAgents graph，而不再触及旧 Agent Loop。

3. **代码体积回落到 2.3 万行附近**
   - 2026-03-22 snapshot（见 `docs/deepagents_22k_lines_todo_20260322.md`）：约 3.76 万行功能代码；
   - 2026-03-24 本次 native shell 完成后重新统计：
     - 后端 Python：**13,721 行**  
     - 前端核心：**5,411 行**  
     - Desktop 壳：**4,340 行**  
     - 合计 ≈ **23,472 行**
   - 在保留 web_search / attachments / device / GWS / skills / remote control 等能力的前提下，Aelin 已经从“多套 Agent Loop + 多层 DB 记忆 + plane/pinchtab”收敛成“**DeepAgents 原生壳 + 轻量能力服务**”。

---

## 5. 现在的状态：Aelin = DeepAgents 原生壳 + 能力服务

把现在的形态总结成一句话：

> **Aelin 后端就是：HTTP 壳 (`/api/v1/deepagents/*` + 少量兼容型 `/api/v1/aelin/*` 非聊天接口) + DeepAgents graph + 几个独立的 domain service（web_search / attachments / device / Google Workspace / skills）。**

这意味着：

- 想改 Agent 行为 → 去看 DeepAgents 的 graph / middleware / skills；
- 想加新能力 → 在 Aelin 这边写一个干净的 service + DeepAgents 工具 wrapper；
- 想看执行链路 → 前端 Execution Pane 直接基于 DeepAgents 的 tool runs / run graph 渲染；
- 想改记忆 → 改 `/memory/AGENTS.md` 与 DeepAgents MemoryMiddleware，而不是再加 DB 表。

---

## 6. 收尾标记与 Legacy 提示

- 聊天主入口：
  - 现在唯一的聊天流式入口是 `/api/v1/deepagents/chat/stream`。
  - `/api/v1/aelin/chat` / `/api/v1/aelin/chat/stream` 已在代码中下线，仅在历史文档中保留。
- Legacy Aelin Agent Loop：
  - 旧的 Aelin Agent Loop / stop_reason / plane/pinchtab 相关实现全部归档到 `docs/archive/legacy-aelin/`。
  - 任何新功能都不应再依赖这些概念。

---

## 7. 给未来的开发者的一点建议

- 如果你要扩展 Aelin：
  - 优先阅读：`docs/deepagents_arch.md` 和 DeepAgents 官方文档；
  - 把 Aelin 当成一个“带工具和 UI 的 DeepAgents 壳”，而不是一个要自己实现 Agent Loop 的系统。
- 如果你发现某个模块里还有 plane/pinchtab/openviking/legacy memory 的影子：
  - 欢迎继续删；  
  - 只要 DeepAgents graph + AGENTS.md 记忆 +必要工具还在，Aelin 就不会迷路。

希望若干个月后再翻这篇文档，你会觉得：  
**“还好当时我们做了这次大收敛。”**
