# DeepAgents 工具契约 & 限制调整 TODO（2026-03-21）

> 目标：先只调整 “工具契约（尤其是 web_search / plane）” 和 “工具调用上限”，让 DeepSeek 在 Aelin 中几乎不受限地试用工具，同时减少 `missing query` / `unsupported plane action` / `round_call_limit` 一类的错误。

## 1. Web 搜索工具契约（web_search）

- [x] 在 `backend/app/services/deepagents_graph.py` 的 `build_chat_tools` 中，为 `web_search` 补充详细的 description：
  - [x] 明确要求参数：`action` 只能是 `"search"` 或 `"search_and_fetch"`。
  - [x] 明确 `query` 必须是非空字符串（中文或英文均可），否则工具会返回 `missing query`。
  - [x] 说明 `max_results` 取值范围 `1-15`，`fetch_top_k` 取值范围 `0-6` 且不得大于 `max_results`。
  - [x] 给出 1-2 个 JSON 示例调用（搜索新闻、搜索技术文档），帮助模型形成 schema 印象。

- [x] 保持 `backend/app/services/tools_web.py::tool_web_search` 行为不变，仅在错误信息上稍作收敛：
  - [x] 保证 `missing query` / `unsupported action` 这类 error 文本简洁、直白，便于 DeepAgents 读懂并纠错。

- [x] 在 DeepAgents system prompt 中追加 “Web 搜索工具使用规范” 小节：
  - [x] 指出调用 `web_search` 前必须先构造好 `query`，不得留空。
  - [x] 如果收到 `missing query` 错误，下一次调用必须补充 `query` 后再试。

- [x] 验证（DeepSeek 账号）：
  - [x] 使用 `debug_run_aelin_for_user.py` 或真实 HTTP 请求，发送 “最近 3 天国际要闻” 这类 prompt。
  - [x] 检查 `tool_trace` 中不再出现 `agent_loop_tool failed - missing query`。
  - [ ] 确认最多只看到少量合理的工具调用，而不会立刻触发 round 限制。

## 2. Plane 工具契约（plane）

- [x] 在 `build_chat_tools` 中为 `plane` 工具补充清晰的 description：
  - [x] 列出允许的 `action`：`"delegate"`, `"status"`, `"continue"`, `"close"`, `"catalog"`。
  - [x] 说明首次使用浏览器 plane 时必须使用 `{"action":"delegate","plane":"browser","goal":"..."}`。
  - [x] 说明只有已有 `task_id` 时才允许使用 `status` / `continue` / `close`，并给出 JSON 示例。
  - [x] 明确写出：任何未列出的 `action` 都会返回 `unsupported plane action`。

- [x] 保持 `backend/app/services/tools_browser_plane.py::tool_plane` 的控制流不变，仅确保错误文案对模型友好：
  - [x] `unsupported plane action` 提示中包含允许的 action 列表。
  - [x] `missing task_id` 明确指出需要传入上一次 plane 调用返回的 `task_id`。

- [x] 在 DeepAgents system prompt 中增加 “Plane 使用规范” 小节：
  - [x] 说明：当用户让你“在浏览器中打开/浏览 xxx”时，应优先调用 `plane`，且第一次用 `delegate`。
  - [x] 说明：如果 plane 返回 `waiting_user` 等状态，并提供了 `task_id`，续上任务时应使用 `status` / `continue` 并带上该 `task_id`。
  - [x] 禁止模型发明新的 plane action 名称。

- [x] 验证（DeepSeek 账号）：
  - [x] 使用 “请在浏览器中打开 https://www.baidu.com …” 这类 prompt 进行测试。
  - [x] 确认 `tool_trace` 中不再出现 `agent_loop_tool failed - unsupported plane action`。
  - [x] 确认 plane 调用数量相比之前略有增加但仍在策略允许范围内（目前仅有少量 `agent_loop_tool` 记录且未触发 plane 专属错误）。

## 3. 极大放宽工具调用策略上限

- [x] 在 `backend/app/settings.py` 中放宽 DeepAgents 用到的工具策略配置：
  - [x] 将 `aelin_agent_loop_max_calls_per_round` 默认值从 `2` 提升到 `32`。
  - [x] 将 `aelin_agent_loop_max_tool_calls` 默认值从 `4` 提升到 `128`。
  - [x] 将 `aelin_agent_loop_max_write_calls` 默认值从 `1` 提升到 `32`。

- [x] 确认 `_try_agent_loop_chat` 中构造 `AelinToolPolicy` 时仍然只依赖这些配置字段，没有其它隐藏上限：
  - [x] 检查 `AelinToolPolicy.evaluate` 是否还有硬编码的总次数/轮次数限制，如有则同步放宽或改为依赖上述配置（当前仅依赖上述配置）。

- [x] 回归测试：
  - [x] 运行核心后端测试：`pytest backend/tests/test_aelin.py backend/tests/test_agent_memory_deepagents.py backend/tests/test_remote_control.py -q`。
  - [x] 检查 `AgentLoop` 相关断言仍全部通过（尤其是关于 tool_trace 的那些）。

- [x] 端到端验证（DeepSeek 用户）：
  - [x] 使用 `debug_run_aelin_for_user.py` 或真实 UI，对 “web 搜索新闻 / 浏览百度首页 / 架构文档大纲” 三类复杂 prompt 重新测试。
  - [x] 记录每个场景下 `tool_trace` 中的工具调用数量和阶段，确认二级错误（例如 `round_call_limit`）已基本消失，目前仅在极端多轮调用下出现一次 `total_call_limit` 保护。

## 4. 清理与提交

- [x] 如果在调试过程中新增了临时脚本或日志（例如 debug 脚本），统一整理：
  - [x] 将仍有用的脚本保留在 `backend/debug_*.py` 并加上简短注释。
  - [x] 删除不再需要的临时文件。

- [x] 更新相关文档：
  - [x] 在现有 DeepAgents 相关文档中补充一小节，说明新的工具契约和放宽后的策略上限。

- [ ] 最终提交：
  - [ ] 格式化并自查代码（包括描述文案是否清晰、注释是否简洁）。
  - [ ] 使用单独的 commit 提交本次工具契约与策略调整，commit message 建议类似：`feat(deepagents): relax tool limits and clarify web/plane contracts`。
