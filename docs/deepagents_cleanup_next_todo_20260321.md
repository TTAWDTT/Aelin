# DeepAgents 纯壳化后续清理 TODO（Plane/PinchTab 退场 & ToolHub 极限瘦身）

> 目标：在已经完成 DeepAgents 作为唯一 Agent Loop 的基础上，  
> 进一步把 Aelin 清理成「一个极薄的 DeepAgents 外壳 + 少量业务工具」，  
> 把 plane / PinchTab / 旧 Agent Loop 残留彻底删除，并让 ToolHub 变成真正轻量的工具注册层。

---

## 1. Plane / PinchTab 全家桶彻底退场

### 1.1 从工具契约与 Agent Core 中移除 plane

- [x] 在 `backend/app/services/aelin_tools.py` 中移除 plane 相关暴露：
  - [x] 从 `tool_definitions()` 中删除 `plane` 的 function 条目，以及 plane 专用的提示文案 / continuation hints 等常量（如 `_PLANE_CONTINUATION_HINTS`、`_STALE_PLANE_ERRORS` 等）。
  - [x] 从 `execute()` 中删除 `if tool == "plane": return tool_plane(...)` 分支。
  - [x] 删除仅被 plane 使用的辅助函数（如 `_build_plane_adapter_for_entry`、`_should_reuse_active_plane_task`、`should_resume_active_plane_for_query`、`_should_restart_plane_task_after_reuse_failure` 等），确认无其它调用点后直接移除。
- [x] 在 `backend/app/services/aelin_tool_policy.py` 中：
  - [x] 从工具白名单中去掉 `"plane"`。
  - [x] 删除 `classify_tool_call` 中对 plane 写操作的判断分支。
- [x] 在 `backend/app/services/aelin_core.py` 中：
  - [x] 从 `_try_agent_loop_chat` 中移除 `get_active_plane_task(...)` 及 `should_resume_active_plane_for_query(...)` 的逻辑，不再构造 `plane_snapshot`。
  - [x] 在调用 `run_deepagents_loop(...)` 时删除 `plane_snapshot` 参数，并同步更新 `run_deepagents_loop` 的函数签名与所有调用点。
  - [x] 在 trace 拼装逻辑中移除对 `run.name == "plane"` 的特殊 stage 拆分（`plane_delegate` / `plane_status` / ...），统一作为普通 `agent_loop_tool` 处理。

验收：
- [x] Aelin 后端中不再有任何 plane 相关的工具 definition / execute 分支 / resume heuristics；DeepAgents 也看不到名为 `plane` 的工具。
- [x] `_try_agent_loop_chat` 的主要职责收敛为「preflight → 调 DeepAgents → 映射 trace」，不再关心 plane 状态。

### 1.2 删除 plane / PinchTab 运行时代码

- [x] 删除或归档以下 plane 相关服务模块（确认无其它引用后删除文件本身）：
  - [x] `backend/app/services/aelin_planes.py`
  - [x] `backend/app/services/browser_plane_adapter.py`
  - [x] `backend/app/services/plane_runtime.py`
  - [x] `backend/app/services/tools_browser_plane.py` 中的 `tool_plane`（保留 `tool_pinchtab*` 仅在确认还需要 PinchTab 时）。
- [x] 评估是否还需要保留 PinchTab 全家桶，如不再需要则一并删除：
  - [x] `pinchtab_client.py` / `pinchtab_runtime.py` / `pinchtab_launcher.py`
  - [x] `AelinToolHub` 中 `_tool_pinchtab` / `_tool_pinchtab_agent` / `_tool_pinchtab_session` 及 `_ensure_pinchtab_runtime`、`_PINCHTAB_SESSIONS` 等辅助。
  - [x] settings 中 `pinchtab_*` 相关配置（`pinchtab_base_url` / `pinchtab_executable_path` 等）。
  - [x] FastAPI lifespan 中的 `shutdown_pinchtab_launcher()` 调用。
- [x] 针对 DB 层 plane 结构（`PlaneTask` 及其 Checkpoint/Artifact/Event）：
  - [x] 在 `app/models.py` 中标记这些表为「legacy plane 用途」，检查当前代码是否仍有读写。
  - [x] 在确认所有读写入口删除后，可以在单独 commit 中完全移除这些模型定义，并计划后续 SQLite schema 清理。

验收：
- [x] 全局搜索关键字 `plane` / `browser_plane` / `PinchTab` 时，仅剩文档与少量历史 JSON 记录，运行时代码中不存在 plane 运行时或适配层。
- [x] 应用启动 / 关闭不再拉起或尝试关闭 PinchTab 相关进程。

### 1.3 清理 plane / PinchTab 测试与文档

- [x] 后端测试：
  - [x] 删除 `backend/tests/test_aelin_core_plane_resume.py` 整个文件。
  - [x] 在 `backend/tests/test_aelin_tools.py` 中删除 plane / pinchtab 相关测试用例与 `_patch_pinchtab_runtime` 辅助。
  - [x] 在 `backend/tests/test_skill_loader.py` 中移除与 “browser plane / pinchtab skill” 相关的断言。
  - [x] 在 `backend/tests/test_aelin_tool_policy.py` 中删去 plane/pinchtab 的写操作判断用例。
  - [x] 在 `backend/tests/test_aelin_preflight_perf.py` 中移除对 `get_active_plane_task` 的 monkeypatch 和 plane resume 相关逻辑。
- [x] 文档：
  - [x] 将 `docs/browser_plane_architecture.md` / `chat_plane_ui_design.md` / `chat_plane_ui_steps.md` / `deepagents_plane_trace_todo.md` 等 plane 专属文档移动到 `docs/archive/` 或标记为「已废弃」。
  - [x] 在 `deepagents_arch.md` / `aelin_deepagents_journey_202602.md` 中补一句说明：plane / PinchTab 已在 DeepAgents 纯壳化阶段移除。

验收：
- [x] `pytest backend/tests/test_aelin.py backend/tests/test_aelin_tools.py backend/tests/test_aelin_preflight_perf.py backend/tests/test_remote_control.py -q` 通过。
- [x] 文档中对 plane 的描述仅保留在历史/归档章节，不再出现在当前架构说明中。

---

## 2. 将 AelinToolHub 收缩为「极薄的 DeepAgents 工具注册层」

### 2.1 明确 ToolHub 需要长期保留的工具集合

- [x] 在 `AelinToolHub.tool_definitions()` 中做一次“白名单盘点”，最终只保留：
  - [x] `context_get`（会话摘要/重点，只读视图，供 UI / 调试用，不暴露给 DeepAgents 作为工具）。
  - [x] `profile`（用户画像 note，只读/追加视图，供 UI 使用）。
  - [x] `device` / `screen_get`。
  - [x] `web_search`。
  - [x] `attachment_search`。
  - [x] `google_workspace`。
  - [x] `skill`（仅供人类/外层系统阅读 skill 用法，不再作为 agent 决策工具）。
- [x] 确认 DeepAgents 侧真正用到的只有上述子集中的：`device` / `screen_get` / `web_search` / `attachment_search` / `google_workspace`。

验收：
- [x] `tool_definitions()` 输出的函数列表中不再出现 plane/pinchtab/其它 legacy 工具。
- [x] DeepAgents `build_chat_tools` 中的 allowlist 与上述集合一致。

### 2.2 精简 ToolHub 内部实现与辅助函数

- [x] 删除或内联掉仅服务于旧 Agent Loop 的复杂 heuristics：
  - [x] plane 相关所有 continuation / checkpoint 判断函数（已在 1.1 中标记，统一移除）。
  - [x] PinchTab session 相关 owner/session 映射，如果 PinchTab 一并下线则同时删除 `_PINCHTAB_SESSIONS` 等全局状态。
- [x] 保留的职责仅包括：
  - [x] 保存当前请求上下文：`db` / `user_id` / `workspace` / `AgentMemoryService` / `AelinAttachmentService` / `LLMService`。
  - [x] 提供统一的 `tool_definitions()`（供 planner/debug/前端展示使用）。
  - [x] 提供 `execute(name, args)` 分发到按领域拆分的 `tool_*` 函数（`tools_web` / `tools_files` / `tools_gws` / `tools_device` / `tools_skill` 等）。
- [x] 检查是否仍有地方通过 `AelinToolHub.execute` 走“万能工具入口”：
  - [x] 对 DeepAgents 主路径：依旧保持在 `build_chat_tools` 中直接调用领域函数（`tool_web_search` 等），尽量避免在 DeepAgents 里再绕一次 `execute`。
  - [x] 对 planner / debug 路径：早期曾保留 `run_aelin_structured_tools` 作为独立调试入口；现在已在 DeepAgents 分支中完全移除，仅保留 DeepAgents 自身的规划能力。

验收：
- [x] `AelinToolHub` 文件体量和复杂度明显下降，类的职责一句话即可概括：“按请求构造一个带上下文的工具 registry”。  
- [x] 除 planner / debug 以外，运行时代码中不再有“工具 → ToolHub.execute → 再跳转领域函数”的多层委托，DeepAgents 直接调用领域工具。

---

## 3. 深化对 DeepAgents 自带工具/记忆的依赖，淘汰重复能力

### 3.1 标准化使用 DeepAgents Filesystem + Execute 工具

- [x] 确认当前 `create_deep_agent` 调用已经挂载了 DeepAgents 默认中间件（`FilesystemMiddleware` + `TodoListMiddleware` + `SubAgentMiddleware` 等）：
  - [x] 在 `deepagents_graph.build_chat_agent` 中注释说明：DeepAgents 内置工具包括 `write_todos` / `ls` / `read_file` / `write_file` / `edit_file` / `glob` / `grep` / `execute` / `task` 等。
  - [x] 明确 Aelin 不再为“文件读写 / 代码编辑 / shell 执行”另造一套工具层，而是完全依赖 DeepAgents 自带实现。
- [x] 检查 Aelin 代码中是否存在重复的“文件工具”等能力：
  - [x] 如有自定义的文件读写/grep 工具，评估是否可以直接删掉或迁移为 DeepAgents filesystem 的一层 UI 视图，不再暴露给 agent。
- [x] 在 DeepAgents system prompt / 文档中补一节，面向 Aelin，说清楚：
  - [x] 文件操作请优先使用 `ls/read_file/edit_file/grep/glob` 等 DeepAgents 内建工具。
  - [x] Shell 命令请通过 `execute` 调用，遵循 DeepAgents 的安全约束。

验收：
- [x] 代码层面没有第二套“文件工具”能力；文件/命令相关操作完全用 DeepAgents middleware 提供的工具。
- [x] Agent 行为上，文件编辑/grep/execute 的调用 trace 都来自 DeepAgents 自带工具，而不是 Aelin 自行实现的重复工具。

### 3.2 记忆与上下文完全围绕 DeepAgents MemoryMiddleware

- [x] 确认 `deepagents_graph.build_chat_agent` 配置了 `memory` 路径并使用 DeepAgents `MemoryMiddleware` + `StateBackend`：
  - [x] 所有长期记忆都挂在 `/memory/AGENTS.md` 之类的虚拟文件上，由 DeepAgents 注入 system prompt。
  - [x] 移除任何自定义的 `download_files` / `file_data_to_string` 兼容层（避免再次出现 `file_data["content"]` 这类结构不匹配错误）。
- [x] 顶层文档中更新记忆说明：
  - [x] Aelin 的记忆 = DeepAgents 的虚拟文件记忆（AGENTS.md），DB 里仅保留必要的 cache/索引视图。
  - [x] 旧式 DB 记忆表如果已不用，可在后续单独 todo 中安排删除。

验收：
- [x] 再次对“你好 + 请你介绍一下你自己”等典型对话进行真实链路测试，不再出现 `MemoryMiddleware.before_agent` 类的 deepagents_unhandled_error。
- [x] `AGENTS.md` 的变动确实能反映在 agent 的长期记忆表现上（例如改写项目说明/代码风格后，新对话能遵循）。

---

## 4. 回归测试、真实链路验证与提交

- [x] 后端测试：
  - [x] `pytest backend/tests/test_aelin.py backend/tests/test_aelin_tools.py backend/tests/test_aelin_preflight_perf.py backend/tests/test_remote_control.py -q`。
  - [x] 如有改动到 attachment/gws/device 等工具，实现对应子集测试。
- [ ] 真实链路测试（使用你配置好的 DeepSeek 账号）：
  - [ ] 纯聊天：`你好，请你介绍一下你自己`。
  - [ ] Web 搜索：`请你帮我总结最近 3 天的国际要闻`。
  - [ ] GWS：`请帮我列出最近 5 封未读邮件的大致情况`。
  - [ ] Device：`请在浏览器中打开 https://www.baidu.com`（在 desktop 插件正常运行时）。
  - [ ] DeepAgents 文件工具：`请用 ls 和 read_file 看看 /memory/AGENTS.md 的内容，然后帮我总结一下。`
- [ ] 提交：
  - [ ] 每完成一个大块（例如“plane/PinchTab 删除”“ToolHub 瘦身”“记忆/文件工具整合”）单独 commit，并在 TODO 中勾选对应项。
  - [ ] 建议 commit 信息类似：
    - `refactor(plane): remove browser plane and PinchTab runtime`
    - `refactor(tools): slim AelinToolHub into DeepAgents tool registry`
    - `feat(deepagents): standardize filesystem/memory usage in chat agent`

验收：
- [ ] 所有以上大项 checklist 勾完后，Aelin 的 Python 端结构可以用一句话概括为：  
  “一个 DeepAgents chat agent + 一组业务工具实现（通过极薄 ToolHub 暴露）+ HTTP/SSE 外壳”，  
  看代码时不会再感受到 plane/PinchTab/旧 agent loop 的历史负担。
