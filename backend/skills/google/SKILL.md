---
name: Google Workspace via gws
slug: google
version: 1.1.0
applies_to_tools: google_workspace
trigger_keywords: google,gmail,drive,calendar,docs,sheets,google workspace,谷歌邮箱,谷歌云盘,日历,邮件,网盘
---

# Purpose

Google Workspace 能力在 Aelin 中应通过本地 `gws` CLI 使用，而不是通过浏览器自动化硬点页面。

这组能力适合：

- 读取 Gmail 邮件列表和单封邮件
- 检索 Google Drive 文件
- 查询 Google Calendar 日程
- 以后扩展到 Docs / Sheets / Chat

`gws` 的价值在于它直接走 Google Workspace API，输出稳定的结构化 JSON，比网页自动化更适合 agent。

---

# Positioning

请把 Google 工具理解为：

- **生产力系统工具层**
- **不是 PinchTab 那种浏览器托管子系统**

也就是说：

- PinchTab 用于“像人一样操作网页”
- Google 工具用于“对 Google Workspace 做结构化 API 操作”

如果用户问的是 Gmail / Drive / Calendar / Docs / Sheets，优先考虑这组工具，而不是先打开浏览器。

---

# Tool Boundaries

当前通过一个统一工具 `google_workspace` 来访问这些能力：

1. `action=runtime` / `status`
   - 检查本地 `gws` 是否已安装、以及配置目录是否就绪。
   - 返回字段中包含：`available`、`install_hint`、`login_command`（如果适用）、`next_action`。
   - 当用户第一次要求读取 Gmail / Drive / Calendar 时，通常先调用它。

2. `action=auth_status`
   - 检查当前是否已经完成 Google OAuth 登录。
   - 未登录时会携带 `login_command`，例如 `["gws", "auth", "login"]`。

3. `action=gmail_list`
   - 获取 Gmail 消息列表。
   - 适合“列出未读邮件”“找最近关于某主题的邮件”。

4. `action=gmail_get`
   - 获取单封邮件详情。
   - 适合“打开刚才那封邮件并总结”。

5. `action=drive_list`
   - 检索 Drive 文件。
   - 适合“找某份 PRD / 文档 / 表格”。

6. `action=calendar_list`
   - 查询日历事件。
   - 适合“看我今天/这周的日程”。

---

# Usage Order

推荐顺序：

1. 先调用 `google_workspace`，`action=runtime`：
   - 若返回未安装，先明确告诉用户需要完成本地安装（使用 `install_hint` 字段）。
2. 再调用 `google_workspace`，`action=auth_status`：
   - 若返回未登录，提示用户在终端执行 `login_command` 完成 `gws auth login`。
3. 确认 `next_action=ready` 后，再调用对应的读取 action（`gmail_list` / `drive_list` / `calendar_list` 等）。
4. 先读后总结：
   - 尽量不要直接凭空总结 Gmail / Drive / Calendar，而应基于工具返回内容组织答案。

---

# Query Mapping

以下需求优先用 `google_workspace`：

- “帮我看一下我的 Gmail 未读邮件”
- “帮我找 Drive 里最近的产品文档”
- “帮我看看今天的日历安排”
- “总结一下这封 Google 邮件”

以下需求不要优先用 Google 工具：

- “去某个网页点按钮并提交表单”
- “在网页登录某个非 Google 网站”
- “需要验证码、浏览器交互、持续网页会话”的任务

这些仍应使用 PinchTab 或其他浏览器 / computer-use plane；如果只是查公开网页信息，优先使用 `web_search`。

在同一个问题上，尽量避免同时对同一事实既用 `google_workspace` 又用 `web_search`：

- 若问题本质是“我的邮箱 / 文件 / 日历里有什么”，优先只用 `google_workspace`
- 若问题本质是“互联网上公开的信息是什么”，优先只用 `web_search`
- 只有在需要“用公开信息补充说明私人数据”的时候，才在同一回合组合使用两者

---

# Safety Rules

- 当前阶段优先只读，不主动做写操作
- 不要假设用户已经完成 Google OAuth
- 如果 `google_status` 显示不可用或未认证，应明确告知阻塞点
- 不要为了读 Gmail/Drive/Calendar 而退回浏览器自动化，除非用户明确要求

`google_workspace` 属于 **第二层原子工具**，不是 plane：

- 它不负责长生命周期任务或复杂流程委派
- 它只负责把 Gmail / Drive / Calendar 的结构化结果拿回来
- 如果需要长流程“帮我持续整理这周日程”“长期跟踪某类邮件”，由 planner 决定是否把总结结果写入 diary / memory，而不是把 gws 本身当成 plane

---

# Output Style

- 对 Gmail 列表，优先提炼：主题、发件人、时间、是否未读
- 对单封邮件，优先提炼：主题、发件人、正文摘要、后续行动项
- 对 Drive 检索，优先提炼：文件名、类型、最近修改时间、链接
- 对 Calendar，优先提炼：开始时间、结束时间、标题、地点/会议链接

当结果很多时，先按时间或相关性列前 5~10 条，再继续追问。
