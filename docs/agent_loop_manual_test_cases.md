# Agent Loop 手工测试用例（截图 / 读屏 / 浏览器）

## 使用说明
- 测试环境：`backend` + `frontend/desktop` 最新代码。
- 记录格式：每条用例记录 `结果(通过/失败)`、`日志片段`、`复现步骤`。

## 用例清单
### TC-01 纯聊天链路（不触发工具）
- 步骤：输入普通问答（如“帮我总结今天计划”）。
- 预期：直接文本回复；日志出现 `agent_loop llm_request/llm_response`，无 `tool_call_start`。

### TC-02 手动截图输入链路
- 步骤：在聊天中上传截图并提问“这是什么页面？”。
- 预期：模型可基于图片回答；不强制触发 `screen_get`。

### TC-03 自主读屏链路（screen_get）
- 步骤：输入“看下我屏幕上在做什么”。
- 预期：触发 `screen_get`，随后给出基于当前屏幕的分析。

### TC-04 screen_get 失败回退
- 步骤：关闭/断开桌面插件后再次触发读屏。
- 预期：工具失败但流程不中断，返回可理解错误与下一步建议。

### TC-05 浏览器状态读取（browser_state_get）
- 步骤：打开浏览器页面后输入“读取当前浏览器状态”。
- 预期：返回页面 URL/标题等状态信息。

### TC-06 浏览器操作（browser_use）
- 步骤：输入“打开某网站并搜索关键词”。
- 预期：触发 `browser_use`；日志包含 tool start/end 与耗时。

### TC-07 高风险操作确认
- 步骤：请求“自动提交表单/点击购买”类动作。
- 预期：进入确认门控（未确认不执行写操作）。

### TC-08 多轮工具协作
- 步骤：输入“先读屏，再打开浏览器搜索，再总结”。
- 预期：多轮调用稳定结束，`agent_loop end` 给出 stop reason 与总调用数。

### TC-09 LLM 多模态降级重试
- 步骤：在不支持多模态模型下触发图像输入。
- 预期：出现 `llm_retry_without_images`，流程可继续。

### TC-10 超时与无进展退出
- 步骤：构造复杂请求触发长链路。
- 预期：在超时或无进展时安全退出，返回阶段性结果。

### TC-11 浏览器状态监控（system/all）
- 步骤：输入“列出浏览器会话和系统浏览器进程”或调用 `browser_session_list(scope=all)`。
- 预期：返回 `managed_sessions` 与 `system_processes` 两个视图；可用 `pid` 定位单进程。

### TC-12 CDP 接入当前 Chrome（可选）
- 前置：Chrome 用调试端口启动（见下方“CDP 前置”）。
- 步骤：输入“读取当前浏览器状态（scope=cdp）”。
- 预期：返回 `session_scope=cdp`，可读取用户当前 Chrome 会话状态（非 agent 独立会话）。

## 建议重点观察日志关键字
- `agent_loop llm_request`
- `agent_loop llm_response`
- `agent_loop tool_call_start`
- `agent_loop tool_call_end`
- `agent_loop end`

## CDP 前置（可选）
- 目的：让 Aelin 接入用户当前 Chrome，而非独立 agent 浏览器会话。
- Windows 启动示例：
  ```powershell
  chrome.exe --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222
  ```
- 说明：未开启调试端口时，`scope=auto` 会自动回落到 `managed` 会话。
