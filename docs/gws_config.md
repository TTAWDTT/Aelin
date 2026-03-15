## Google Workspace CLI（gws）本地配置与登录教程

本文档记录在 Windows 环境下，为 Aelin 准备可用的 Google Workspace CLI（`gws`）认证环境的完整步骤。目标是让 Aelin 能够通过 `google_workspace` 工具安全地访问你的 Gmail / Drive / Calendar / Docs 等数据，并在你明确同意后执行少量写操作（发邮件、创建日历事件、创建文档等）。

> 前置假设：你已经在本机安装好了 `gws` 命令（例如通过 `npm install -g @googleworkspace/cli`），并且正在使用同一台机器运行 Aelin backend。

---

### 一、确认 gws 与 gcloud 安装情况

1. 在终端（PowerShell）中检查 gws 是否可用：

   ```powershell
   gws --version
   ```

   能正常输出版本号即可。如果提示找不到命令，需要先安装：

   ```powershell
   npm install -g @googleworkspace/cli
   ```

2. gws 的 `auth setup` 依赖 Google Cloud SDK（`gcloud`），先确认是否已经安装并在 PATH 中：

   ```powershell
   gcloud --version
   ```

   - 若有版本输出，说明已经安装。
   - 若提示找不到命令，请先按照 Google 官方文档安装 Cloud SDK，然后重新打开终端再检查一遍。

---

### 二、在 Google Cloud Console 中启用 API 并创建 OAuth 客户端

这一步是为 gws 和 Aelin 准备 OAuth 客户端凭据，并启用所需的 Google API，避免出现 “No OAuth client configured” 或各类 403 错误。

1. 打开 Google Cloud Console，选择/创建一个项目，用于 gws 集成（后续所有 API 都应启用在同一个项目下）。
2. 在左侧菜单中进入 `API 和服务` → `已启用的 API 和服务`：
   - 搜索并启用至少以下 API：
     - `Gmail API`
     - `Google Drive API`
     - `Google Calendar API`
     - `Google Docs API`
   - 如果后续还要用 Sheets/Slides 等服务，也可以一并启用：
     - `Google Sheets API`
     - `Google Slides API`
3. 在同一模块中进入 `凭据` 页面：
   - 点击「创建凭据」→「OAuth 客户端 ID」。
   - 应用类型选择「桌面应用」。
   - 名称可以写成 `aelin-gws`（或任意你能识别的名字）。
   - 创建完成后，点击下载 JSON 凭据文件。

4. 将下载的 JSON 文件重命名为：

   ```text
   client_secret.json
   ```

   并放到（如果目录不存在可以手动创建）：

   ```text
   C:\Users\<你的用户名>\.config\gws\client_secret.json
   ```

   在你当前环境下，这个路径通常是：

   ```text
   C:\Users\86153\.config\gws\client_secret.json
   ```

---

### 三、配置 OAuth 同意屏幕并添加测试用户

如果你在浏览器授权时遇到如下提示：

> “禁止访问：“aelin-gws”尚未完成 Google 验证流程……仅供已获开发者批准的测试人员使用……错误 403：access_denied”

说明当前 OAuth 应用处于测试模式，且你的 Google 账号还不在测试用户白名单中。

按下面步骤处理：

1. 在 Google Cloud Console 中，进入 `API 和服务` → `OAuth 同意屏幕`。
2. 确认应用名称为你刚刚创建的那个（例如 `aelin-gws`）。
3. 在页面下方找到「测试用户」模块：
   - 点击「添加用户」。
   - 输入你要用来登录的 Google 账号邮箱，例如：

     ```text
     luoz061114@gmail.com
     ```

   - 保存更改。

4. 再次从本机发起授权登录（见下一节），此时不应再出现 403 access_denied。

---

### 四、使用 gws 执行 OAuth 登录（读/写全功能）

确保前面的 client_secret、测试用户、API 启用 都配置完成后，在本机终端执行：

1. 先清理可能的旧状态（可选）：

   ```powershell
   gws auth logout
   ```

2. 发起登录流程：

   - 如只希望 Aelin 拥有只读能力（推荐起步）：

     ```powershell
     gws auth login --readonly --services=gmail,drive,calendar,docs
     ```

   - 如希望 Aelin 可以执行写操作（发邮件、创建日历事件、创建文档等）：

     ```powershell
     gws auth login --full
     ```

   说明：
   - `--readonly` 会请求一组只读 scope，适合只看不写的场景。
   - `--full` 会请求更宽的 scope（含 cloud-platform、pubsub 等），适合本地完全信任的开发环境。
   - 这两个命令都会自动打开浏览器。
   - 浏览器里选择你在测试用户列表中的 Google 账号。
   - 若看到「Google 尚未验证此应用」之类的提示，可以点击「高级」→「继续访问（不安全）」完成授权（因为这是你自己创建的测试应用）。

3. 授权成功后，回到终端执行：

   ```powershell
   gws auth status
   ```

   你应当看到类似字段，表示已经登录且 token 有效：

   - `token_valid: true`
   - `user: <你的 Gmail 地址>`
   - `scope_count` 以及具体的 scope 列表，例如：
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/documents`
     - `https://www.googleapis.com/auth/drive`

若这里仍然是未登录状态，或者 scope 明显不全，通常是：

- client_secret.json 路径不正确；
- 使用了与测试用户列表不一致的账号；
- 浏览器授权过程中被中断或取消；
- 之前用的是过于受限的 scope，需要重新执行 `gws auth login`。

请重新检查前面几个步骤并重登。

---

### 五、可选：本地验证读写 API 是否真的可用

在让 Aelin 使用之前，可以先用 gws 命令行做一次「读 + 写」的真实测试，以确认：

- OAuth 已配置正确；
- 对应 API 已启用；
- 账号 scope 足够。

1. 测试读取 Gmail（只读能力）

   ```powershell
   gws gmail users messages list --params '{\"userId\":\"me\",\"maxResults\":5,\"q\":\"is:unread\"}'
   ```

   若命令返回最近几封未读邮件的 JSON 列表，说明 Gmail 读能力正常。

2. 测试创建日历事件（写操作）

   先用 `--dry-run` 验证参数：

   ```powershell
   gws calendar events insert `
     --dry-run `
     --params '{\"calendarId\":\"primary\"}' `
     --json   '{\"summary\":\"Aelin test event\",\"start\":{\"dateTime\":\"2026-03-16T10:00:00+08:00\"},\"end\":{\"dateTime\":\"2026-03-16T11:00:00+08:00\"}}'
   ```

   若 dry-run 返回 `dry_run: true` 且没有报错，再去掉 `--dry-run` 真正创建：

   ```powershell
   gws calendar events insert `
     --params '{\"calendarId\":\"primary\"}' `
     --json   '{\"summary\":\"Aelin test event\",\"description\":\"Created by Aelin/gws for integration test. You can safely delete this.\",\"start\":{\"dateTime\":\"2026-03-16T10:00:00+08:00\"},\"end\":{\"dateTime\":\"2026-03-16T11:00:00+08:00\"}}'
   ```

   - 若成功，会返回包含 `id`、`summary`、`htmlLink` 等字段的 JSON。
   - 你可以在 Google 日历中搜索 `Aelin test event` 确认是否存在（该事件可随时手动删除）。

3. 测试创建 Google 文档（写操作）

   ```powershell
   gws docs documents create --json '{\"title\":\"Aelin test doc\"}'
   ```

   若成功，会返回：

   - `documentId`: 文档 ID；
   - `title`: `Aelin test doc`；

   然后可以在浏览器中访问：

   ```text
   https://docs.google.com/document/d/<documentId>/edit
   ```

   即可看到这个测试文档，同样可以随时删除。

> 注意：如果上述写操作返回 403 且错误提示类似 “API has not been used in project ... or it is disabled”，通常是对应 API 在 GCP 项目中尚未启用或刚刚启用未生效。请回到“二、启用 API”按链接启用对应 API，稍等几分钟再重试。

---

### 六、与 Aelin 集成后的验证思路

当本机 `gws auth status` 已经显示登录成功时，Aelin 就可以通过 `google_workspace` 工具实际调用 gws CLI 访问你的 Workspace 数据。

简单的验证思路如下：

1. 启动 Aelin backend，例如：

   ```powershell
   cd backend
   python -m uvicorn app.main:app --port 8000
   ```

2. 使用 HTTP 请求模拟用户提问（示意）：

   ```bash
   curl -s -X POST http://127.0.0.1:8000/api/v1/aelin/chat ^
     -H "Content-Type: application/json" ^
     -d "{\"workspace\":\"default\",\"provider\":\"openai\",\"query\":\"帮我列一下最近的 Gmail 未读邮件\",\"images\":[],\"history\":[]}"
   ```

3. 在后端日志或返回的 `tool_trace` 中观察：
   - 期望看到 `google_workspace:ok`，不再是 `gws_not_installed`、`gws_failed:...` 或 401 未授权错误。
   - Aelin 的回答中会引用真实的 Gmail 邮件列表（主题、发件人、时间等）。

当你能走通上面的整条链路时，说明 gws 与 Aelin 的「读取能力」已经配置成功。

如果还希望验证 Aelin 的写能力（例如通过对话说「帮我创建一个明天早上 9 点的日历事件」），需要满足：

- gws 已使用 `--full` 或包含写 scope 的方式登录；
- 对应 API（Calendar / Docs / Gmail）已经在 GCP 项目中启用；
- Aelin 的 ToolPolicy 已允许 `google_workspace` 写操作（由后端配置 `allow_write_tools`、`max_write_calls` 控制）。

在这些前提满足后，Aelin 就可以在你明确提出写需求时，调用 `google_workspace` 的写 action（如 `calendar_create_event`、`gmail_send`、`gmail_draft`）来帮你真正创建事件/邮件/草稿。
