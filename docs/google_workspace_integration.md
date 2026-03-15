# Google Workspace Integration

## Positioning

`googleworkspace/cli` 在 Aelin 中的定位是：

- 本地 Google Workspace 能力后端
- 通过稳定的 Aelin 原子工具暴露
- 由 skill 指导调用顺序与边界

它不是 `pinchtab` 那种“接受整件任务并自己长期推进”的子系统。

## Architecture

当前接入架构仍然是四层，但经过几轮迭代后，具体实现形态已经更新为：

1. `gws` CLI（二进制）
   - 本地安装或捆绑在桌面应用中；
   - 通过 `MERCURYDESK_GOOGLE_WORKSPACE_CLI_BIN` 指定可执行路径；
   - 通过 `MERCURYDESK_GOOGLE_WORKSPACE_CLI_CONFIG_DIR` 指定配置目录（`GWS_CONFIG_DIR`）。

2. `GoogleWorkspaceCliService`
   - 文件：`backend/app/services/google_workspace_cli.py`
   - 职责：
     - 解析 `bin_path` / `timeout_seconds` / `config_dir`；
     - 统一处理命令构造、超时、JSON 解析、错误归一化；
     - 封装为稳定的 Python 方法（`runtime_status` / `auth_status` / `gmail_list_messages` / `gmail_get_message` / `drive_list_files` / `calendar_list_events`）。

3. `google_workspace` 工具（Level 2）
   - 文件：`backend/app/services/aelin_tools.py`
   - 通过 `AelinToolHub` 暴露单一工具 `google_workspace`，action 集合为：
     - 读：`runtime` / `auth_status` / `gmail_list` / `gmail_get` / `drive_list` / `calendar_list`
     - 写：`calendar_create_event` / `gmail_send` / `gmail_draft` —— 当前仅预留，占位逻辑返回 `write_actions_not_implemented`
   - 统一返回格式：
     - `ok`: 是否成功
     - `scope`: `"runtime" | "auth" | "gmail" | "drive" | "calendar" | "google_workspace"`
     - `items` / `item`: 结构化结果列表或单条记录
     - `raw`: 原始 JSON 结果
     - `error`: 错误描述（失败时）
     - `next_action`: `"install" | "login" | "ready"`（runtime / auth 场景）
     - `install_hint` / `login_command`: 指导用户在终端完成安装或登录的具体提示。

4. `backend/skills/google/SKILL.md`
   - 通过 `applies_to_tools: google_workspace` 与工具自动关联；
   - 负责说明：
     - 什么时候优先用 gws 而不是 `web_search` 或 PinchTab；
     - 如何按顺序调用 `runtime` → `auth_status` → 各种读 action；
     - 当 `next_action` 为 `install` / `login` 时，如何用自然语言转述 `install_hint` / `login_command`；
     - 当前写操作尚未开放，看到 `write_actions_not_implemented` 时不要强行重试，而是退回纯说明。

## Next Steps

后续扩展建议保持“小步快跑”的节奏：

1. 桌面分发层打包 `gws`
   - 在 desktop 侧增加对 `google_workspace_cli_bin` / `google_workspace_cli_config_dir` 的默认配置；
   - 明确 Windows / macOS 下的 `GWS_CONFIG_DIR` 放置位置，保证多版本共存时不会互相污染。

2. 增加“连接 Google Workspace”引导
   - 在能力总览 / onboarding 中提示用户：
     - 需要本机安装 `gws`；
     - 首次需要在终端执行 `gws auth login`；
     - 可随时通过 `gws auth revoke` 撤销授权。

3. 逐步增加写操作能力（严格确认）
   - 从风险较低、易解释的能力开始，例如：`calendar_create_event`；
   - 所有写能力必须：
     - 在工具 schema 中标记为高风险写操作；
     - 在调用前，先用自然语言明确说明操作细节并征求用户确认；
     - 在 ToolPolicy / agent loop 层面增加“确认门槛”，防止模型连环调用。

4. 稳定后再考虑 plane 级场景
   - 例如“长期监控日程变化并提醒”的需求，可能需要引入基于 gws 的 plane；
   - 当前阶段保持 gws 作为 Level 2 工具即可，plane 依然由 PinchTab 等系统主导。

## Current Readiness Contract

`google_status` 现在不只是检查“能不能用”，还会返回：

- `available`
- `authenticated`
- `configured_bin_path`
- `resolved_bin_path`
- `config_dir`
- `login_command`
- `install_hint`
- `next_action`

其中 `next_action` 约定为：

- `install`
  - 本机还没有 `gws`
- `login`
  - 有 `gws`，但还没完成认证
- `ready`
  - 已安装且已认证，可以继续调用 Gmail / Drive / Calendar

这让 Aelin 能清楚区分：

- “工具没装”
- “工具装了但没登录”
- “工具已经可用”
