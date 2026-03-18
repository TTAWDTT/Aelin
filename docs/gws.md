# Google Workspace CLI（gws）集成说明

## 1. gws 是什么？能做什么？

[`gws`](https://github.com/googleworkspace/cli) 是 Google 官方提供的命令行工具，用于以统一、可脚本化的方式访问 Google Workspace 系列产品（Gmail / Drive / Calendar 等）的 API。它负责：

- 认证与授权：本地浏览器完成 OAuth 登录与授权，持久化凭据；
- API 协议细节：封装 HTTP 请求、分页、错误处理；
- 命令行入口：通过子命令形式暴露常见操作，例如：
  - `gws gmail users messages list`：列出用户邮件；
  - `gws drive files list`：列出 Drive 文件；
  - `gws calendar events list`：列出日历事件；
  - `gws auth status`：查看当前认证状态。

在 Aelin 中，我们不希望直接在 Agent 内部编写和维护 Google API 细节，而是把这部分职责委托给 gws：Aelin 只需要调用少量经过约束的 gws 命令，并消费其 JSON 输出结果即可。

## 2. 将 gws 集成进 Aelin 的意义

从产品能力和工程维护两方面看，把 gws 作为工具接入 Aelin 有几个直接收益：

- **安全且可控的 Google 能力入口**  
  - 封装成固定 action 的工具（如 `gmail_list`, `drive_list`, `calendar_list`），避免任意 shell 执行任意 gws 子命令；
  - 在清晰的 ToolPolicy 约束下开放少量写操作（如发邮件、创建日历事件、创建 Docs 文档），降低误操作风险；
  - 将 `bin_path` / `config_dir` 隔离在 settings 中，避免硬编码路径。

- **统一的跨产品访问方式**  
  - Aelin 可以用一套统一 contract 访问 Gmail、Drive、Calendar 等不同产品：
    - 统一的 `ok/error` 字段；
    - 统一的 `items` 列表；
    - 统一的 `raw` 原始 JSON 兜底。  
  - 对 Agent 来说，这些工具只是新的 Level 2 原子工具，与 `web_search` / `context_get` 同一层级，无需了解 gws 的底层差异。

- **配置与打包友好**  
  - 桌面端可以在打包时直接包含 gws 二进制，并设置默认 `GWS_CONFIG_DIR`；
  - 服务器端可以在部署脚本里统一安装 gws，然后通过环境变量完成接入；
  - 用户只需要按提示运行一次 `gws auth login` 完成授权，不需要手动管理 token。

## 3. Aelin 中的接入方案概览

现有代码中已经有一层针对 gws 的安全封装：

- 文件：`backend/app/services/google_workspace_cli.py`
- 核心类：`GoogleWorkspaceCliService`
  - 负责解析与解析：`bin_path`, `timeout`, `config_dir`；
  - 提供运行时状态：`runtime_status()`, `auth_status()`；
  - 提供只读查询：
    - `gmail_list_messages()` / `gmail_get_message()`
    - `drive_list_files()`
    - `calendar_list_events()`

在此基础上，本轮集成采用 **“原子工具 + Skill 指南”** 的模式，而不是 Plane，并且不刻意限制为“只读”：在清晰可控的前提下开放少量写操作（例如创建日历事件、发送邮件、创建 Docs 文档）。下面的方案分为“读能力”和“写能力”两部分描述。

1. **工具层（Level 2 Tool）：`google_workspace` / `gws` 工具**
   - 在 `AelinToolHub` 中新增一个工具入口，例如：
     - 工具名：`google_workspace`（或短名 `gws`）；
     - 参数：
       - `action`: 读操作例如  
         - `"runtime" | "auth_status" | "gmail_list" | "gmail_get" | "drive_list" | "calendar_list"`  
       - 已实现的写操作例如：  
         - `"calendar_create_event" | "gmail_send" | "gmail_draft" | "docs_create"` 等
       - 其他 action 专属参数：
         - `query`, `max_results`, `include_spam_trash`（gmail_list）
         - `message_id`（gmail_get）
         - `calendar_id`, `time_min`, `time_max`, `single_events`（calendar_list）
         - 写操作会有更严格、显式的参数（如时间、与会人、主题、文档标题/正文等），并在工具注册时标记为 `is_write=True`、风险级别较高。
   - 工具内部通过 `get_google_workspace_cli_service()` 调用对应方法，将结果统一整理为：
     ```json
     {
       "ok": true/false,
       "scope": "gmail|drive|calendar|runtime",
       "items": [...],         // 规范化后的条目列表
       "raw": {...},           // 原始 JSON，必要时可供深挖
       "next_action": "install|login|ready"
     }
     ```
   - 当本机尚未安装或尚未完成登录时，工具会：
     - 返回 `ok=false`；
     - 同时返回 `install_hint` 或 `login_command`（例如 `["gws", "auth", "login"]`）给 Agent，用自然语言提示用户下一步。

2. **技能层（Skill 指南）：`google_workspace` Skill**

   - 在 `backend/skills/google/SKILL.md` 中写明：
     - 适用场景：
       - 用户明确提到 Gmail/Drive/Calendar 相关需求；
       - 用户提到 “Google 日历”、“Google 文件”、“Gmail 收件箱” 等关键词；
       - 需要访问用户私有数据时，应优先选择 gws，而不是公共 `web_search`。
     - 工具使用模式（读）：
       - 首先调用 `google_workspace` 工具的 `"auth_status"` / `"runtime"` action 判断可用性；
       - 如果需要用户先执行 `gws auth login`，则用中文解释如何在终端执行该命令；
       - 登录完后再调用 `gmail_list` / `drive_list` / `calendar_list` 等 action 获取数据；
       - 对 `items` 列表进行归纳、筛选或进一步问询，而不是把原始 JSON 整段贴给用户。
     - 工具使用模式（写）：
       - 当需要创建日历事件、发送邮件、创建 Docs 文档等写操作时，必须先用自然语言向用户明确说明即将执行的操作和影响；
       - 只有在用户明确同意后，才调用带写语义的 action（如 `calendar_create_event` / `gmail_draft` / `gmail_send` / `docs_create`）；
       - 写操作必须在工具注册时标记为 `is_write=True`，并通过现有的 ToolPolicy / 确认机制加一道“是否真的要执行”的拦截；
       - 写操作完成后，尽量将结果转化为人类可读的摘要（例如 “已为你在 3 月 20 日 15:00 创建会议：XXX”；“已为你创建文档《Agent Swarm 简介》，并写入初稿内容”）。
   - 多模态决策：
       - 当用户只提到 “帮我找一篇公开文章” 时，优先 `web_search`；
       - 当用户提到 “帮我找下我昨天收到的某封邮件” 时，优先 gws Gmail；
       - 当用户提到 “下周三我有没有空” 这类自我日程问题，优先 gws Calendar。

3. **架构层级定位**

在 Aelin 的能力分层中，gws 集成定位如下：

- Level 1：LLM 基本对话能力；
- Level 2：原子工具（tools）——`google_workspace` 属于这一层，与 `web_search` / `device` 类似，既可以读也可以在受控前提下执行少量写操作；
- Level 3：Plane（可委派系统）——如 PinchTab browser plane，不适用于 gws；
- Level 4：Aelin 特有的 plan 能力——在综合使用 gws / web_search / memory 时进行规划与监督。

也就是说，**gws 不是 plane**，而是一个“Google 工具族”的入口，由 Aelin 通过工具调用完成原子查询，再用自身规划能力组合这些结果，帮用户完成更长链路的任务。
