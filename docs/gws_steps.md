# gws 集成实施步骤（待办清单）

> 目标：在 Aelin 中以“原子工具 + Skill 指南”的方式集成 Google Workspace CLI（gws），支持 Gmail / Drive / Calendar 的读取能力，并在明确、可控的前提下逐步开放少量写操作（如创建日历事件、发送邮件）。

## 1. 整理和确认现有 gws 封装

- [x] 检查 `GoogleWorkspaceCliService` 封装范围是否合理
  - [x] 确认仅暴露经过约束的能力（auth_status / gmail_list / gmail_get / drive_list / calendar_list 等），无任意命令执行入口
  - [x] 确认所有 CLI 调用都通过 `_run_json()` 统一处理超时与错误
  - [x] 确认所有返回值都使用 `{"ok": bool, "error": str | None, "data": ...}` 结构（由 `_run_json()` 提供，外层方法在此基础上增加 `items`/`raw` 等高阶字段）
- [x] 校验配置来源是否统一
  - [x] 确认 `bin_path`、`timeout_seconds`、`config_dir` 均来自 `settings.google_workspace_*` 配置
  - [x] 确认 `_env()` 中正确注入 `GWS_CONFIG_DIR`，不会污染全局环境变量

## 2. 设计 `google_workspace` 工具接口

- [x] 确定工具命名与命名空间
  - [x] 工具名为 `google_workspace`，并在 `AelinToolHub.tool_definitions()` 与 `execute()` 中保持一致
  - [x] 工具说明中明确标注“Google Workspace 相关”，并区分读 action 与预留写 action
- [x] 定义统一 action 集（读能力）
  - [x] `action="runtime"`：返回当前安装/配置状态（`scope="runtime"`）
  - [x] `action="auth_status"`：返回当前登录状态与邮箱、scope 等（`scope="auth"`）
  - [x] `action="gmail_list"`：列出邮件列表（`scope="gmail"`）
  - [x] `action="gmail_get"`：获取单封邮件详情（`scope="gmail"`）
  - [x] `action="drive_list"`：列出 Drive 文件（`scope="drive"`）
  - [x] `action="calendar_list"`：列出日历事件（`scope="calendar"`）
  - [x] 规划写能力 action（可按阶段实施）
  - [x] 实现 `action="calendar_create_event"`：通过 gws 创建日历事件，并在失败时透传错误
  - [x] 实现 `action="gmail_send"`：通过 gws 发送邮件，并在失败时透传错误
  - [x] 实现 `action="gmail_draft"`：通过 gws 创建邮件草稿，并在失败时透传错误
  - [x] 实现 `action="docs_create"`：通过 gws 创建 Docs 文档，并在有正文内容时追加写入文本
  - [x] 所有未知 `action` 返回 `{"ok": false, "error": "unsupported_action"}`
- [x] 规范每个 action 的参数
  - [x] 读 action：
    - [x] `gmail_list`：`query`, `max_results`, `include_spam_trash`
    - [x] `gmail_get`：`message_id`, 可选 `format`
    - [x] `drive_list`：`query`, `max_results`
    - [x] `calendar_list`：`calendar_id`, `time_min`, `time_max`, `max_results`, `single_events`
  - [x] 写 action（示例）：
    - [x] 在工具 schema 中预留 `event_*`、`email_*` 参数，但实现阶段暂不调用 gws 写接口
  - [x] 对所有数值参数使用 `_safe_int` 风格的防御式转换，限制上下限

## 3. 在 `AelinToolHub` 中实现 `google_workspace` 工具

- [x] 工具实现基础结构
  - [x] 在 `AelinToolHub` 内新增 `_tool_google_workspace` 方法
  - [x] 在工具注册表中添加 `google_workspace` 条目，包含参数 schema 与说明
  - [x] 工具内部通过 `get_google_workspace_cli_service()` 获取 service 实例
- [x] 统一结果格式
  - [x] 读能力成功调用时返回 `{"ok": true, "scope": "...", "items"/"item": ..., "raw": {...}}`
  - [x] 失败调用返回 `{"ok": false, "error": "...", "scope": "...", ...}`，直接透传 service 层错误字段
  - [x] `runtime` / `auth_status` 在结果中带有 `next_action` 字段（`"install" | "login" | "ready"`）
- [x] 安装与登录提示
  - [x] 当 CLI 未安装时，`runtime` 结果中包含可读的 `install_hint`，指向 gws 安装或打包说明
  - [x] 当 CLI 已安装但未登录时，`auth_status` 结果中包含 `login_command`（如 `["gws", "auth", "login"]`）
  - [x] Agent 可以通过 `next_action` + `install_hint` + `login_command` 判断下一步需要用户在终端执行什么

## 4. 为 gws 编写 Skill 指南

- [x] 创建/调整 `backend/skills/google/SKILL.md`
  - [x] 写明 gws 能力范围：Gmail / Drive / Calendar 等 Google Workspace 能力（当前实现以读取为主）
  - [x] 写明何时应优先使用 gws（访问私有工作区数据时）而不是 `web_search`
  - [x] 写明需要用户在本机完成 `gws auth login` 的场景与操作步骤（通过 `runtime`/`auth_status` 的 `install_hint`/`login_command` 字段）
- [x] 为各 action 提供调用示例（文档化）
  - [x] 读能力示例：
    - [x] `action=gmail_list`：根据关键词查找最近 N 封邮件，并总结核心要点
    - [x] `action=drive_list`：根据名称或 owner 查找文件，并按时间排序
    - [x] `action=calendar_list`：查询一段时间内的会议事件，并给出时间段冲突提示
  - [x] 写能力示例（需要明确“先解释再执行”）：
    - [x] 在 Skill 中提示可以使用 `calendar_create_event` / `gmail_draft` / `gmail_send` / `docs_create`，并强调必须先向用户解释再执行
  - [x] 在 Skill 中强调：工具结果中的 `raw` 只在必要时用，默认使用精简后的 `items`/`item`
- [x] 接入 Skill 目录
  - [x] 通过 `applies_to_tools: google_workspace` 让 Skill 与工具自动建立关联
  - [x] 使用 slug/name `google`；现有 skill loader 可加载该 Skill，并在「Google」相关能力下索引

## 5. 与现有工具和能力的边界设计

- [x] 明确 gws 与其他工具的边界
  - [x] 当用户询问公共信息（新闻、公开网页）时，优先 `web_search`
  - [x] 当用户询问个人邮件/文件/日历时，优先 `google_workspace`
  - [x] 避免在同一回合中同时对同一问题既用 gws 又用 web_search，除非 Skill 指南明确建议
- [x] 与 memory / plane 的协作
  - [x] 允许 Agent 在使用 gws 后，将关键信息写入 diary/memory（由 planner 决定）
  - [x] 不将 gws 视为 plane，不纳入 plane 监督与 checkpoint 流程

## 6. 测试与验证

- [x] 单元测试
  - [x] 为 `GoogleWorkspaceCliService` 中的每个方法编写测试（使用 monkeypatch 替换 `subprocess.run`）
  - [x] 测试安装缺失、超时、JSON 解析失败等边界情况
  - [x] 测试 `google_workspace` 工具各 action 的正常返回与错误返回（包括 calendar_create_event / gmail_send / gmail_draft / docs_create）
- [ ] 集成测试（本地手动）
  - [ ] 在本机安装并配置 gws（含登录）
  - [ ] 通过 Aelin Chat 输入例如“帮我列一下最近 10 封 Gmail 邮件”，观察是否自动选择 gws 工具
  - [ ] 通过 Aelin Chat 输入例如“帮我创建一个 Google 文档讲讲 Agent Swarm”，观察是否调用 `docs_create` 并返回文档信息
  - [ ] 验证当未安装/未登录时，Aelin 会用中文提示用户在终端执行何种命令
  - [ ] 验证当用户完成登录后再次询问，Aelin 能顺利拉取并总结数据或创建文档

## 7. 文档与用户提示

- [x] 更新 README / docs 能力说明
  - [x] 在能力总览中加入 “Google Workspace 集成（Gmail / Drive / Calendar）” 一节
  - [x] 简要说明 gws 依赖的安装方式与授权方式
  - [x] 标明当前仅支持通过受控工具访问，不会在未明确确认的前提下修改或删除用户数据
- [ ] 桌面端集成说明
  - [ ] 在桌面打包相关文档中说明：
    - 是否随应用一起打包 gws 二进制
    - gws 配置目录（`GWS_CONFIG_DIR`）放置位置
  - [ ] 提供一段面向最终用户的“首次使用 gws 能力”的引导（如何登录、如何撤销授权）

## 8. 回归与后续扩展

- [ ] 完成回归检查
  - [ ] 跑一遍 backend 测试：`pytest -q`
  - [ ] 确认新的 `google_workspace` 工具不会影响现有工具行为
  - [ ] 确认能力文档与实际代码一致
- [ ] 规划后续扩展方向（可选）
  - [ ] 评估是否增加写操作能力（例如创建日历事件），并在设计上增加更严格的确认与权限控制
  - [ ] 评估是否需要为 gws 集成单独引入 plane（例如长时间监控日历变化），并与当前 pinchtab plane 机制对齐
