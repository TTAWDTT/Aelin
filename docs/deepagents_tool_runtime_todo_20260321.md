# DeepAgents 工具与链路修复 TODO（基于 2026-03-21 实测结果）

> 说明：本清单只聚焦于 DeepAgents 运行期工具契约和链路行为问题，来源是 2026-03-21 的真实链路测试  
> （纯聊天 / Web 搜索 / GWS / device / DeepAgents 文件工具）。

---

## 1. Agent Loop 工具调用上限与时限放宽

- [x] **1.1 明确当前限制来源并统一配置入口**
  - 操作：
    - 检查 `deepagents_loop.py` / `deepagents_graph.py` 中对 `max_tool_calls`、`max_rounds`、`time_limit_s` 之类的配置。
    - 对齐环境变量（例如 `.env` 中的 `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS` / `MERCURYDESK_AELIN_AGENT_LOOP_MAX_TOOL_CALLS`）与 DeepAgents 的配置，使二者不会互相打架。
  - 验收：
    - 在代码中能一眼看出「一处」控制工具调用/轮次/时限的配置路径，而不是分散在多处。

- [x] **1.2 放宽工具调用上限，消除频繁的 `total_call_limit`**
  - 操作：
    - 将 DeepAgents 图的工具调用上限（尤其是 `agent_loop_tool` 的 total_call_limit）显著调大，至少满足：
      - Web 搜索类请求可以容忍 8–12 次工具调用。
      - GWS / device 组合链路在正常情况下不会被过早打断。
    - 同步调整 `AelinToolPolicy` 中相关限制，避免在 DeepAgents 之前就被拦截。
  - 验收：
    - 对「请你帮我总结最近3天的国际要闻」这类请求，`tool_trace` 中不会再出现 `agent_loop_tool: denied: "total_call_limit"`，同时能拿到正常回答。

- [ ] **1.3 为极端情况保留软保护与友好提示**
  - 操作：
    - 保留一个较高的终极上限（防止工具调用失控），但在触达时返回友好错误而不是“什么也不说”：
      - 在 DeepAgents 输出中带上 `agent_loop_no_result` 或类似标记。
      - 在 Aelin 的最终答复中转译成「本轮工具调用次数过多，已被安全策略中止」之类的提示。
  - 验收：
    - 人为构造一个会触达极限的请求时，前端用户能收到清晰提示，而不是“空回答 + 只在日志里看到 total_call_limit”。

---

## 2. `device` 工具契约修复（StructuredTool 化）

> 实测错误：  
> `ToolException: Too many arguments to single-input tool device. Args: ['open_url', 'https://www.baidu.com']`

- [x] **2.1 设计 `device` StructuredTool 输入模型**
  - 操作：
    - 在 `tools_device.py` 或相邻模块中定义一个 Pydantic 模型，例如：
      - `DeviceToolInput { action: Literal['open_url', ...], url: Optional[str], text: Optional[str], ... }`
    - 明确列出当前计划支持的 action 集合，至少包含：
      - `open_url`（浏览器打开链接，原先 plane 的 P0 替代能力）。
  - 验收：
    - `DeviceToolInput` 的字段和语义在代码和 docstring 中清晰可见，便于 LLM 根据描述构造参数。

- [x] **2.2 调整 DeepAgents 工具注册为 StructuredTool**
  - 操作：
    - 在 `deepagents_graph.build_chat_tools` 中，将 `device` 从简单单参数工具改为 StructuredTool：
      - 函数签名形如 `def device_tool(input: DeviceToolInput) -> dict[str, Any]: ...`
      - 内部调用已有的 `DeviceCenter` / `tools_device` 逻辑。
    - 确保返回结构适合作为 DeepAgents 工具结果（含 summary/错误信息等）。
  - 验收：
    - 对「请在浏览器中打开 https://www.baidu.com」再跑真实链路，不再出现 `Too many arguments to single-input tool device`，而是看到：
      - `tool_trace` 中有一条 `agent_loop_tool: completed: "device(...)"`。
      - 桌面侧浏览器确实被打开（在 desktop 插件已正常运行的前提下）。

- [x] **2.3 增加最小集成测试覆盖**
  - 操作：
    - 在 `backend/tests/test_aelin_tools.py` 或新增 test 文件中，模拟一个简单的 device 调用（使用 mock/假 DeviceCenter）：
      - 构造 DeviceToolInput(`action='open_url', url='https://example.com'`)。
      - 断言底层调用收到的参数正确，且返回结构符合预期。
  - 验收：
    - 本测试在 CI 中长期通过，防止未来 StructuredTool 定义被无意破坏。

---

## 3. Google Workspace (`google_workspace`) 工具可用性修复

> 实测现象：  
> 「请帮我列出最近5封未读邮件的大致情况」的回答里没有任何 `google_workspace(...)` 记录，  
> `tool_trace` 中反而多次出现 `"agent_loop_tool": "failed", "detail": "unsupported_action"`。

- [x] **3.1 梳理现有 GWS 工具 action 集**
  - 操作：
    - 检查 `tools_gws.py` 和 `google_workspace_cli.py` 中当前支持的 action（例如 `drive_list` / `docs_create` 等）。
    - 标记哪些 action 实际对“列出最近未读邮件摘要”有帮助，哪些是高风险写操作。
  - 验收：
    - 文档或注释中有一份简短列表：当前支持的安全 GWS 读操作，以及暂不开放的写操作。

- [x] **3.2 为典型 read-only 场景提供稳定 action**
  - 操作：
    - 设计一到两个稳定的、抽象程度较高的只读动作，例如：
      - `gmail_list_unread_summary`：返回最近 N 封未读邮件的发件人/主题/时间摘要。
    - 在 `tools_gws.py` 中实现对应分支，并在工具描述中明确用法（供 DeepAgents prompt 使用）。
  - 验收：
    - 在后续真实链路测试中，对「请帮我列出最近5封未读邮件的大致情况」：
      - `tool_trace` 中出现一次或少数几次 `google_workspace(gmail_list_unread_summary)` 调用。
      - 回答内容能合理提炼最近未读邮件的关键信息（在本地账号已正确授权的前提下）。

- [x] **3.3 放宽工具策略中对 GWS 的限制**
  - 操作：
    - 在 `AelinToolPolicy` 和 DeepAgents 工具注册处，确保：
      - 对上述只读 action 不再按“写工具”对待，不被过早拒绝。
      - 仍对可能产生副作用的写操作保持严格限制或完全禁用。
  - 验收：
    - 再次构造邮件类请求时，不会再出现 `"unsupported_action"`，而是要么正确调用，只读失败时也有明确错误信息。

---

## 4. DeepAgents 文件工具与 AGENTS.md 自省体验

> 实测现象：  
> 对「Use ls and read_file to inspect /memory/AGENTS.md and summarize it.」请求，  
> `tool_trace` 里只有 `agent_loop(deepagents_core_v0)`，没有任何 `ls` / `read_file` 工具调用。

- [x] **4.1 在 system prompt 中显式提示文件工具使用方式**
  - 操作：
    - 在 DeepAgents chat agent 的 system prompt 中补充一节说明：
      - 当用户显式要求使用 `ls/read_file`/等文件工具时，应优先调用这些工具，而不是凭空臆测。
      - 示意几条典型用法（例如检查 `/memory/AGENTS.md`）。
  - 验收：
    - 再次发出「Use ls and read_file to inspect /memory/AGENTS.md and summarize it.」：
      - `tool_trace` 中能看到至少一次 `ls` 和一次 `read_file` 调用。

- [x] **4.2 为 AGENTS.md 自省增加轻量测试**
  - 操作：
    - 在后端测试中增加一个不依赖真实网络/桌面的用例，模拟：
      - DeepAgents 使用 `ls` / `read_file` 访问挂载的 `/memory/AGENTS.md` 虚拟文件。
    - 断言：得到的文本片段与实际 AGENTS.md 内容一致。
  - 验收：
    - 该测试通过，保证未来修改 MemoryMiddleware 或文件挂载时不会悄悄破坏这条路径。

---

## 5. 回归测试与文档更新

- [ ] **5.1 完整回归本次四类真实链路**
  - 操作：
    - 在完成 1–4 之后，重新跑以下真实请求（使用已有 DeepSeek 配置）：  
      - 纯聊天：`你好，请你介绍一下你自己`  
      - Web 搜索：`请你帮我总结最近3天的国际要闻`  
      - GWS：`请帮我列出最近5封未读邮件的大致情况`  
      - Device：`请在浏览器中打开 https://www.baidu.com`（桌面插件正常运行时）  
      - 文件工具：`Use ls and read_file to inspect /memory/AGENTS.md and summarize it.`  
    - 对每个请求记录：
      - 最终自然语言答复是否符合预期；
      - `tool_trace` 是否显示了预期工具调用；
      - 是否仍存在 `total_call_limit`、`unsupported_action`、`agent_loop_no_result` 之类错误。
  - 验收：
    - 上述五条场景全部表现正常，若有残余错误，需在本文件中追加新的 TODO 条目。

- [ ] **5.2 更新相关 DeepAgents 文档**
  - 操作：
    - 在 `docs/deepagents_cleanup_next_todo_20260321.md` 和 `docs/deepagents_arch.md` 中补充一小节：
      - 描述新的 device StructuredTool 契约；
      - 描述 GWS 只读能力的当前范围；
      - 描述 agent loop 工具调用上限的新策略。
  - 验收：
    - 文档与代码实现保持一致，新读者可以直接通过文档理解当前工具层的真实能力与限制。
