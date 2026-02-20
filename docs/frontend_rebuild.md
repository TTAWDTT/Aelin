# Frontend Rebuild 方案（Aelin）

本文档描述：在你已删除旧 `frontend/` 的前提下，为 Aelin 从 0 重建一个更贴合产品核心（证据引用 / 长期记忆 / 长期跟踪 / 主动提醒 / 多端壳）的全新前端的**开发方案**与**预期效果**。

> 本方案已显式参考并贯彻以下 skill 的要求：`brand-guidelines`（配色/字体基调）、`frontend-design`（明确审美方向、避免“模板化 UI”）、`vercel-react-best-practices`（减少瀑布、优化包体、避免无谓重渲染等）。

---

## 1. 重建目标与非目标

### 1.1 目标（必须达成）

1. **Chat-first**：`/` 默认进入 Aelin Chat；对话输出支持：
   - 流式（`POST /api/v1/aelin/chat/stream`）
   - 结构化响应（answer/citations/actions/tool_trace/memory_summary/expression）
   - Markdown 安全渲染（可复制、可跳转、可预览引用证据）
2. **Evidence-first**：任何关键结论尽量能被“证据卡（citation）”审阅，并能：
   - 预览
   - 在 Signals/Desk 中定位原消息（message_id）
   - 打开外部网页（web citations）
3. **Tracking-first**：把“长期跟踪”从“附属功能”提升为一级产品资产：
   - 跟踪中心（列表/状态/过滤/详情）
   - 变化流（severity、ack、change_type）
   - 快照（snapshots）与差异阅读
   - `POST /api/v1/aelin/track/confirm` 的确认与配置引导（needs_config → Settings）
4. **主动提醒可用**：通知中心与角标（`GET /api/v1/aelin/proactive/poll` + `GET /api/v1/aelin/notifications`）
5. **设置即健康面板**：把“是否可用”做成可自检与可修复的体验：
   - 数据源连接（accounts + OAuth）
   - Agent/LLM 配置（catalog/config/test）
6. **多端一致**：Web / Electron / Capacitor 维持一套前端产物（Vite `dist/`），满足：
   - `desktop/` 打包仍可复用 `../frontend/dist`
   - 移动壳仍可 `cap sync`（需要 HashRouter 与触控优化）

### 1.2 非目标（明确不做或后置）

- 团队多租户、组织协作、权限系统（当前后端也是单用户兜底逻辑为主）。
- “全自动外部动作执行”（目前 actions 以导航/创建任务/建议为主；设备动作受 OS/权限限制）。
- 追求 100% 还原旧前端的交互细节（本方案**不沿用**旧 UI）。

---

## 2. 设计方向（审美与交互哲学）

### 2.1 统一审美方向：**“温暖的证据编辑台（Editorial Evidence Desk）”**

我们把 Aelin 的核心差异（长期信号 → 证据 → 记忆 → 跟踪）视觉化为一个“编辑台”：

- “答案”像编辑稿，优先可读。
- “证据”像脚注与卡片，可随时翻证、回看上下文。
- “跟踪”像持续更新的专题报道（变化流 + 快照对比）。

### 2.2 品牌配色与字体（来自 brand-guidelines）

基础色（强对比、可读性优先）：

- Ink Dark：`#141413`（主文字/深色背景）
- Parchment Light：`#faf9f5`（浅色背景）
- Mid Gray：`#b0aea5`（次级文字/边界）
- Light Gray：`#e8e6dc`（卡片底/分隔）

强调色（用于关键动作、状态、提醒）：

- Orange：`#d97757`（主强调：跟踪、确认、关键 CTA）
- Blue：`#6a9bcc`（次强调：跳转、引用、外链）
- Green：`#788c5d`（第三强调：成功、已同步、健康）

字体策略：

- Headings：Poppins（fallback：Arial）
- Body：Lora（fallback：Georgia）
- 中文 fallback（建议）：`"Noto Serif SC"`, `"Source Han Serif SC"`, `"PingFang SC"`, `"Microsoft YaHei"`

> `frontend-design` 强调避免“无差别模板 UI”。因此：字体/排版会更“编辑部”，同时保证中文阅读舒适。

### 2.3 动效策略（少而准）

- 只在“高价值时刻”做动效：页面首屏进入、对话流式输出、引用卡展开、跟踪变化到达。
- 避免处处 bounce 的“动效噪音”；默认尊重 `prefers-reduced-motion`。

---

## 3. 信息架构（IA）与路由

### 3.1 顶级导航（4 个一级区）

1. **Chat（Aelin）**：默认入口（`/`）
2. **Signals（Desk）**：消息聚合与检索（`/signals`）
3. **Tracking**：跟踪中心（`/tracking`）
4. **Settings**：配置与健康（`/settings`）

辅助入口：

- **Notifications**：可做为右侧抽屉/面板，不一定独立路由（也可 `/notifications`）
- **Device Center**：右侧抽屉/面板（桌面优先）；移动端作为全屏页

### 3.2 关键路由建议（含深链）

- `/`：Aelin Chat（带 workspace 参数：`?workspace=default`）
- `/signals`：聚合视图（支持 `?workspace=work&q=xxx&unread=1`）
- `/signals/contact/:contactId`：联系人线程（可 `?beforeId=...`）
- `/message/:messageId`：消息详情（后端已有 `GET /api/v1/messages/{message_id}`）
- `/tracking`：目标列表（状态/来源/关键字过滤）
- `/tracking/:targetId`：目标详情（changes/snapshots/file-memory）
- `/settings`：配置面板（accounts / agent / appearance / profile）

> 桌面壳兼容：保留 `/desk` 的跳转策略可后置（新 IA 用 `/signals` 取代“Desk”命名，但可以做别名路由以兼容历史链接）。

---

## 4. 技术栈与工程结构

### 4.1 推荐栈（以“可控、可打包、多端”优先）

- 构建：Vite（产物 `dist/`，方便 Electron extraResources）
- UI：Tailwind CSS（强调排版与密度）+ Headless/无障碍 primitives（Radix UI 或 Headless UI）
- Router：React Router（web 用 BrowserRouter，移动壳用 HashRouter）
- Data Fetch：SWR（请求去重、缓存、并发控制；符合 vercel 客户端数据获取建议）
- 表单：React Hook Form + Zod（可选）
- Markdown：react-markdown + rehype-sanitize（避免 XSS）
- 长列表：react-virtuoso 或 @tanstack/react-virtual（消息/变化流虚拟化）
- 测试：Vitest + Testing Library；关键流补充 Playwright（可选）
- 类型：从 OpenAPI 生成 TypeScript types（`openapi-typescript`）

> 选择 SWR 的原因：对“同一资源多处订阅”非常友好，天然去重；并且迁移成本低。

### 4.2 目录结构（建议）

重建后的 `frontend/`（示意）：

```text
frontend/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  public/
  src/
    app/
      routes/
      layout/
      providers/
    features/
      chat/
      signals/
      tracking/
      settings/
      notifications/
      device/
    components/
      ui/
      common/
    api/
      client.ts
      sse.ts
      endpoints.ts
      types.generated.ts
    store/
    styles/
      tokens.css
      globals.css
    utils/
    test/
```

### 4.3 Vercel React Best Practices（在本项目的落地方式）

重点落地项（不空喊口号）：

- **避免瀑布**：
  - Chat 页面首屏：并行拉取 `GET /api/v1/aelin/context` 与恢复本地会话（Promise 并行、await 延后）
  - Tracking 详情：并行拉取 targets + changes + snapshots（互不依赖则 `Promise.all`）
- **包体优化**：
  - Chat / Signals / Tracking / Settings 做路由级 code-splitting（动态 import）
  - 重组件（Markdown 渲染、虚拟列表、图像预览）按需加载
- **重渲染控制**：
  - 将“长列表 item”拆为 memoized row
  - localStorage/IndexedDB 读取做缓存（避免每次 render 读）
  - 事件处理器稳定化（必要时用 ref 保存 handler，避免子组件频繁重渲染）

---

## 5. 核心交互与页面效果（你最终会看到什么）

### 5.1 Chat（Aelin）页面

你会看到一个“编辑台式”的对话界面：

- 中央：对话流（虚拟化，支持大量历史）
- 右侧（可收起）：上下文面板
  - Memory Layers（分层摘要）
  - Today Focus（高价值 signals）
  - Suggested Actions（可执行 chips）
  - Citations Stack（证据栈）
- 输入区：
  - 支持图片（最多 4 张，发送到 `images: [{data_url,name}]`）
  - 支持 “Local/Web/Auto” 搜索模式切换（映射 `search_mode`）

对话消息的结构化增强：

- `citations` 以“脚注卡”形式出现在答案段落旁：
  - 点击 → 右侧预览抽屉
  - “在 Signals 中定位” → 直接打开 `message_id`
  - 外链 → 新标签打开
- `actions` 以 chips 形式展示，点击会触发：
  - open_settings / open_tracking / open_message / confirm_track 等
- `tool_trace` 以“轻量进度条”形式出现（不喧宾夺主）

### 5.2 Signals（聚合）页面

你会得到一个“密度更高、可快速处理未读”的信号台：

- 左侧：工作区 + 过滤（未读、来源、时间窗）
- 中央：联系人卡片（未读数、最新主题/预览、来源徽标）
- 右侧：线程内容（点击联系人进入；支持“标记已读”）
- 每条消息上有一组快捷按钮：
  - 总结（Agent summarize）
  - 生成待办（todo）
  - 建议跟踪（track confirm）
  - 复制引用（生成 citation 样式文本）

### 5.3 Tracking 页面

你会看到“目标列表 + 变化流 + 快照对比”的完整闭环：

- 目标列表：
  - 状态（active/paused/error）
  - unread changes 数
  - next_run_at / last_run_at
  - notify_level 与 mute_until
- 详情页：
  - Changes：按 severity 与 ack 过滤；一键 ack
  - Snapshots：可选择两个版本做差异阅读（高亮新增/删除/更新）
  - File memory：提供搜索框（`/api/v1/aelin/tracking/file-memory/search`）返回 markdown 命中预览

### 5.4 Settings（配置与健康）

你会看到“我现在到底能不能用”的一屏答案：

- Accounts：
  - 各 provider 的连接状态、最后同步时间、错误提示
  - OAuth 一键授权（Gmail/Outlook/GitHub）
  - forward 的专属转发地址展示与复制
- Agent：
  - `GET /api/v1/agent/catalog` 选择 provider/model
  - 保存 config（`PATCH /api/v1/agent/config`）
  - 一键 test（`POST /api/v1/agent/test`）
- Appearance：
  - Light/Dark（默认跟随系统，可手动覆盖）
  - 字体与密度（阅读模式：标准/紧凑）

### 5.5 Notifications + Device Center

- Notifications：角标 + 抽屉列表，每条通知都带下一步动作按钮。
- Device Center（桌面优先）：
  - “能力矩阵”提示（平台/权限限制）
  - 进程列表（按异常分排序）
  - 结束进程/调优先级必须二次确认
  - 模式切换（meeting/focus/sleep/normal）会展示“已应用/仅记录状态”的明确反馈

---

## 6. 与后端契约：接口与数据模型（前端视角）

### 6.1 Aelin Chat

- `POST /api/v1/aelin/chat`
- `POST /api/v1/aelin/chat/stream`
- 请求（关键字段，来自 `backend/app/schemas.py`）：
  - `query`（必填）
  - `use_memory`（默认 true）
  - `max_citations`（默认 6）
  - `workspace`（默认 default）
  - `images[]`（最多 4，`{data_url,name}`）
  - `history[]`（最多 20 turns）
  - `search_mode`（auto/local/web）
- 响应：
  - `answer`
  - `citations[]`（含 `message_id`）
  - `actions[]`
  - `tool_trace[]`
  - `memory_summary`
  - `expression`（驱动表情/情绪表达素材）

### 6.2 Context / Proactive / Notifications

- `GET /api/v1/aelin/context`：右侧上下文面板（summary/focus_items/notes/todos/pins/daily_brief/layout_cards/memory_layers/notifications）
- `GET /api/v1/aelin/proactive/poll`：主动提醒轮询
- `GET /api/v1/aelin/notifications`：通知列表（如需要独立刷新）

### 6.3 Tracking

- `GET /api/v1/aelin/tracking`（或 `/tracking/targets`）：目标列表
- `PATCH /api/v1/aelin/tracking/targets/{target_id}`：更新状态/频率/免打扰/标签等
- `POST /api/v1/aelin/tracking/targets/{target_id}/run`：立即运行
- `GET /api/v1/aelin/tracking/targets/{target_id}/changes`：变化流
- `POST /api/v1/aelin/tracking/changes/{change_id}/ack`：确认已读
- `GET /api/v1/aelin/tracking/targets/{target_id}/snapshots`：快照列表
- `GET /api/v1/aelin/tracking/file-memory/search`：文件化记忆检索
- `POST /api/v1/aelin/track/confirm`：从 Chat 发起的“确认跟踪”

### 6.4 Accounts / Agent / Signals

- Accounts（`/api/v1/accounts...`）：连接、同步、OAuth 配置与回调
- Agent（`/api/v1/agent/...`）：catalog/config/test/memory/todos/daily-brief/search 等
- Contacts/Messages（signals 的基础数据）：
  - `GET /api/v1/contacts`
  - `GET /api/v1/contacts/{contact_id}/messages`
  - `POST /api/v1/contacts/{contact_id}/mark-read`
  - `GET /api/v1/messages/{message_id}`

---

## 7. 性能、可用性与安全（前端侧）

### 7.1 性能

- 长列表全部虚拟化（消息流、跟踪 changes、通知列表）。
- 首屏并行加载（context + 本地会话恢复）。
- 路由级拆包，减少初始 JS。

### 7.2 可用性

- 离线/弱网提示：SWR error + retry 策略与“重新连接流式”的按钮。
- 关键动作二次确认：结束进程、删除 todo、删除 note、暂停/删除跟踪目标等。

### 7.3 安全

- Markdown 渲染必须 sanitize（避免 XSS）。
- 外链统一经过安全跳转/提示（可选）。
- 头像/图片预览遵循大小限制与错误处理（后端头像限制 5MB；Chat 图片 data_url 可能很大，需要前端压缩策略可选）。

---

## 8. 开发计划（可执行的里程碑）

> 你可以把它理解为“按顺序交付、每一步都有可见成果”的重建路线。

### Milestone 0：脚手架与契约（1–2 天）

- 重建 `frontend/`：Vite + React + TS + Tailwind
- 加入 OpenAPI types 生成脚本（本地跑后端时生成）
- 基础路由与 Layout（4 顶级区 + 右侧面板容器）

### Milestone 1：Chat 闭环（2–4 天）

- `GET /api/v1/aelin/context` 面板可用
- `POST /api/v1/aelin/chat/stream` 流式可用（含 tool_trace 解析与断线重试）
- citations/actions 基础 UI 可用
- `track/confirm` 从 action 走通（needs_config → 跳 Settings）

### Milestone 2：Signals 闭环（2–4 天）

- contacts 列表、线程、mark-read、message detail
- “在 Signals 中打开 citation”链路完成

### Milestone 3：Tracking 闭环（3–6 天）

- 列表/过滤/详情（changes/snapshots/ack）
- 快照差异阅读（先简单文本 diff，再逐步增强）
- file-memory search UI

### Milestone 4：Settings/健康面板（2–4 天）

- Accounts 接入（OAuth start/callback 的弹窗/深链策略）
- Agent catalog/config/test

### Milestone 5：多端收口（1–3 天）

- Electron：验证 `desktop/` 对 `frontend/dist` 的引用恢复可打包
- Mobile：HashRouter、触控与键盘（Capacitor Keyboard）适配

---

## 9. 验收标准（Definition of Done）

- `npm run dev`：能在浏览器打开并完成 Chat → citations → 跳 Signals → track confirm → Tracking 详情 的完整链路。
- `npm run build`：生成 `frontend/dist`，`desktop/` 能引用并打包（至少开发模式可跑）。
- 流式输出在弱网情况下可恢复，不会把 UI 卡死。
- 无障碍：键盘可用、焦点可见、对比度足够、`prefers-reduced-motion` 生效。

---

## 10. 下一步（建议你确认的 3 件事）

1. 新前端是否沿用名称 **Signals**（替代旧的 Desk）？还是继续叫 Desk（仅改 UI）？
2. 你更偏好**密度更高的编辑台**（信息多、效率高）还是**更松弛的对话体验**（留白多）？
3. Tracking 是否要作为默认显眼入口（例如左侧栏置顶、未读 changes 角标）？

确认后我就可以按本文档开始把 `frontend/` 从 0 重建出来，并逐里程碑交付可运行版本。

