---
name: google-workspace
description: 使用 `google_workspace` 工具安全地访问和操作 Gmail、Drive、Calendar 与 Docs 等 Google Workspace 资源。
license: MIT
---

# Google Workspace Skill for DeepAgents

本技能文件向 DeepAgents 说明如何通过 `google_workspace` 工具与用户的 Google 账号交互。

## 能力概览

- 读取 Gmail 邮件列表与邮件内容。
- 读取 Google Drive / Docs / Sheets / Slides 元数据。
- 在写权限开启时，可以执行写操作（例如创建文档、发送邮件等），但需要遵守安全策略。

## 使用约定

1. 所有操作都通过 `google_workspace` 工具完成，使用 `action` 字段区分具体功能：
   - 读能力示例：
     - `auth_status`：检查认证与 scope。
     - `gmail_list` / `gmail_get`：列出或读取邮件。
     - `drive_list`：列出 Drive 文件。
   - 写能力示例（仅在 Aelin 策略允许时使用）：
     - `docs_create`：创建 Google 文档。
     - 后续可能扩展的 `gmail_send`、`calendar_create_event` 等。

2. 在尝试写操作前，应先调用 `auth_status` 检查：
   - 用户是否已登录。
   - 是否具备所需 scope（如 `documents`、`drive` 等）。

3. 写操作需要遵守以下原则：
   - 只在用户明确要求时创建或修改内容（例如「帮我创建一个 Google 文档」）。
   - 文档、事件、邮件的标题与内容应简洁、可读，并用用户的语言回答。

4. 如果出现权限不足或配置错误：
   - 工具会返回 `ok: false` 和 `error` 字段。
   - 应向用户解释无法完成的原因，并给出下一步建议（例如要求用户在本地完成登录）。

