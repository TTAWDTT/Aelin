# Pinchtab 登录协同设计草案（Browser Plane Login Flow）

> 目标：让「Aelin + Pinchtab browser plane」在遇到登录/验证码/2FA 时，有一套清晰可执行的协同流程，而不是只丢一句“请登录”给用户。

## 一、问题背景与目标

当前行为（真实链路观测）：

- Aelin 把复杂网页任务委派给 browser plane（Pinchtab）；
- Pinchtab 打开目标网站（例如 X），检测到在登录或验证页面；
- browser plane 进入 `waiting_user` 状态，带上 `requires_user_input + user_prompt`；
- agent loop 检测到 `waiting_user`，用 `plane_waiting_user` 收口，一句「请先登录」返给用户；
- 由于 Pinchtab 默认以 **headless 模式**运行，用户看不到浏览器窗口，不知道去哪儿登录。

目标：

- 为「需要用户登录/验证码/2FA」这种场景，定义一套完整的协同协议：
  - Pinchtab：如何标记状态与提示；
  - Aelin：如何翻译成可执行指引；
  - 用户：具体该到哪儿去操作、操作完要说什么；
  - UI：如何呈现/提醒。

## 二、运行模式策略：headless vs headed

Pinchtab 支持 headless/headed 两种模式。结合 Aelin 的实际使用场景：

### 2.1 短期策略（开发/桌面优先）

- 在 **桌面 + 开发** 场景下，优先使用 **headed 模式**：
  - Pinchtab 启动 Chrome 时指定 `mode="headed"`；
  - 这样 browser plane 一旦进入 `waiting_user`，你就能直接在被 Pinchtab 控制的浏览器窗口里看到登录页并操作。

- 对 headless 的保留：
  - 对于不需要用户交互、只是简单抓取/导航的任务，仍然可以考虑保持 headless；
  - 但短期内，为了降低心智负担，可以统一先走 headed，保证“看得到、点得到”。

### 2.2 中期策略（按任务动态切换）

中期可以进一步细化：

- 默认任务：headless；
- 一旦 Pinchtab 检测到登录/验证码场景：
  - 自动切到 headed 实例（或者创建一个 headed 的“登录辅助实例”）；
  - 明确告诉 Aelin「已经在某个 headed 窗口里打开登录页」；
  - Aelin 再将这个事实转述给用户。

本设计文档暂不展开动态切换的具体实现，先把「统一 headed + 协同协议」作为第一阶段落地目标。

## 三、browser plane 状态与 checkpoint 协议

当前 plane 侧已有的元素：

- 状态枚举：
  - `_ACTIVE_STATES = {"queued", "running", "waiting_user", "blocked"}`；
  - `_TERMINAL_STATES = {"completed", "failed", "closed"}`。
- `PlaneTaskCheckpoint` 机制：
  - `kind`：通过 `_checkpoint_kind` 判定（login / manual_review）；
  - `status=open/resolved`；
  - `prompt`：给用户看的提示；
  - `metadata_json`：记录 `state/last_url` 等辅助信息。
- `PinchTabBrowserPlaneAdapter`：
  - 根据 Pinchtab 返回的 `requires_user_login/user_prompt/status/...` 映射出：
    - `state="waiting_user"`；
    - `requires_user_input=True`；
    - `user_prompt="请在浏览器中完成登录..."` 等。

进一步的协议建议：

1. **login checkpoint 的判定规则**  
   - `_checkpoint_kind(payload)` 中，如果 `user_prompt + last_url` 中包含：
     - 登录 / sign in / log in / 验证码 / 2FA / challenge 等关键词；
   - 则 `kind="login"`，否则为 `manual_review`。

2. **waiting_user 状态的必要字段**  
   当 plane 进入 `waiting_user` 时，payload 应该至少包含：

   - `state="waiting_user"`；
   - `requires_user_input=True`；
   - `user_prompt`：给用户的自然语言提示（可由 Pinchtab skill 指导）；  
   - `last_url`：当前页面 URL（方便 Aelin 或 UI 告知“我们现在在哪个站点的登录页”）。

3. **多次轮询下的保持行为**  
   - 如果 plane 已经在 `waiting_user` 且仍未检测到登录完成：
     - 不应每次都重写 `user_prompt`，应保持原始提示；
     - `state` 仍然保持在 `waiting_user`，直到 Pinchtab 再次检测到已登录或任务失败。

## 四、Aelin 与用户的协同协议（逻辑层）

当 agent loop 检测到 active plane 且 `state="waiting_user"`、checkpoint.kind="login" 时，Aelin 应执行以下逻辑：

1. **必须向用户说明这些关键信息：**

   - 「我已经在一个由 Pinchtab 控制的浏览器实例中打开了登录/验证页面」；
   - 站点：根据 `last_url` 提取（例如 X、某 SaaS 后台等）；
   - 操作路径：告诉用户要去“刚刚弹出的浏览器窗口”里进行登录；
   - 完成后指令：要求用户登录后在聊天里回复固定话术。

2. **建议规范一段标准提示模板（示例）：**

   ```text
   我已经在一个由 Pinchtab 控制的浏览器窗口中打开了 {site} 的登录/验证页面。
   请你在该窗口中手动完成登录（包括验证码/2FA），完成后在这里回复：“已登录，继续”。
   如果登录失败，可以告诉我错误提示，我会尝试换一种方式处理。
   ```

   其中：

   - `{site}` 可以根据 `last_url` 的域名简化，比如：
     - `x.com` → “X（原 Twitter）”
     - `weibo.com` → “微博”
     - 若无法映射，就直接用域名。

3. **用户响应协议：**

   - 用户完成登录后，在 Chat 中回复：
     - `已登录，继续`（推荐固定短语，便于检测）；
   - Aelin 收到这条 message 时：
     - 可将其视作「登录已完成，可以继续原 browser plane 任务」的信号；
     - 在 agent loop 中，优先构造一次 `plane.continue` 调用，复用当前 `browser` plane 的 `task_id`。

4. **失败或中断场景：**

   - 如果用户在登录时遇到错误，可以回复错误提示（截屏 + 文本描述）；  
   - Aelin 可以选择：
     - 继续调用 `plane.status` 观察是否有更多细节；  
     - 或干脆关闭当前 plane 任务（`plane.close`），并退回纯说明性的回答。

## 五、桌面 / Web 前端的 UI 建议

为了让上述协议在 UI 层真正可执行，需要配合前端做一些改动（高层建议）：

### 5.1 waiting_user 登录状态的显式 banner

当 plane 状态为 `waiting_user` 且 checkpoint.kind="login" 时：

- 在 Chat 时间线中展示一个显式的 banner（而非普通消息），例如：

  - 标题：`浏览器 plane 等待你完成登录`；
  - 内容：显示上面那段标准提示文案；
  - 附带站点信息（如 X / 微博 / 某 SaaS）和 `last_url` 的简短预览。

### 5.2 桌面端的「唤起浏览器」/「在 Pinchtab 中查看」按钮

在 Electron 桌面版本中，可以考虑：

- 在 banner 或 plane trace 面板内加入一个按钮：
  - 文案：`在浏览器中查看` / `唤起登录窗口`；
  - 行为：通过桌面插件或 IPC，尝试将 Pinchtab 的 headed 浏览器窗口带到前台。

Web 版（纯浏览器）由于无法直接控制系统级窗口，可以先不实现这一点，仅依赖用户自己找到窗口。

### 5.3 plane trace 面板中的 login checkpoint 标记

在 plane trace 视图中，对于 login 类型 checkpoint：

- 以特殊图标/颜色标识；
- 显示简短信息：
  - 「等待用户登录 {site}」；
  - 「点击查看完整提示」；
- 方便用户回顾「为什么会停在这里」。

## 六、实现顺序建议

1. **后端配置层：允许 Pinchtab headed 模式**
   - 在 `PinchTabRuntime._config_payload()` 中：
     - 支持从 settings/env 读取 `instanceDefaults.mode`；
     - 开发/桌面环境默认配置为 `"headed"`；
   - 确保 headed 下 Pinchtab 能稳定拉起浏览器窗口。

2. **agent loop 层：收紧 login 分支处理**
   - 当检测到 active plane 的 `state="waiting_user"` 且 checkpoint.kind="login"：
     - 使用统一模板构造 user-facing 提示；
     - 明确在 `stop_reason="plane_waiting_user"` 时，告诉前端这是“等待登录”的特殊状态，而不是普通错误。

3. **前端层：登录协同 UI（可放入 plane UI 总方案中实现）**
   - 在 chat 时间线和 plane trace 中，实现：
     - waiting_user 登录 banner；
     - login checkpoint 标记；
     - 桌面端按钮（如有）。

4. **协议文档层：在 pinchtab skill / ability 相关文档中补充说明**

   - 在 Pinchtab skill 文档中增加：
     - 登录场景的使用建议；
     - 如何配合用户操作；
   - 在 `ability.md` / plane 文档中，明确这套登录协同是 browser plane 的标准行为。

---

本设计文档只定义了「Pinchtab 登录协同」这一部分的目标与协议，不直接修改代码。  
后续可以按上述顺序拆分为若干小 PR 实现，先从 headed 模式与 login 提示模板开始，再逐步完善前端 UI。 

