# Aelin 前端重建设计文档

> **文档版本**：v2.0 · 2026-02-21
> **定位**：完整的前端架构设计文档，基于对 Aelin 后端 61 个 API 端点、12 个数据源连接器、17 个服务模块、以及全部产品设计文档的深度分析，提出**从零重建**的系统性方案。

---

## 目录

- [第一部分：现状分析](#第一部分现状分析)
  - [1. 后端功能全景](#1-后端功能全景)
  - [2. 现有前端的架构与问题](#2-现有前端的架构与问题)
- [第二部分：设计哲学](#第二部分设计哲学)
  - [3. 产品内核与设计原则](#3-产品内核与设计原则)
  - [4. 视觉设计语言](#4-视觉设计语言)
- [第三部分：架构设计](#第三部分架构设计)
  - [5. 技术栈选型](#5-技术栈选型)
  - [6. 工程目录结构](#6-工程目录结构)
  - [7. 状态管理架构](#7-状态管理架构)
  - [8. API 对接层设计](#8-api-对接层设计)
- [第四部分：信息架构与布局](#第四部分信息架构与布局)
  - [9. 路由与导航体系](#9-路由与导航体系)
  - [10. 响应式布局系统](#10-响应式布局系统)
- [第五部分：核心页面交互设计](#第五部分核心页面交互设计)
  - [11. Aelin Chat — 主对话区](#11-aelin-chat--主对话区)
  - [12. Context Panel — 右侧上下文面板](#12-context-panel--右侧上下文面板)
  - [13. Signals — 信息聚合面板](#13-signals--信息聚合面板)
  - [14. Tracking — 持续追踪中心](#14-tracking--持续追踪中心)
  - [15. Settings — 配置与健康面板](#15-settings--配置与健康面板)
  - [16. Notifications — 通知中心](#16-notifications--通知中心)
  - [17. Device Center — 设备中心](#17-device-center--设备中心)
- [第六部分：后端接口契约](#第六部分后端接口契约)
  - [18. API 端点全量映射](#18-api-端点全量映射)
- [第七部分：多端适配](#第七部分多端适配)
  - [19. Electron 桌面端](#19-electron-桌面端)
  - [20. Capacitor 移动端](#20-capacitor-移动端)
- [第八部分：性能、安全与测试](#第八部分性能安全与测试)
  - [21. 性能优化策略](#21-性能优化策略)
  - [22. 安全策略](#22-安全策略)
  - [23. 测试策略](#23-测试策略)
- [第九部分：开发路线图](#第九部分开发路线图)
  - [24. 里程碑计划](#24-里程碑计划)
  - [25. 验收标准](#25-验收标准)
- [附录](#附录)
  - [A. 表情系统映射表](#a-表情系统映射表)
  - [B. 设计 Token 完整定义](#b-设计-token-完整定义)
  - [C. 与旧前端的差异对照](#c-与旧前端的差异对照)

---

# 第一部分：现状分析

## 1. 后端功能全景

Aelin 后端提供 **61 个 API 端点**，横跨 7 个路由模块和 17 个服务/连接器层。新前端必须完整承接以下功能域：

### 1.1 认证与用户（5 端点）

| 端点 | 说明 |
|---|---|
| `POST /register` | 用户注册 |
| `POST /token` | JWT 登录 |
| `GET /me` | 获取当前用户 |
| `PATCH /me` | 更新用户信息 |
| `POST /me/avatar` | 上传头像（≤5MB，png/jpg/webp/gif） |

**特殊机制**：单用户桌面端模式 — 无 token 时自动 fallback 到本地用户，实现免登录体验。

### 1.2 多源信息采集（13 端点）

支持 **12 个数据源 Provider**，每个有主策略 + 回退链：

| 类别 | Provider | 抓取策略 |
|---|---|---|
| 邮件 | Gmail (OAuth)、Outlook (OAuth)、IMAP、邮件转发 | OAuth 授权 / IMAP 拉取 / Webhook 接收 |
| 社交/视频 | X(Twitter)、B站、抖音、小红书、微博 | API → Cookie GraphQL → RSSHub 回退 |
| 订阅 | RSS/Blog、GitHub (OAuth) | RSS 订阅 / GitHub API |
| 调试 | Mock | 模拟数据 |

关键端点：

| 端点 | 说明 |
|---|---|
| `GET /accounts` | 列出已连接账户 |
| `POST /accounts` | 添加数据源 |
| `GET /accounts/oauth/{provider}/start` | 启动 OAuth 流 |
| `GET /accounts/oauth/{provider}/callback` | OAuth 回调 |
| `GET /accounts/oauth/{provider}/config` | 查询 OAuth 凭据 |
| `PATCH /accounts/oauth/{provider}/config` | 设置自定义 OAuth 凭据 |
| `GET /accounts/{id}/forward-info` | 获取邮件转发地址 |
| `POST /accounts/{id}/sync` | 触发同步 Job |
| `GET /accounts/sync-jobs/{job_id}` | 查询同步状态 |
| `DELETE /accounts/{id}` | 删除数据源 |
| `GET /accounts/x/config` | X API 配置状态 |
| `PATCH /accounts/x/config` | 设置 X Bearer Token |
| `PATCH /accounts/x/cookies` | 设置 X Cookie |

### 1.3 联系人与消息（4 端点）

| 端点 | 说明 |
|---|---|
| `GET /contacts` | 搜索联系人（带未读计数/最新消息预览） |
| `GET /contacts/{id}/messages` | 联系人消息列表（`before_id` 分页） |
| `POST /contacts/{id}/mark-read` | 标记全部已读 |
| `GET /messages/{id}` | 消息详情 |

### 1.4 Aelin 核心智能体（20 端点）— 最核心模块

#### 对话系统

| 端点 | 说明 |
|---|---|
| `POST /aelin/chat` | 同步对话 → 结构化响应 |
| `POST /aelin/chat/stream` | **SSE 流式对话** → 事件序列 `[intent, plan, tool_step, citations, actions, reply, done, error]` |

**内部流水线（5906 行核心逻辑）**：

```
用户输入
  → Intent Lens Agent（意图识别）
  → Main Agent Planner（工具规划：local_search vs web_search）
  → Critic Agent（审计修正）
  → Web Query Decomposer（分解为 3-5 个正交搜索 facet）
  → 并行子 Agent（最多 5 Web + 5 Local 并发）
  → Trace Agent（追踪意图处理 → 追踪建议）
  → Reply Agent（综合证据生成最终回复）
  → Expression System（选择 11 种表情之一）
```

#### 上下文与通知

| 端点 | 说明 |
|---|---|
| `GET /aelin/context` | 完整上下文包（记忆摘要 + 焦点项 + 笔记 + 待办 + Pin推荐 + 每日简报 + 布局卡片 + 记忆分层 + 通知） |
| `GET /aelin/notifications` | 通知列表（合并记忆 + 追踪变化） |
| `GET /aelin/proactive/poll` | 主动推送轮询（管理 seen 状态） |

#### 追踪系统

| 端点 | 说明 |
|---|---|
| `POST /aelin/track/confirm` | 确认并创建追踪订阅 |
| `GET /aelin/tracking` | 列出追踪目标（带未读变化数） |
| `PATCH /aelin/tracking/targets/{id}` | 更新追踪目标 |
| `POST /aelin/tracking/targets/{id}/run` | 立即执行一次 |
| `GET /aelin/tracking/targets/{id}/changes` | 变化列表（可按 severity/type/ack 筛选） |
| `POST /aelin/tracking/changes/{id}/ack` | 确认变化 |
| `GET /aelin/tracking/targets/{id}/snapshots` | 快照列表 |
| `GET /aelin/tracking/file-memory/search` | 文件化记忆语义搜索 |

#### 设备中心

| 端点 | 说明 |
|---|---|
| `GET /aelin/device/capabilities` | 设备能力检测 |
| `GET /aelin/device/processes` | 进程列表（异常评分） |
| `POST /aelin/device/processes/{pid}/action` | 进程操作 |
| `POST /aelin/device/processes/optimize` | 一键优化 |
| `GET /aelin/device/mode` | 当前模式 |
| `POST /aelin/device/mode/apply` | 应用模式（meeting/focus/sleep/normal） |

### 1.5 Agent 辅助功能（17 端点）

| 端点 | 说明 |
|---|---|
| `POST /agent/chat` | Agent 流式对话（SSE + 工具调用） |
| `GET /agent/catalog` | 模型目录（多提供商） |
| `POST /agent/summarize` | 文本摘要 |
| `POST /agent/summarize/stream` | 流式摘要 |
| `POST /agent/draft-reply` | 回复草稿 |
| `POST /agent/draft-reply/stream` | 流式回复草稿 |
| `GET /agent/config` | Agent 配置 |
| `PATCH /agent/config` | 更新 Agent 配置 |
| `GET /agent/memory` | 记忆快照 |
| `POST /agent/memory/notes` | 添加记忆笔记 |
| `DELETE /agent/memory/notes/{id}` | 删除笔记 |
| `POST /agent/memory/layout` | 保存布局偏好 |
| `GET /agent/pin-recommendations` | Pin 推荐 |
| `GET /agent/daily-brief` | 每日简报 |
| `GET/POST/PATCH/DELETE /agent/todos` | 待办 CRUD |
| `POST /agent/search/advanced` | 高级搜索 |
| `POST /agent/test` | 连通性测试 |

### 1.6 邮件转发接收（2 端点）

| 端点 | 说明 |
|---|---|
| `POST /inbound/forward/{secret}` | 通过 secret 接收转发邮件 |
| `POST /inbound/forward` | 通用邮件接收（自动解析 MIME） |

---

## 2. 现有前端的架构与问题

### 2.1 现有技术栈

| 类别 | 选型 |
|---|---|
| 框架 | React 18 + TypeScript 5.4 |
| 构建 | Vite 5 |
| UI 库 | MUI v7 (Material Design) |
| 动画 | framer-motion v12 |
| 数据 | SWR v2 |
| 移动端 | Capacitor 6 |
| 桌面端 | Electron 31（独立 `desktop/` 项目） |

### 2.2 现有架构问题（重建的理由）

#### 问题 A：巨石组件

`Aelin.tsx` 达到 **1669 行**，集中承担：

- 所有聊天会话状态管理（sessions / messages / activeSession）
- Desk 面板开关控制
- 7+ 个子对话框的 open/close 状态
- SSE 流式逻辑
- 引用系统
- Handoff 动画
- Context 刷新
- Tracking sheet 逻辑

单组件管理 **15+ 个 `useState`**，任何改动都需要理解整个文件的上下文。

#### 问题 B：Prop Drilling 严重

子对话框（如 `AelinTrackingCenterDialog`）接收 **25+ 个 props**，没有使用 Context 或状态管理库。

#### 问题 C：Desk 面板是 Drawer 而非独立布局

Dashboard 作为右侧 `<Drawer>` 嵌入，无法与聊天并排查看。每次打开都覆盖聊天区，桌面端大屏未被充分利用。

#### 问题 D：路由系统严重欠缺

实际只有 `/`（Aelin）和 `/settings` 两个实体页，`/chat`、`/desk`、`/dashboard`、`/login` 全部加重定向。所有功能堆在首页。

#### 问题 E：缺少全局状态管理

无 Redux / Zustand / Jotai。全靠 `useState` + `useCallback`，状态散落各处。

#### 问题 F：API 层单体文件

`api.ts` 达到 **1346 行**，类型定义和请求函数混合，无领域拆分。

#### 问题 G：MUI 与品牌调性冲突

Aelin 的品牌是「暖白杂志感 + 衬线体 + 低饱和度」，与 Material Design 的几何/弹性/高彩度语言根本冲突。现有代码大量 override MUI 默认样式。

---

# 第二部分：设计哲学

## 3. 产品内核与设计原则

### 3.1 Aelin 是什么

Aelin 是一个 **信号原生的聊天代理（Signal-native Chat Agent）**：

- **普通 AI**：`query → fetch → answer`
- **Aelin**：`定义兴趣边界 → 持续采集 → 持久化 → 结构化时间线 → 带证据回答 → 更新长期记忆`

Aelin 不是冷冰冰的工具，而是有温度的个人信息伙伴 —— 拥有 11 种表情、情感化表达、中文优先的女性化角色。

### 3.2 五条设计原则

| 原则 | 含义 | 具体体现 |
|---|---|---|
| **Chat-first** | 对话是主交互面，一切从对话触发 | `/` 默认进入聊天、所有功能可通过对话访问 |
| **Evidence-first** | 每个回答可追溯到具体信号源 | Citation 卡片、源链接、message_id 跳转 |
| **Memory-first** | 记忆是持续积累的资产 | 三层记忆可视化、记忆笔记管理、焦点项排序 |
| **Tracking-first** | 长期追踪是一级产品功能 | 独立路由、变化流、快照对比、人性化通知 |
| **Warmth-first** | Aelin 有温度、有人格 | 11 种表情动态切换、情感化文案、编辑台式排版 |

### 3.3 审美方向：「温暖的证据编辑台（Editorial Evidence Desk）」

将 Aelin 的核心差异视觉化为一个「编辑台」：

- **答案** 像编辑稿，优先可读
- **证据** 像脚注与卡片，可随时翻证、回看上下文
- **追踪** 像持续更新的专题报道（变化流 + 快照对比）
- **整体** 像一个私人编辑部，温暖但专业

---

## 4. 视觉设计语言

### 4.1 色彩令牌体系

采用 **低饱和度暖调** 色系，区别于常见 SaaS 产品的高彩度倾向：

#### 基础色

| Token | Light 值 | Dark 值 | 语义 |
|---|---|---|---|
| `--color-bg` | `#faf9f5` | `#141413` | 页面背景 |
| `--color-bg-elevated` | `#f3f1e8` | `#1b1b19` | 悬浮/弹窗背景 |
| `--color-panel` | `#fffdf8` | `#1d1d1b` | 卡片/面板底色 |
| `--color-panel-alt` | `#f5f3ec` | `#232320` | 交替面板色 |
| `--color-text` | `#141413` | `#faf9f5` | 主文字 |
| `--color-text-muted` | `#7a786f` | `#b0aea5` | 次要文字 |
| `--color-border` | `#e8e6dc` | `#34332f` | 分割线/边框 |
| `--color-border-strong` | `#d0cec4` | `#4a4944` | 强调边框 |

#### 强调色

| Token | 值 | 语义 |
|---|---|---|
| `--color-accent` | `#111111` / `#f3f3f1` | 主强调（按钮、选中态） |
| `--color-accent-soft` | `#e8e6dc` / `#2a2a27` | 柔和强调（hover 背景） |
| `--color-orange` | `#d97757` | 追踪、确认、关键 CTA |
| `--color-blue` | `#6a9bcc` | 引用、外链、跳转 |
| `--color-green` | `#788c5d` | 成功、同步健康 |
| `--color-danger` | `#c45c5c` | 错误、危险操作 |
| `--color-warning` | `#d4a853` | 警告 |

### 4.2 字体系统

| 用途 | 字体栈 | 说明 |
|---|---|---|
| 标题 | `Poppins`, `Noto Sans SC`, `PingFang SC`, `Microsoft YaHei`, sans-serif | 无衬线，现代感 |
| 正文 | `Lora`, `Noto Serif SC`, `Songti SC`, `STSong`, serif | **衬线体**，编辑台/杂志感，高辨识度 |
| 代码 | `JetBrains Mono`, `IBM Plex Mono`, `Consolas`, monospace | 等宽，代码块与引用ID |

**排版参数**：

| 属性 | 值 |
|---|---|
| body1 字号 | `0.95rem` |
| body1 行高 | `1.62` |
| body2 字号 | `0.875rem` |
| body2 行高 | `1.56` |
| heading 字重 | `600` |
| 段落间距 | `1rem` |

### 4.3 形状与阴影

| 属性 | 值 |
|---|---|
| 通用圆角 | `10px` |
| 卡片圆角 | `12px` |
| Chip/Badge 圆角 | `999px`（胶囊） |
| 按钮最小高度 | `34px` |
| 按钮内边距 | `6px 14px` |
| Light 阴影 | `0 1px 3px rgba(20,20,19,0.06)` |
| Dark 阴影 | `0 1px 4px rgba(0,0,0,0.3)` |

### 4.4 动效策略

- **只在高价值时刻** 做动效：页面首屏进入、对话流式输出、引用卡展开、追踪变化到达、表情切换
- **禁止** 处处 bounce 的"动效噪音"
- **尊重** `prefers-reduced-motion` 媒体查询
- **工具**：framer-motion v12（保留，对表情系统和过渡动画至关重要）

---

# 第三部分：架构设计

## 5. 技术栈选型

| 类别 | 选型 | 理由 |
|---|---|---|
| **框架** | React 19 + TypeScript 5.7 | 生态最成熟，Capacitor/Electron 兼容性最好 |
| **构建** | Vite 6 | 快速 HMR，`dist/` 产物适配 Electron extraResources |
| **路由** | react-router v7 (Data Router) | 支持 loader/action 数据预取，嵌套路由 |
| **状态管理** | Zustand v5 | 轻量无 boilerplate，完美替代 useState 堆叠 |
| **数据请求** | TanStack Query v5 | 比 SWR 更强的缓存策略、mutation、乐观更新、stale-while-revalidate |
| **UI 基础** | Radix UI Primitives | 无样式原语 + 完全控制视觉层 + 内建无障碍 |
| **样式** | Tailwind CSS v4 + CSS 变量 | 快速开发 + 主题 token 系统契合 |
| **动画** | framer-motion v12 | 表情系统和过渡动画 |
| **Markdown** | react-markdown v10 + rehype-sanitize | 安全渲染 chat 回复 |
| **长列表** | @tanstack/react-virtual v3 | 消息/变化流虚拟化 |
| **表单** | React Hook Form + Zod | 类型安全验证 |
| **移动端** | Capacitor 6 | 已验证可行 |
| **桌面端** | Electron 31 | 已有成熟壳 |
| **测试** | Vitest + Testing Library + Playwright | 单元 + 集成 + E2E |

### 5.1 为何不继续用 MUI？

Aelin 的品牌调性是「暖白杂志感 + 衬线体 + 低饱和度」，与 Material Design 的设计语言根本冲突：

| 维度 | Material Design | Aelin 品牌 |
|---|---|---|
| 色彩 | 高彩度、主色强烈 | 低饱和度、暖灰调 |
| 字体 | Roboto（无衬线） | Lora（衬线）+ Poppins |
| 形状 | 几何、弹性、波纹效果 | 柔和、沉稳、编辑台感 |
| 间距 | Material spacing scale | 自定义紧凑/宽松模式 |

用 MUI 需要大量 override（现有前端已经在做），不如用 Radix + Tailwind 实现像素级控制。

### 5.2 为何 Zustand 而非 Redux / Jotai？

| 方案 | 优势 | 劣势 |
|---|---|---|
| useState (现状) | 零依赖 | 15+ state 变量，prop drilling 25+ props |
| Redux Toolkit | 成熟、DevTools | Boilerplate 重，对本项目规模过度 |
| Jotai | 原子化 | 学习曲线，不适合有明确领域边界的状态 |
| **Zustand** | 极简 API、中间件丰富、DevTools、无 Provider | — |

---

## 6. 工程目录结构

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── capacitor.config.ts
│
├── public/
│   ├── expressions/            # 11 个表情图 (exp-01.png ~ exp-11.png)
│   └── fonts/                  # Poppins / Lora / JetBrains Mono / Noto CJK
│
└── src/
    ├── main.tsx                # 入口：React 挂载 + 移动端 bootstrap
    │
    ├── app/                    # 应用层（路由 + 全局 Provider）
    │   ├── router.tsx          # 路由注册（BrowserRouter / HashRouter 双模式）
    │   ├── providers.tsx       # 全局 Provider 组合（Query + Zustand + Toast + Theme）
    │   └── routes/             # 路由页面组件
    │       ├── _layout.tsx     # 根布局（Sidebar + Main + ContextPanel）
    │       ├── index.tsx       # / → Aelin Chat
    │       ├── signals.tsx     # /signals → 信息聚合
    │       ├── signals.$contactId.tsx  # /signals/:contactId → 联系人线程
    │       ├── tracking.tsx    # /tracking → 追踪中心
    │       ├── tracking.$targetId.tsx  # /tracking/:targetId → 追踪详情
    │       └── settings/       # /settings 嵌套路由
    │           ├── _layout.tsx
    │           ├── profile.tsx
    │           ├── ai.tsx
    │           ├── accounts.tsx
    │           └── appearance.tsx
    │
    ├── features/               # 功能模块（领域驱动 Feature Slices）
    │   ├── chat/               # Aelin 对话
    │   │   ├── components/
    │   │   │   ├── ChatArea.tsx           # 消息列表区（虚拟化）
    │   │   │   ├── MessageBubble.tsx      # 单条消息（支持 citation/action/trace）
    │   │   │   ├── ComposerBar.tsx        # 输入框 + 图片上传 + 模式切换
    │   │   │   ├── ExpressionAvatar.tsx   # Aelin 表情头像（动态切换）
    │   │   │   ├── CitationCard.tsx       # 引用卡片
    │   │   │   ├── ActionChip.tsx         # 建议动作按钮
    │   │   │   ├── ToolTraceBar.tsx       # 工具调用进度追踪
    │   │   │   └── SessionTabs.tsx        # 多会话标签
    │   │   ├── hooks/
    │   │   │   ├── useChatStream.ts       # SSE 流式对话 hook
    │   │   │   ├── useChatSessions.ts     # 会话管理 hook
    │   │   │   └── useChatActions.ts      # 动作执行 hook
    │   │   ├── stores/
    │   │   │   └── chatStore.ts           # Zustand chat store
    │   │   └── types.ts
    │   │
    │   ├── context-panel/      # 右侧上下文面板
    │   │   ├── components/
    │   │   │   ├── ContextPanel.tsx       # 面板容器 + Tab 切换
    │   │   │   ├── MemoryTab.tsx          # 记忆分层视图
    │   │   │   ├── FocusTab.tsx           # 今日焦点
    │   │   │   ├── CitationsTab.tsx       # 引用证据栈
    │   │   │   └── NotificationsTab.tsx   # 通知 Tab
    │   │   └── hooks/
    │   │       └── useAelinContext.ts     # GET /aelin/context 数据 hook
    │   │
    │   ├── signals/            # 信息聚合
    │   │   ├── components/
    │   │   │   ├── ContactList.tsx        # 联系人列表（筛选/排序/未读）
    │   │   │   ├── ContactCard.tsx        # 联系人卡片
    │   │   │   ├── MessageThread.tsx      # 消息线程
    │   │   │   ├── MessageItem.tsx        # 单条消息 + 快捷操作
    │   │   │   └── SignalsFilter.tsx      # 过滤控件
    │   │   ├── hooks/
    │   │   │   ├── useContacts.ts
    │   │   │   └── useMessages.ts
    │   │   └── stores/
    │   │       └── signalsStore.ts
    │   │
    │   ├── tracking/           # 追踪系统
    │   │   ├── components/
    │   │   │   ├── TrackingList.tsx       # 目标列表 + 过滤
    │   │   │   ├── TrackingCard.tsx       # 追踪目标卡片
    │   │   │   ├── ChangeTimeline.tsx     # 变化时间线
    │   │   │   ├── ChangeItem.tsx         # 单条变化
    │   │   │   ├── SnapshotDiff.tsx       # 快照差异对比
    │   │   │   ├── TrackingConfig.tsx     # 追踪目标配置编辑
    │   │   │   └── TrackConfirmSheet.tsx  # 追踪确认底部弹窗
    │   │   ├── hooks/
    │   │   │   ├── useTrackingTargets.ts
    │   │   │   ├── useTrackingChanges.ts
    │   │   │   └── useTrackingSnapshots.ts
    │   │   └── stores/
    │   │       └── trackingStore.ts
    │   │
    │   ├── memory/             # 记忆系统
    │   │   ├── components/
    │   │   │   ├── MemoryExplorer.tsx     # 记忆浏览器
    │   │   │   ├── NoteList.tsx           # 笔记列表
    │   │   │   ├── LayerView.tsx          # 分层视图（facts/preferences/in_progress）
    │   │   │   └── DailyBrief.tsx         # 每日简报
    │   │   └── hooks/
    │   │       └── useAgentMemory.ts
    │   │
    │   ├── device/             # 设备中心
    │   │   ├── components/
    │   │   │   ├── DeviceDialog.tsx       # 设备中心弹窗
    │   │   │   ├── ProcessTable.tsx       # 进程表
    │   │   │   ├── ModeSelector.tsx       # 系统模式切换
    │   │   │   └── CapabilitiesInfo.tsx   # 能力检测
    │   │   └── hooks/
    │   │       └── useDeviceCenter.ts
    │   │
    │   ├── accounts/           # 数据源管理
    │   │   ├── components/
    │   │   │   ├── AccountList.tsx        # 已连接账户列表
    │   │   │   ├── ConnectWizard.tsx      # 连接向导
    │   │   │   ├── OAuthFlow.tsx          # OAuth 弹窗流程
    │   │   │   ├── SyncStatus.tsx         # 同步状态
    │   │   │   └── ForwardInfo.tsx        # 转发地址展示
    │   │   └── hooks/
    │   │       └── useAccounts.ts
    │   │
    │   ├── notifications/      # 通知中心
    │   │   ├── components/
    │   │   │   ├── NotificationDrawer.tsx # 通知抽屉
    │   │   │   ├── NotificationItem.tsx   # 通知项
    │   │   │   └── ProactiveBadge.tsx     # 主动推送角标
    │   │   └── hooks/
    │   │       └── useNotifications.ts
    │   │
    │   ├── todos/              # 待办事项
    │   │   ├── components/
    │   │   │   ├── TodoList.tsx
    │   │   │   └── TodoItem.tsx
    │   │   └── hooks/
    │   │       └── useTodos.ts
    │   │
    │   └── auth/               # 认证
    │       ├── components/
    │       │   └── LoginGuard.tsx
    │       └── hooks/
    │           └── useAuth.ts
    │
    ├── shared/                 # 共享层
    │   ├── components/         # 通用 UI 组件（基于 Radix primitives）
    │   │   ├── Button.tsx
    │   │   ├── Dialog.tsx
    │   │   ├── Drawer.tsx
    │   │   ├── Card.tsx
    │   │   ├── Avatar.tsx
    │   │   ├── Badge.tsx
    │   │   ├── Input.tsx
    │   │   ├── Select.tsx
    │   │   ├── Tabs.tsx
    │   │   ├── Tooltip.tsx
    │   │   ├── Toast.tsx
    │   │   ├── Skeleton.tsx
    │   │   ├── ConfirmDialog.tsx
    │   │   └── EmptyState.tsx
    │   │
    │   ├── api/                # API 客户端（按领域拆分）
    │   │   ├── client.ts       # fetch 基础配置 + 拦截器
    │   │   ├── sse.ts          # SSE 流式连接封装
    │   │   ├── auth.ts         # 认证相关 API
    │   │   ├── accounts.ts     # 数据源管理 API
    │   │   ├── contacts.ts     # 联系人/消息 API
    │   │   ├── aelin.ts        # Aelin chat/context API
    │   │   ├── tracking.ts     # 追踪系统 API
    │   │   ├── agent.ts        # Agent 辅助功能 API
    │   │   ├── device.ts       # 设备中心 API
    │   │   └── types.ts        # 共享类型定义（从后端 schemas 推导）
    │   │
    │   ├── design-tokens/      # 设计令牌
    │   │   ├── colors.ts       # 色彩 token 导出
    │   │   ├── typography.ts   # 字体 token
    │   │   └── spacing.ts      # 间距/圆角 token
    │   │
    │   ├── hooks/              # 通用 hooks
    │   │   ├── useMediaQuery.ts
    │   │   ├── usePlatform.ts  # Web/Electron/Capacitor 检测
    │   │   ├── useDebounce.ts
    │   │   ├── useConfirmDialog.ts
    │   │   └── useTheme.ts
    │   │
    │   └── utils/
    │       ├── format.ts       # 日期/数字格式化
    │       ├── markdown.ts     # Markdown 处理工具
    │       └── oauth-popup.ts  # OAuth 弹窗工具
    │
    ├── styles/
    │   ├── tokens.css          # CSS 变量定义（双主题）
    │   └── globals.css         # 全局样式 + Tailwind 指令
    │
    └── mobile/
        └── runtime.ts          # Capacitor 原生平台检测 & bootstrap
```

### 6.1 设计原则

- **Feature-first**：按功能域（chat / signals / tracking …）组织，每个 feature 自包含组件、hooks、store
- **单文件 ≤300 行**：严格控制组件体积，超过即拆分
- **API 按领域拆分**：`shared/api/` 下每个文件对应一个后端路由模块，避免 1346 行单体
- **共享组件无业务逻辑**：`shared/components/` 只做通用 UI，不包含任何 API 调用

---

## 7. 状态管理架构

### 7.1 三层状态模型

```
┌─────────────────────────────────────────────────────────────┐
│                    Server State                              │
│            (TanStack Query — 服务端数据缓存)                  │
│                                                              │
│  • contacts / messages / tracking targets / changes          │
│  • aelin context / notifications / daily brief               │
│  • agent config / model catalog                              │
│  • 特性：stale-while-revalidate、背景刷新、乐观更新            │
└─────────────────────────────────────────────────────────────┘
                             ↕
┌─────────────────────────────────────────────────────────────┐
│                   Client State                               │
│              (Zustand — 客户端 UI 状态)                       │
│                                                              │
│  • chatStore: sessions, activeSessionId, isStreaming          │
│  • signalsStore: selectedContactId, filterState              │
│  • trackingStore: selectedTargetId, filterState              │
│  • themeStore: mode (light/dark/system), density             │
│  • layoutStore: sidebarCollapsed, contextPanelOpen           │
│  • 特性：persist 中间件（localStorage）、DevTools              │
└─────────────────────────────────────────────────────────────┘
                             ↕
┌─────────────────────────────────────────────────────────────┐
│                   Local State                                │
│           (useState / useRef — 组件局部状态)                   │
│                                                              │
│  • dialog open/close、input value、hover state               │
│  • scroll position、animation state                          │
│  • 原则：只在单组件内使用，不需要跨组件共享的状态                  │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Store 示例：chatStore

```typescript
// features/chat/stores/chatStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  workspace: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  expression?: string          // exp-01 ~ exp-11
  citations?: AelinCitation[]
  actions?: AelinAction[]
  toolTrace?: AelinToolStep[]
  memorySummary?: string
  images?: { dataUrl: string; name: string }[]
  timestamp: number
}

interface ChatStore {
  // State
  sessions: ChatSession[]
  activeSessionId: string | null
  isStreaming: boolean
  pendingTrackConfirm: AelinAction | null

  // Computed
  activeSession: () => ChatSession | undefined

  // Actions
  createSession: (workspace?: string) => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateLastMessage: (sessionId: string, partial: Partial<ChatMessage>) => void
  setStreaming: (v: boolean) => void
  setPendingTrackConfirm: (action: AelinAction | null) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isStreaming: false,
      pendingTrackConfirm: null,

      activeSession: () => {
        const { sessions, activeSessionId } = get()
        return sessions.find(s => s.id === activeSessionId)
      },

      createSession: (workspace = 'default') => {
        const id = crypto.randomUUID()
        set(state => ({
          sessions: [
            { id, title: '新对话', messages: [], createdAt: Date.now(), workspace },
            ...state.sessions,
          ],
          activeSessionId: id,
        }))
        return id
      },

      switchSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) => set(state => ({
        sessions: state.sessions.filter(s => s.id !== id),
        activeSessionId: state.activeSessionId === id
          ? state.sessions.find(s => s.id !== id)?.id ?? null
          : state.activeSessionId,
      })),

      addMessage: (sessionId, msg) => set(state => ({
        sessions: state.sessions.map(s =>
          s.id === sessionId
            ? { ...s, messages: [...s.messages, msg] }
            : s
        ),
      })),

      updateLastMessage: (sessionId, partial) => set(state => ({
        sessions: state.sessions.map(s =>
          s.id === sessionId
            ? {
                ...s,
                messages: s.messages.map((m, i) =>
                  i === s.messages.length - 1 ? { ...m, ...partial } : m
                ),
              }
            : s
        ),
      })),

      setStreaming: (v) => set({ isStreaming: v }),
      setPendingTrackConfirm: (action) => set({ pendingTrackConfirm: action }),
    }),
    { name: 'aelin-chat-sessions' }
  )
)
```

### 7.3 跨 Feature 通信

```typescript
// 追踪变化 → 通知角标更新（Zustand subscribeWithSelector）
import { useTrackingStore } from '@/features/tracking/stores/trackingStore'
import { useNotificationStore } from '@/features/notifications/stores/notificationStore'

// 在 app 初始化时订阅
useTrackingStore.subscribe(
  state => state.unreadCount,
  (unread) => useNotificationStore.getState().setTrackingBadge(unread)
)
```

---

## 8. API 对接层设计

### 8.1 基础客户端

```typescript
// shared/api/client.ts
const BASE_URL = import.meta.env.VITE_API_BASE || ''

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function fetchJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const token = localStorage.getItem('token')
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail || res.statusText)
  }
  return res.json()
}
```

### 8.2 SSE 流式封装

```typescript
// shared/api/sse.ts
import type { AelinChatRequest, AelinCitation, AelinAction, AelinToolStep } from './types'

interface StreamCallbacks {
  onIntent?: (data: { intent_type: string; time_sensitivity: string }) => void
  onPlan?: (data: { steps: string[] }) => void
  onToolStep?: (step: AelinToolStep) => void
  onCitations?: (citations: AelinCitation[]) => void
  onActions?: (actions: AelinAction[]) => void
  onReplyChunk?: (text: string) => void
  onDone?: (data: { expression: string; memory_summary: string }) => void
  onError?: (error: { message: string; code?: string }) => void
}

export function streamChat(
  body: AelinChatRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): () => void {
  const controller = new AbortController()
  const combinedSignal = signal
    ? AbortSignal.any([signal, controller.signal])
    : controller.signal

  const token = localStorage.getItem('token')
  const BASE_URL = import.meta.env.VITE_API_BASE || ''

  fetch(`${BASE_URL}/api/v1/aelin/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: combinedSignal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw || raw === '[DONE]') continue

          try {
            const evt = JSON.parse(raw)
            const type = evt.type || evt.event
            switch (type) {
              case 'intent':    callbacks.onIntent?.(evt.data ?? evt); break
              case 'plan':      callbacks.onPlan?.(evt.data ?? evt); break
              case 'tool_step': callbacks.onToolStep?.(evt.data ?? evt); break
              case 'citations': callbacks.onCitations?.(evt.data ?? evt); break
              case 'actions':   callbacks.onActions?.(evt.data ?? evt); break
              case 'reply':     callbacks.onReplyChunk?.(evt.data?.chunk ?? evt.chunk ?? ''); break
              case 'done':      callbacks.onDone?.(evt.data ?? evt); break
              case 'error':     callbacks.onError?.(evt.data ?? evt); break
            }
          } catch { /* skip malformed */ }
        }
      }
    })
    .catch((err) => {
      if (!combinedSignal.aborted) {
        callbacks.onError?.({ message: err.message })
      }
    })

  return () => controller.abort()
}
```

### 8.3 按领域拆分示例

```typescript
// shared/api/tracking.ts
import { fetchJson } from './client'
import type {
  AelinTrackingListResponse,
  AelinTrackingChangeListResponse,
  AelinTrackingSnapshotListResponse,
  AelinTrackConfirmRequest,
  AelinTrackConfirmResponse,
  AelinTrackingTargetUpdateRequest,
  AelinTrackingItem,
  AelinTrackingRunResponse,
} from './types'

export const trackingApi = {
  list: (params?: Record<string, string>) =>
    fetchJson<AelinTrackingListResponse>(
      `/api/v1/aelin/tracking${params ? '?' + new URLSearchParams(params) : ''}`
    ),

  updateTarget: (targetId: number, body: AelinTrackingTargetUpdateRequest) =>
    fetchJson<AelinTrackingItem>(`/api/v1/aelin/tracking/targets/${targetId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  runTarget: (targetId: number) =>
    fetchJson<AelinTrackingRunResponse>(
      `/api/v1/aelin/tracking/targets/${targetId}/run`,
      { method: 'POST' }
    ),

  getChanges: (targetId: number, params?: Record<string, string>) =>
    fetchJson<AelinTrackingChangeListResponse>(
      `/api/v1/aelin/tracking/targets/${targetId}/changes${params ? '?' + new URLSearchParams(params) : ''}`
    ),

  ackChange: (changeId: number) =>
    fetchJson<void>(
      `/api/v1/aelin/tracking/changes/${changeId}/ack`,
      { method: 'POST' }
    ),

  getSnapshots: (targetId: number, params?: Record<string, string>) =>
    fetchJson<AelinTrackingSnapshotListResponse>(
      `/api/v1/aelin/tracking/targets/${targetId}/snapshots${params ? '?' + new URLSearchParams(params) : ''}`
    ),

  searchFileMemory: (params: Record<string, string>) =>
    fetchJson(`/api/v1/aelin/tracking/file-memory/search?${new URLSearchParams(params)}`),

  confirm: (body: AelinTrackConfirmRequest) =>
    fetchJson<AelinTrackConfirmResponse>('/api/v1/aelin/track/confirm', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
```

### 8.4 TanStack Query Hooks 示例

```typescript
// features/tracking/hooks/useTrackingTargets.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { trackingApi } from '@/shared/api/tracking'

export function useTrackingTargets(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['tracking', 'targets', params],
    queryFn: () => trackingApi.list(params),
    refetchInterval: 30_000,  // 30 秒自动刷新
  })
}

export function useTrackingChanges(targetId: number, params?: Record<string, string>) {
  return useQuery({
    queryKey: ['tracking', 'changes', targetId, params],
    queryFn: () => trackingApi.getChanges(targetId, params),
    enabled: !!targetId,
  })
}

export function useRunTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (targetId: number) => trackingApi.runTarget(targetId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tracking'] }),
  })
}

export function useAckChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (changeId: number) => trackingApi.ackChange(changeId),
    onSuccess: (_data, changeId) => {
      // 乐观更新：立即从列表中标记为已确认
      qc.invalidateQueries({ queryKey: ['tracking', 'changes'] })
    },
  })
}
```

---

# 第四部分：信息架构与布局

## 9. 路由与导航体系

### 9.1 路由表

| 路径 | 组件 | 导航定位 | 说明 |
|---|---|---|---|
| `/` | AelinChat | 主导航 Tab 1 | 默认入口，Chat-first |
| `/signals` | Signals | 主导航 Tab 2 | 信息聚合面板 |
| `/signals/:contactId` | SignalThread | — | 联系人消息线程 |
| `/tracking` | Tracking | 主导航 Tab 3 | 追踪中心 |
| `/tracking/:targetId` | TrackingDetail | — | 追踪目标详情 |
| `/settings` | SettingsLayout | 主导航 Tab 4 | 配置入口 |
| `/settings/profile` | ProfileSection | Settings 子路由 | 个人资料 |
| `/settings/ai` | AiSection | Settings 子路由 | AI Provider 配置 |
| `/settings/accounts` | AccountsSection | Settings 子路由 | 数据源管理 |
| `/settings/appearance` | AppearanceSection | Settings 子路由 | 外观与密度 |
| `*` | NotFound | — | 404 页面 |

**兼容性别名**（重定向）:

| 旧路径 | 重定向目标 |
|---|---|
| `/chat` | `/` |
| `/desk` | `/signals` |
| `/dashboard` | `/signals` |

### 9.2 导航元素

```
桌面端: 左侧 Navigation Rail（64px 宽）
  ┌────┐
  │ 🏠 │  Chat (/)
  │ 📨 │  Signals (/signals)    [未读角标]
  │ 📡 │  Tracking (/tracking)  [变化角标]
  │    │
  │    │  ← 弹性空间
  │    │
  │ 🔔 │  Notifications (Drawer)
  │ ⚙️ │  Settings (/settings)
  └────┘

移动端: 底部 Tab Bar
  ┌──────┬──────┬──────┬──────┐
  │ Chat │Sgnls │Track │ More │
  └──────┴──────┴──────┴──────┘
  「More」展开: Settings / Notifications / Device
```

---

## 10. 响应式布局系统

### 10.1 三档断点

| 断点 | 宽度 | 布局模式 | 导航 |
|---|---|---|---|
| Desktop | ≥ 1280px | 三栏 | 左侧 Rail |
| Tablet | 768–1279px | 两栏 | 左侧 Rail（紧凑） |
| Mobile | < 768px | 单栏 | 底部 Tab |

### 10.2 布局结构图

#### Desktop（≥ 1280px）— 三栏

```
┌───────┬───────────────────────────┬─────────────────────┐
│       │                           │                     │
│  Nav  │      Main Content         │   Context Panel     │
│  Rail │                           │                     │
│       │  Chat / Signals /         │  Memory / Focus /   │
│ 64px  │  Tracking / Settings      │  Citations / Notif  │
│       │                           │                     │
│       │        flex-1             │      380px          │
│       │                           │    (可折叠)          │
└───────┴───────────────────────────┴─────────────────────┘
```

#### Tablet（768–1279px）— 两栏

```
┌───────┬─────────────────────────────────────────────────┐
│       │                                                 │
│  Nav  │           Main Content                          │
│  Rail │                                                 │
│ 56px  │   Chat / Signals / Tracking / Settings          │
│       │                                                 │
│       │   Context Panel 变为 Overlay Drawer              │
│       │                                                 │
└───────┴─────────────────────────────────────────────────┘
```

#### Mobile（< 768px）— 单栏 + 底部 Tab

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│              Main Content（全屏）                        │
│                                                         │
│    Chat / Signals / Tracking / Settings                 │
│                                                         │
│    Context Panel 变为全屏页 / Bottom Sheet                │
│                                                         │
├─────────────────────────────────────────────────────────┤
│   💬 Chat  │  📨 Signals  │  📡 Track  │  ⋯ More      │
└─────────────────────────────────────────────────────────┘
```

### 10.3 Layout 组件实现思路

```tsx
// app/routes/_layout.tsx
import { Outlet } from 'react-router-dom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { NavigationRail } from './NavigationRail'
import { BottomTabBar } from './BottomTabBar'
import { ContextPanel } from '@/features/context-panel/components/ContextPanel'
import { Drawer } from '@/shared/components/Drawer'

export function RootLayout() {
  const isDesktop = useMediaQuery('(min-width: 1280px)')
  const isTablet = useMediaQuery('(min-width: 768px)')
  const isMobile = !isTablet
  const { contextPanelOpen, toggleContextPanel } = useLayoutStore()

  return (
    <div className="flex h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      {/* 左侧导航 */}
      {isTablet && <NavigationRail compact={!isDesktop} />}

      {/* 主内容区 */}
      <main className="flex-1 min-w-0 overflow-hidden">
        <Outlet />
      </main>

      {/* 右侧 Context Panel */}
      {isDesktop && contextPanelOpen ? (
        <aside className="w-[380px] border-l border-[var(--color-border)] overflow-y-auto">
          <ContextPanel />
        </aside>
      ) : (
        <Drawer
          open={contextPanelOpen && !isDesktop}
          onClose={toggleContextPanel}
          anchor="right"
          width={380}
        >
          <ContextPanel />
        </Drawer>
      )}

      {/* 移动端底部 Tab */}
      {isMobile && <BottomTabBar />}
    </div>
  )
}
```

---

# 第五部分：核心页面交互设计

## 11. Aelin Chat — 主对话区

### 11.1 整体结构

```
┌─ Aelin Chat ─────────────────────────────────────────────┐
│                                                           │
│  ┌─ Session Tabs ──────────────────────────────────────┐  │
│  │  ● 新对话  │  "追踪 Next.js 更新"  │  "B站动态"  │ + │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─ Aelin Header ──────────────────────────────────────┐  │
│  │  [exp-04 表情图]                                     │  │
│  │  Aelin · 正在思考…                                   │  │
│  │  搜索模式: [Auto ▾]  [Local] [Web]                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─ Message Stream (虚拟化滚动) ───────────────────────┐  │
│  │                                                      │  │
│  │  ╭─ User ─────────────────────────────────────────╮  │  │
│  │  │ 最近 B站有什么值得关注的 AI 相关动态？           │  │  │
│  │  │ [图片缩略图]                                    │  │  │
│  │  ╰────────────────────────────────────────────────╯  │  │
│  │                                                      │  │
│  │  ╭─ Aelin [exp-02 热情] ──────────────────────────╮  │  │
│  │  │                                                 │  │  │
│  │  │  我帮你搜了一下！最近有几个值得关注的动态：      │  │  │
│  │  │                                                 │  │  │
│  │  │  1. **xxx** 发布了关于 …… [1]                   │  │  │
│  │  │  2. **yyy** 的新视频 …… [2]                     │  │  │
│  │  │                                                 │  │  │
│  │  │  ┌─ 引用 ────────────────────────────────────┐  │  │  │
│  │  │  │ [1] 📺 xxx · B站 · 2h ago · ★ 8.2        │  │  │  │
│  │  │  │ [2] 📺 yyy · B站 · 5h ago · ★ 7.1        │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  │                                                 │  │  │
│  │  │  ──── 工具追踪 ────────────────────── ▸ 展开    │  │  │
│  │  │  ✓ 搜索本地消息 (3条) · ✓ 网络搜索 (5结果)     │  │  │
│  │  │                                                 │  │  │
│  │  │  ┌─ 建议操作 ────────────────────────────────┐  │  │  │
│  │  │  │ [🔔 追踪此话题]  [📖 查看原文]  [📋 待办]  │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  │                                                 │  │  │
│  │  ╰─────────────────────────────────────────────────╯  │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─ Composer ──────────────────────────────────────────┐  │
│  │  [📷]  [📎]  输入消息，按 Enter 发送…    [Send ▸]   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 11.2 关键交互细节

#### 流式输出（SSE）处理流程

1. 用户发送消息 → 创建 user bubble + 空 assistant bubble
2. 收到 `intent` 事件 → 更新 Aelin 状态文案（"正在理解你的意图…"）
3. 收到 `plan` 事件 → 更新状态（"正在搜索…"）
4. 收到 `tool_step` 事件 → ToolTraceBar 追加进度条
5. 收到 `citations` 事件 → 预填充引用区
6. 收到 `reply` 事件（文本 chunk）→ 逐字追加到 assistant bubble
7. 收到 `actions` 事件 → 渲染建议操作按钮
8. 收到 `done` 事件 → 设置 expression + memorySummary
9. 收到 `error` 事件 → 显示错误提示 + 重试按钮

#### 表情系统动画

```
收到 done.expression = "exp-02"
  → ExpressionAvatar 从当前表情过渡到 exp-02
  → 使用 framer-motion AnimatePresence 做 crossfade (300ms)
  → 同时更新状态文案（从表情映射表获取描述）
```

#### 引用卡片交互

- **悬停**：显示消息预览气泡
- **点击**：右侧 Context Panel 切换到 Citations Tab 并高亮该引用
- **"在 Signals 中查看"**：导航到 `/signals/:contactId?highlight=messageId`
- **外部链接**：新标签打开

#### 多会话管理

- Session Tabs 水平滚动，最新在最左
- 每个 Session 持久化到 localStorage（通过 Zustand persist middleware）
- 支持重命名、删除、搜索历史会话

### 11.3 Composer 详细设计

| 功能 | 交互 |
|---|---|
| 文本输入 | 自动增高 textarea，最大 6 行 |
| 发送 | Enter 发送，Shift+Enter 换行 |
| 图片 | 📷 按钮或粘贴，最多 4 张，显示缩略预览条 |
| 搜索模式 | Auto / Local / Web 三选一，映射到 `search_mode` 字段 |
| 快捷指令 | 输入 `/` 触发命令面板（`/track`、`/todo`、`/brief`…） |

---

## 12. Context Panel — 右侧上下文面板

### 12.1 四个 Tab

```
┌─ Context Panel ──────────────────────────────────────────┐
│                                                           │
│  [记忆]  [焦点]  [引用]  [通知]                            │
│  ══════════════════════════════════════════                │
│                                                           │
│  ┌─ 记忆 Tab ─────────────────────────────────────────┐  │
│  │                                                     │  │
│  │  ┌─ 摘要 ────────────────────────────────────────┐  │  │
│  │  │ "用户关注 AI 开源项目、B站技术UP主、Next.js…"   │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │                                                     │  │
│  │  ┌─ 记忆分层 ─────────────────────────────────────┐  │  │
│  │  │ Facts (3)                                       │  │  │
│  │  │  · 用户偏好深色模式 (conf: 0.9)                 │  │  │
│  │  │  · 使用 Mac + Windows 双系统                    │  │  │
│  │  │                                                 │  │  │
│  │  │ Preferences (5)                                 │  │  │
│  │  │  · 关注 AI 开源项目                             │  │  │
│  │  │  · 偏好简洁风回复                               │  │  │
│  │  │                                                 │  │  │
│  │  │ In Progress (2)                                 │  │  │
│  │  │  · 正在准备毕业论文                             │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │                                                     │  │
│  │  ┌─ 笔记 (手动) ──────────────────────── [+ 添加]  │  │
│  │  │  📝 "关注 xxx 的 GitHub 仓库"          [🗑]      │  │  │
│  │  │  📝 "周五前提交报告"                   [🗑]      │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │                                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 12.2 数据来源

| Tab | 数据端点 | 刷新策略 |
|---|---|---|
| 记忆 | `GET /aelin/context` → `summary`, `notes`, `memory_layers` | 每次对话后 + 30s 轮询 |
| 焦点 | `GET /aelin/context` → `focus_items`, `daily_brief`, `todos` | 每次对话后 + 60s 轮询 |
| 引用 | 来自最近 chat response 的 `citations[]` | 对话触发 |
| 通知 | `GET /aelin/proactive/poll` | 15s 轮询 |

---

## 13. Signals — 信息聚合面板

### 13.1 布局

```
┌─ /signals ─────────────────────────────────────────────────┐
│                                                             │
│  ┌─ Filter Bar ─────────────────────────────────────────┐  │
│  │  🔍 搜索联系人…   [全部 ▾] [未读 ○] [来源: All ▾]    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Contact List ─────┬─ Message Thread ────────────────┐  │
│  │                     │                                 │  │
│  │ ┌───────────────┐  │  ┌─ Thread Header ──────────┐   │  │
│  │ │ 📺 UP主-A      │  │  │  UP主-A · bilibili       │   │  │
│  │ │ 3 unread       │  │  │  [标记已读] [全部总结]    │   │  │
│  │ │ "新视频: AI…"  │  │  └──────────────────────────┘   │  │
│  │ │ 2h ago         │  │                                 │  │
│  │ ├───────────────┤  │  Message 1                       │  │
│  │ │ ✉️ john@…      │  │  ├─ subject: "AI 前沿速递"      │  │
│  │ │ 0 unread       │  │  ├─ preview: "本期推荐…"        │  │
│  │ │ "Re: 会议…"   │  │  ├─ [总结] [待办] [追踪]        │  │
│  │ │ 1d ago         │  │  │                              │  │
│  │ ├───────────────┤  │  Message 2                       │  │
│  │ │ 🐙 github/…   │  │  ├─ subject: "Issue #42…"       │  │
│  │ │ 1 unread       │  │  ├─ …                           │  │
│  │ │ "Issue: bug…" │  │                                 │  │
│  │ └───────────────┘  │                                 │  │
│  │                     │  [加载更多 ▾]                    │  │
│  └─────────────────────┴─────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 联系人卡片信息

来自 `GET /api/v1/contacts` 的 `ContactOut`：

| 字段 | 展示 |
|---|---|
| `display_name` | 主标题 |
| `handle` | 副标题（邮箱/用户名） |
| `avatar_url` | 头像 |
| `unread_count` | 未读角标 |
| `latest_subject` | 最新消息主题 |
| `latest_preview` | 预览文本（截断） |
| `latest_source` | 来源图标（bilibili/github/email…） |
| `latest_received_at` | 时间戳（相对时间） |

### 13.3 消息快捷操作

| 操作 | 调用 |
|---|---|
| 📝 总结 | `POST /agent/summarize` → 显示摘要气泡 |
| ☑️ 创建待办 | `POST /agent/todos` → 弹窗确认 |
| 🔔 创建追踪 | `POST /aelin/track/confirm` → TrackConfirmSheet |
| 📋 复制引用 | 格式化为 citation 文本复制到剪贴板 |

---

## 14. Tracking — 持续追踪中心

### 14.1 列表页

```
┌─ /tracking ────────────────────────────────────────────────┐
│                                                             │
│  ┌─ Header ─────────────────────────────────────────────┐  │
│  │  追踪中心                          [+ 新建追踪]       │  │
│  ├──────────────────────────────────────────────────────┘  │
│  │  [全部] [活跃 ●] [暂停 ◐] [异常 ⚠]     🔍 搜索…       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Tracking Cards ─────────────────────────────────────┐  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  📡 "Next.js Releases"                          │  │  │
│  │  │  web · active · ⏰ 每 2min                      │  │  │
│  │  │  🔴 3 个未读变化                                 │  │  │
│  │  │  最后检查: 5min ago · 下次: 1min 后              │  │  │
│  │  │  [查看变化] [立即运行] [⋮ 更多]                   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  📺 "某UP主"                                    │  │  │
│  │  │  bilibili · active · ⏰ 每 5min                 │  │  │
│  │  │  ✓ 无新变化                                     │  │  │
│  │  │  最后检查: 2min ago                              │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  🐙 "repo/xxx"                                  │  │  │
│  │  │  github · paused                                │  │  │
│  │  │  [恢复追踪]                                      │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 14.2 详情页

```
┌─ /tracking/:targetId ──────────────────────────────────────┐
│                                                             │
│  ┌─ Target Header ──────────────────────────────────────┐  │
│  │  ← 返回列表                                          │  │
│  │  📡 "Next.js Releases"                               │  │
│  │  web · active · 标签: [前端] [框架]                   │  │
│  │  [暂停] [立即运行] [编辑] [删除]                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  [变化流]  [快照历史]  [设置]                                │
│  ══════════════════════════════════════════                  │
│                                                             │
│  ┌─ 变化流 Tab ─────────────────────────────────────────┐  │
│  │  过滤: [全部] [🔴 high] [🟡 medium] [🟢 low]         │  │
│  │        [未确认 ◯] [已确认 ✓]                          │  │
│  │                                                       │  │
│  │  ── 2h ago ──────────────────────────────────────     │  │
│  │  🔴 HIGH · updated_item                               │  │
│  │  "Next.js 15.2 发布"                                  │  │
│  │  新增: App Router 性能优化、Turbopack 稳定版…         │  │
│  │  [✓ 确认]  [查看差异]  [在 Signals 中查看]            │  │
│  │                                                       │  │
│  │  ── 5h ago ──────────────────────────────────────     │  │
│  │  🟡 MEDIUM · new_item                                 │  │
│  │  "新 RFC: Server Actions v2"                          │  │
│  │  [✓ 确认]                                             │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 快照历史 Tab ───────────────────────────────────────┐  │
│  │  ┌─ 快照 #42 ── 2h ago ── ok ──────────────────┐     │  │
│  │  │  content_hash: a3f2…                          │     │  │
│  │  │  [查看内容]  [与 #41 对比]                     │     │  │
│  │  └───────────────────────────────────────────────┘     │  │
│  │                                                       │  │
│  │  ┌─ Diff 视图（选中两个快照时展开）──────────────────┐  │  │
│  │  │  - "Next.js v15.1 released"                      │  │  │
│  │  │  + "Next.js v15.2 released"                      │  │  │
│  │  │    Performance improvements...                    │  │  │
│  │  │  + "Turbopack is now stable"                     │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 设置 Tab ──────────────────────────────────────────┐  │
│  │  检查间隔: [120s ▾]                                   │  │
│  │  通知级别: [all ▾]                                    │  │
│  │  静默至: [不设置]                                     │  │
│  │  描述: [可编辑文本框]                                  │  │
│  │  标签: [前端] [框架] [+ 添加]                         │  │
│  │  [保存修改]                                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 14.3 TrackConfirmSheet（从 Chat 触发）

当对话中的 action 建议"创建追踪"时，弹出底部确认表单：

| 字段 | 来自 | 可编辑？ |
|---|---|---|
| `target` | Chat action payload | ✓ |
| `source` | 自动推断（web/bilibili/github…） | ✓ |
| `description` | Chat 上下文自动生成 | ✓ |
| `interval_seconds` | 默认 120 | ✓（30s ~ 24h） |
| `notify_level` | 默认 `all` | ✓（all/important/critical） |
| `is_temporary` | 默认 false | ✓ |
| `tags` | 空 | ✓ |

确认后调用 `POST /aelin/track/confirm`，成功后显示 Toast 并刷新追踪列表。

---

## 15. Settings — 配置与健康面板

### 15.1 布局

```
┌─ /settings ────────────────────────────────────────────────┐
│                                                             │
│  ┌─ Settings Nav ──┬─ Section Content ──────────────────┐  │
│  │                  │                                    │  │
│  │  👤 个人资料     │   (当前选中的设置区域内容)           │  │
│  │  🤖 AI 配置     │                                    │  │
│  │  📡 数据源      │                                    │  │
│  │  🎨 外观        │                                    │  │
│  │                  │                                    │  │
│  └──────────────────┴────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 15.2 各 Section 主要内容

#### Profile（个人资料）

- 头像上传（POST /me/avatar，≤5MB）
- 邮箱修改
- 密码修改

#### AI 配置

- Provider 选择（从 GET /agent/catalog 获取列表）
- Model 选择（按 provider 筛选）
- Base URL 自定义
- API Key 输入（密码模式）
- Temperature 滑块（0-2）
- [保存] + [测试连接] 按钮
- 连接状态指示器（✅ 正常 / ❌ 失败 + 错误详情）

#### 数据源管理

- 已连接账户列表（provider 图标 + 标识 + 最后同步时间 + 状态）
- 每个账户：[同步] [删除] 操作
- Forward 账户额外显示转发地址（可复制）
- 添加新数据源网格（12 个 provider 图标按钮）
- OAuth 流程：popup 弹窗 → 授权 → postMessage 回调 → 自动刷新列表

#### 外观

- 主题切换：Light / Dark / 跟随系统
- 信息密度：标准 / 紧凑（调整间距和字号）

---

## 16. Notifications — 通知中心

### 16.1 触发入口

- Navigation Rail / Bottom Tab 上的 🔔 图标
- 未读通知时显示红色角标（数字）
- 点击打开 Drawer（桌面端）/ 全屏页面（移动端）

### 16.2 通知项结构

```
┌─ Notification Item ─────────────────────────────────────┐
│  🔴 [追踪变化]                              5 min ago   │
│  "Next.js Releases" 检测到 2 个新变化                    │
│                                                          │
│  [查看详情 →]  [确认]                                    │
└──────────────────────────────────────────────────────────┘
```

| 字段 | 来源 |
|---|---|
| `level` | info / warning / critical → 图标颜色 |
| `title` | 通知标题 |
| `detail` | 详细描述 |
| `source` | 来源模块（tracking / memory / system） |
| `action_kind` | 点击动作类型（navigate / ack / open_url） |
| `action_payload` | 动作参数（target_id / message_id / url） |

### 16.3 主动推送轮询

```typescript
// 每 15 秒轮询 GET /aelin/proactive/poll
const { data } = useQuery({
  queryKey: ['proactive-poll'],
  queryFn: () => aelinApi.proactivePoll(),
  refetchInterval: 15_000,
})
// data.items → 新事件 → 更新角标 + 可选桌面通知 (Electron Notification)
```

---

## 17. Device Center — 设备中心

### 17.1 入口与限制

- 仅在桌面端（Electron）显示入口图标
- 通过对话中的 action 也可触发

### 17.2 界面

```
┌─ Device Center Dialog ──────────────────────────────────┐
│                                                          │
│  ┌─ 系统模式 ──────────────────────────────────────┐    │
│  │  当前: 🟢 Normal                                │    │
│  │  [🎯 Focus] [🎤 Meeting] [💤 Sleep] [🟢 Normal] │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─ 进程管理 ──────────── 排序: [CPU ▾] ───────────┐    │
│  │ PID    名称         CPU%   内存MB  异常    操作  │    │
│  │ 1234   chrome.exe   45.2   1200   🔴 高    [⋮]  │    │
│  │ 5678   node.exe     22.1   800    🟡 中    [⋮]  │    │
│  │ 9012   vscode.exe   12.3   600    —        [⋮]  │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  [一键优化高占用进程]                                     │
│                                                          │
│  ┌─ 平台能力 ──────────────────────────────────────┐    │
│  │  ✅ 进程管理   ✅ 优先级调整   ✅ 通知控制       │    │
│  │  ✅ 亮度调节   ⚠️ 需管理员权限: 杀进程           │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

# 第六部分：后端接口契约

## 18. API 端点全量映射

### 18.1 前端页面 → API 端点映射

| 前端页面 | 必需端点 | 可选端点 |
|---|---|---|
| **Chat** | `POST /aelin/chat/stream`, `GET /aelin/context` | `POST /aelin/track/confirm`, `GET /aelin/proactive/poll` |
| **Signals** | `GET /contacts`, `GET /contacts/{id}/messages`, `POST /contacts/{id}/mark-read`, `GET /messages/{id}` | `POST /agent/summarize`, `POST /agent/todos` |
| **Tracking** | `GET /aelin/tracking`, `PATCH /aelin/tracking/targets/{id}`, `GET /.../changes`, `POST /.../ack`, `GET /.../snapshots` | `POST /.../run`, `GET /tracking/file-memory/search` |
| **Settings/Profile** | `GET /me`, `PATCH /me`, `POST /me/avatar` | — |
| **Settings/AI** | `GET /agent/config`, `PATCH /agent/config`, `POST /agent/test`, `GET /agent/catalog` | — |
| **Settings/Accounts** | `GET /accounts`, `POST /accounts`, `DELETE /accounts/{id}`, `POST /accounts/{id}/sync`, `GET /accounts/sync-jobs/{jid}` | `GET /accounts/oauth/…`, `PATCH /accounts/x/…` |
| **Settings/Appearance** | — (纯前端 localStorage) | — |
| **Notifications** | `GET /aelin/notifications`, `GET /aelin/proactive/poll` | — |
| **Device Center** | `GET /aelin/device/capabilities`, `GET /aelin/device/processes`, `POST /.../action`, `POST /.../mode/apply` | `POST /.../optimize` |
| **Context Panel** | `GET /aelin/context` | `GET /agent/memory`, `GET /agent/daily-brief`, `GET /agent/todos` |

### 18.2 SSE 流式事件类型

`POST /api/v1/aelin/chat/stream` 返回的 Server-Sent Events 序列：

| 事件类型 | payload | 前端处理 |
|---|---|---|
| `intent` | `{ intent_type, time_sensitivity, ... }` | 更新 Aelin 状态文案 |
| `plan` | `{ steps: [...] }` | 更新状态 + 准备 ToolTrace 区 |
| `tool_step` | `{ stage, status, detail, count }` | ToolTraceBar 追加进度 |
| `citations` | `AelinCitation[]` | 预填引用区 |
| `actions` | `AelinAction[]` | 渲染建议操作 |
| `reply` | `{ chunk: string }` | 逐字追加到消息 bubble |
| `done` | `{ expression, memory_summary, ... }` | 完成状态 + 更新表情 + 刷新 context |
| `error` | `{ message, code }` | 显示错误 + 重试按钮 |

---

# 第七部分：多端适配

## 19. Electron 桌面端

### 19.1 集成方式

现有 `desktop/src/main.cjs`（391 行）已实现完整的桌面启动链路，新前端需要保证：

| 需求 | 方案 |
|---|---|
| `npm run build` 产出 `dist/` | Vite 默认行为，路径配置不变 |
| `desktop/` 引用 `frontend/dist` | `electron-builder` 的 `extraResources` 引用路径不变 |
| API 代理 | 开发模式代理 `localhost:5173`，生产模式走 express 静态文件 + API 代理 |
| 缩放支持 | `MERCURYDESK_DESKTOP_ZOOM` 环境变量，前端 `<meta viewport>` 配合 |

### 19.2 桌面端增强

- **系统通知**：追踪变化可触发 Electron `Notification` API
- **托盘**：最小化到系统托盘，后台持续追踪
- **窗口管理**：记住窗口位置和大小

---

## 20. Capacitor 移动端

### 20.1 关键适配

| 适配项 | 方案 |
|---|---|
| 路由 | `HashRouter`（运行时检测 `Capacitor.isNativePlatform()`） |
| Safe Area | CSS `env(safe-area-inset-*)` + Tailwind 工具类 |
| API Base URL | Android 模拟器 `10.0.2.2:8000`；物理设备自定义域名；通过 `VITE_API_BASE` 环境变量 |
| StatusBar | `@capacitor/status-bar` 适配深色/浅色主题 |
| Keyboard | `@capacitor/keyboard`，Composer 区跟随键盘弹起 |
| 触控区域 | 所有可点击元素 ≥ 44px × 44px |
| 底部 Tab | 适配 Home Indicator 安全距离 |

### 20.2 构建流程

```bash
# 构建前端产物
cd frontend && npm run build

# 同步到原生项目
npx cap sync

# Android
npx cap open android   # → Android Studio

# iOS
npx cap open ios       # → Xcode
```

---

# 第八部分：性能、安全与测试

## 21. 性能优化策略

### 21.1 首屏加载

| 策略 | 说明 |
|---|---|
| **路由级 Code Splitting** | Chat / Signals / Tracking / Settings 动态 `React.lazy()` |
| **并行数据加载** | `GET /aelin/context` 与 localStorage 会话恢复并行执行 |
| **字体子集化** | 中文字体仅加载常用子集（约 2000 常用字） |
| **预加载关键资源** | 表情图 `<link rel="preload">` |
| **Vite 构建优化** | `rollupOptions.output.manualChunks` 按 vendor 分包 |

### 21.2 运行时性能

| 策略 | 说明 |
|---|---|
| **虚拟化列表** | 消息流、变化流、联系人列表用 `@tanstack/react-virtual` |
| **Memoized Row** | `React.memo(MessageBubble)` + stable key |
| **事件处理器稳定化** | 用 `useRef` 保存 handler，避免子组件重渲染 |
| **TanStack Query 去重** | 同一资源多处订阅自动合并请求 |
| **Debounce 搜索** | 输入框 300ms debounce |
| **Image Lazy Load** | 头像/表情图 `loading="lazy"` |
| **CSS 变量主题切换** | 切换主题只改 `data-theme` 属性，零 JS 重渲染 |

### 21.3 包体大小目标

| 产物 | 目标 |
|---|---|
| 初始 JS (gzipped) | < 100KB |
| 路由 chunk (gzipped) | < 50KB / chunk |
| 总 JS 产物 | < 500KB |
| 总产物（含字体/图片） | < 5MB |

---

## 22. 安全策略

| 风险 | 防护 |
|---|---|
| XSS（Markdown 注入） | `rehype-sanitize` 白名单过滤所有 HTML 标签 |
| 外部链接钓鱼 | `rel="noopener noreferrer"` + 可选安全跳转提示 |
| Token 泄露 | `localStorage` 存储（桌面端单用户模式可接受），未来可迁移到 httpOnly cookie |
| 图片上传攻击 | 前端限制 5MB + 类型白名单 (png/jpg/webp/gif) + 尺寸校验 |
| OAuth 回调劫持 | 严格 `postMessage` origin 验证 |
| 危险进程操作 | 二次确认弹窗 + ConfirmDialog（terminate / optimize） |
| CORS | 后端已配置 allow_origins 白名单 |

---

## 23. 测试策略

| 层次 | 工具 | 覆盖范围 |
|---|---|---|
| **单元测试** | Vitest + Testing Library | shared 组件、hooks、utils、store |
| **集成测试** | Vitest + MSW (Mock Service Worker) | API 调用 + Store 联动 + 页面渲染 |
| **E2E 测试** | Playwright | 关键链路：Chat → Citations → Tracking |
| **视觉回归** | Storybook + Chromatic (可选) | 设计系统组件库 |

**关键测试路径**：

1. Chat 流式对话 → 收到 citations → 点击跳转 Signals
2. Signals 列表 → 拉消息 → 标记已读
3. 追踪创建 → 变化列表 → 确认变化 → 快照对比
4. Settings 添加数据源 → 同步 → 查看状态
5. 主题切换（light/dark/system）无闪烁

---

# 第九部分：开发路线图

## 24. 里程碑计划

### Phase 0：脚手架与设计系统（1-2 轮对话）

- [ ] Vite 6 + React 19 + TypeScript 5.7 项目初始化
- [ ] Tailwind CSS v4 + CSS 变量 Token 系统（双主题）
- [ ] 路由骨架（`_layout.tsx` + 4 个顶级路由 + 空白页面）
- [ ] 响应式 Layout 组件（Nav Rail + Main + Context Panel + Bottom Tab）
- [ ] `shared/components/` 基础 UI 组件（Button, Card, Dialog, Input, Tabs, Toast…）
- [ ] `shared/api/client.ts` + `sse.ts` 基础封装
- [ ] 字体加载 + 表情图迁移

### Phase 1：Aelin Chat 核心体验（2-3 轮对话）

- [ ] `chatStore` (Zustand) + 会话管理 + 持久化
- [ ] SSE 流式对话完整链路（8 种事件类型处理）
- [ ] `MessageBubble`（Markdown 渲染 + Citations + Actions + ToolTrace）
- [ ] `ExpressionAvatar`（11 种表情切换 + framer-motion 动画）
- [ ] `ComposerBar`（文本 + 图片 + 搜索模式 + 快捷指令）
- [ ] `SessionTabs`（多会话 + 重命名 + 删除）
- [ ] Context Panel 4 Tab（记忆/焦点/引用/通知）+ `GET /aelin/context` 对接

### Phase 2：Signals 信息聚合（1-2 轮对话）

- [ ] 联系人列表 + 搜索 + 来源过滤 + 未读排序
- [ ] 消息线程 + `before_id` 分页加载
- [ ] 消息快捷操作（总结/待办/追踪/复制引用）
- [ ] 从 Citation 跳转到 Signals 的联系人线程（含消息高亮）

### Phase 3：Tracking 追踪中心（2 轮对话）

- [ ] 追踪目标列表 + 状态过滤
- [ ] 变化时间线（severity/ack 筛选 + 一键确认）
- [ ] 快照历史 + 简单文本 Diff 视图
- [ ] `TrackConfirmSheet`（从 Chat action 触发 + 独立创建）
- [ ] 追踪目标设置编辑（间隔/通知/标签/描述）
- [ ] 文件化记忆搜索 UI

### Phase 4：Settings + 通知 + 设备中心（1-2 轮对话）

- [ ] Settings 嵌套路由 + 4 个子页面
- [ ] OAuth 连接流程（Gmail/Outlook/GitHub + popup）
- [ ] 模型目录 + AI 配置 + 测试连接
- [ ] 12 种数据源添加向导
- [ ] 通知中心 Drawer + 角标 + 15s 主动轮询
- [ ] 设备中心弹窗（进程表 + 模式切换 + 能力检测）

### Phase 5：多端收口与优化（1 轮对话）

- [ ] Electron 集成验证（`desktop/` 引用 `frontend/dist` 正常启动）
- [ ] Capacitor 移动端适配（HashRouter + Safe Area + Keyboard）
- [ ] 路由级 Code Splitting + 虚拟化列表 + 包体优化
- [ ] 关键路径 E2E 测试

---

## 25. 验收标准

### 功能验收 ✓

- [ ] `npm run dev` → Chat 流式回复 → 点击 Citation → 跳转 Signals → 标记已读
- [ ] Chat → Action"创建追踪" → TrackConfirmSheet → 确认 → Tracking 查看变化
- [ ] Settings 添加数据源 → 触发同步 → Signals 看到新消息
- [ ] 通知角标实时反映追踪变化和新消息
- [ ] 多会话创建/切换/删除/持久化

### 技术验收 ✓

- [ ] `npm run build` → `dist/` 目录可被 `desktop/` 引用打包
- [ ] SSE 流式在弱网下可恢复，不卡 UI
- [ ] Light / Dark 主题切换无闪烁
- [ ] 键盘导航可用、焦点可见
- [ ] `prefers-reduced-motion` 生效

### 性能验收 ✓

- [ ] 首屏初始 JS < 100KB (gzipped)
- [ ] 1000+ 条消息列表滚动 60fps
- [ ] 路由切换 < 200ms

---

# 附录

## A. 表情系统映射表

| ID | 标签 | 使用场景 | 对应图片 |
|---|---|---|---|
| `exp-01` | 捂嘴惊喜 | 害羞、惊喜、被夸 | `expressions/exp-01.png` |
| `exp-02` | 热情出击 | 打招呼、推进执行 | `expressions/exp-02.png` |
| `exp-03` | 温柔赞同 | 支持、安抚、鼓励 | `expressions/exp-03.png` |
| `exp-04` | 托腮思考 | 解释、分析（**默认**） | `expressions/exp-04.png` |
| `exp-05` | 轻声提醒 | 注意事项、风险提示 | `expressions/exp-05.png` |
| `exp-06` | 偷看观察 | 围观进展、等线索 | `expressions/exp-06.png` |
| `exp-07` | 低落求助 | 失败、道歉、需帮助 | `expressions/exp-07.png` |
| `exp-08` | 不满委屈 | 吐槽、抗议 | `expressions/exp-08.png` |
| `exp-09` | 指着大笑 | 玩梗、幽默 | `expressions/exp-09.png` |
| `exp-10` | 发财得意 | 成果突出、高价值 | `expressions/exp-10.png` |
| `exp-11` | 趴桌躺平 | 困倦、过载、需休息 | `expressions/exp-11.png` |

---

## B. 设计 Token 完整定义

```css
/* styles/tokens.css */

:root {
  /* ── Background ── */
  --color-bg: #faf9f5;
  --color-bg-elevated: #f3f1e8;
  --color-panel: #fffdf8;
  --color-panel-alt: #f5f3ec;

  /* ── Text ── */
  --color-text: #141413;
  --color-text-muted: #7a786f;
  --color-text-inverse: #faf9f5;

  /* ── Border ── */
  --color-border: #e8e6dc;
  --color-border-strong: #d0cec4;

  /* ── Accent ── */
  --color-accent: #111111;
  --color-accent-soft: #e8e6dc;

  /* ── Semantic ── */
  --color-orange: #d97757;
  --color-blue: #6a9bcc;
  --color-green: #788c5d;
  --color-danger: #c45c5c;
  --color-warning: #d4a853;

  /* ── Shape ── */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 12px;
  --radius-full: 999px;

  /* ── Shadow ── */
  --shadow-sm: 0 1px 2px rgba(20, 20, 19, 0.04);
  --shadow-md: 0 1px 3px rgba(20, 20, 19, 0.06);
  --shadow-lg: 0 4px 12px rgba(20, 20, 19, 0.08);

  /* ── Typography ── */
  --font-heading: 'Poppins', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-body: 'Lora', 'Noto Serif SC', 'Songti SC', 'STSong', serif;
  --font-mono: 'JetBrains Mono', 'IBM Plex Mono', 'Consolas', monospace;

  /* ── Spacing (8px grid) ── */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
}

[data-theme="dark"] {
  --color-bg: #141413;
  --color-bg-elevated: #1b1b19;
  --color-panel: #1d1d1b;
  --color-panel-alt: #232320;

  --color-text: #faf9f5;
  --color-text-muted: #b0aea5;
  --color-text-inverse: #141413;

  --color-border: #34332f;
  --color-border-strong: #4a4944;

  --color-accent: #f3f3f1;
  --color-accent-soft: #2a2a27;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 1px 4px rgba(0, 0, 0, 0.3);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.4);
}
```

---

## C. 与旧前端的差异对照

| 维度 | 旧前端 | 新设计 | 改进 |
|---|---|---|---|
| **组件体积** | `Aelin.tsx` 1669 行 | 单文件 ≤ 300 行 | Feature Slices 模块化 |
| **状态管理** | 15+ `useState` + 25+ props drilling | Zustand 领域 store + TanStack Query | 消除 prop drilling，状态可预测 |
| **数据请求** | SWR + 单体 `api.ts` 1346 行 | TanStack Query + 8 个领域 API 文件 | 可维护 + 乐观更新 |
| **Desk 面板** | 右侧 Drawer 覆盖聊天 | **独立路由 `/signals`** | 大屏可同时查看聊天和信息 |
| **追踪系统** | 嵌入聊天页的 Dialog | **独立路由 `/tracking`** + 完整 CRUD | 一级产品地位 |
| **UI 库** | MUI (Material Design) | Radix Primitives + Tailwind | 自研设计语言，零冲突 |
| **路由** | 2 个实体页 + 5 个重定向 | 10+ 实体路由 + 嵌套路由 | 功能解耦，可深链 |
| **右侧面板** | 无常驻面板 | **Context Panel**（4 Tab 可折叠） | 大屏并排查看上下文 |
| **响应式** | Drawer 宽度切换 | 三栏 → 两栏 → 单栏 + 底部 Tab | 完整三档适配 |
| **设置页** | 单页面平铺 | 嵌套路由（4 子页面） | 独立可深链 |
| **API 层** | 1346 行混合文件 | 8 个领域文件 + 通用客户端 | 类型完整，按需导入 |
| **主题** | MUI ThemeProvider + 大量 override | CSS 变量 + `data-theme` 属性 | 零 override，切换无闪烁 |
| **动效** | 全局 AnimatePresence | 仅高价值时刻 + 尊重 reduce-motion | 克制、专业 |

