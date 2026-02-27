# Aelin

Aelin 是一个面向个人场景的长期记忆型 AI 助手：以 Chat 为主入口，融合多源数据接入、持续追踪、文件化记忆（OpenViking 兼容）和可控工具调用（Agent Loop）。

## 目录

- [项目定位](#项目定位)
- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [快速启动](#快速启动)
- [桌面版](#桌面版)
- [配置说明](#配置说明)
- [Aelin API 快速索引](#aelin-api-快速索引)
- [搜索与追踪说明](#搜索与追踪说明)
- [测试与验证](#测试与验证)
- [常见问题排查](#常见问题排查)
- [相关文档](#相关文档)

## 项目定位

Aelin 聚焦三件事：

1. 把“聊天、搜索、跟踪、记忆”放在同一个体验里。
2. 给每个回答提供可追溯证据（本地消息、追踪快照、联网检索）。
3. 在可控边界内支持 Agent 化工具调用，而不是纯模板回复。

## 核心能力

### 1) Chat-first 交互

- 默认首页是 Aelin 聊天入口。
- 支持普通回复和流式回复。
- 支持带历史上下文、多图输入、工作区隔离。
- 支持动作回传（例如打开追踪详情、定位日记命中路径）。

### 2) 多源接入与同步

- IMAP 邮箱（Gmail / Outlook / QQ / 163 等）
- GitHub 通知（OAuth 或 Token）
- RSS / Blog
- Bilibili / X / Weibo / 小红书等平台链路（部分由 Connector + 调度执行）
- 邮件转发接入（Forward Inbound）

### 3) 记忆系统

- 短期记忆：会话上下文、focus items、todo 等。
- 文件化长期记忆：Tracking File Memory（OpenViking 兼容结构）。
- 日记文件树检索与内容读取接口（供 UI 和 Agent 工具使用）。

### 4) 追踪系统

- 追踪目标 CRUD
- 定时调度（autonomy scheduler）
- 变化快照与变更记录
- 手动 run once 与批量 ack

### 5) Agent Loop + 工具调用

- 默认启用 Agent Loop（可通过配置关闭）。
- 支持读工具并行执行、写工具策略受控。
- 内置工具族：`context_get` / `diary` / `profile` / `tracking` / `device` / `web_search`。
- 支持影子模式（shadow）与硬失败策略（hard fail）。

## 系统架构

### Monorepo 结构

- `backend/`：FastAPI + SQLAlchemy + 调度器 + Agent 核心服务
- `frontend/`：React + Vite + TypeScript
- `desktop/`：Electron 桌面壳（Windows 打包）
- `docs/`：产品与工程文档
- `data/`：本地文件记忆数据（默认）

### 后端关键组件

- 路由层：
  - `app/routers/aelin.py`
  - `app/routers/agent.py`
  - `app/routers/accounts.py` / `messages.py` / `inbound.py` 等
- 服务层：
  - `app/services/aelin_agent_loop.py`
  - `app/services/aelin_tools.py`
  - `app/services/aelin_tool_policy.py`
  - `app/services/web_search.py`
  - `app/services/tracking_autonomy.py`
  - `app/services/openviking_bridge.py`
- 配置：
  - `app/settings.py`（环境变量前缀仍是 `MERCURYDESK_`，为历史兼容）

## 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+
- npm

### 1) 启动后端

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

后端健康检查：

```text
GET http://127.0.0.1:8000/healthz
```

### 2) 启动前端

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

### 3) 首次登录后建议配置

1. 设置 Agent Provider / Model / API Key
2. 配置连接源（IMAP / OAuth / RSS 等）
3. 如需跨区域检索，在 Agent 设置中填写联网搜索代理 `web_search_proxy_url`

## 桌面版

桌面壳目录：`desktop/`

### 开发模式

```powershell
cd desktop
npm install
npm run dev
```

### 打包

```powershell
cd desktop
npm install
npm run dist
```

产物目录：`desktop/release/` 或 `desktop/release-dist/`

如果本机 Python 不在 PATH，可设置：

```powershell
$env:MERCURYDESK_PYTHON="C:\\path\\to\\python.exe"
```

## 配置说明

### Agent 配置接口

- `GET /api/v1/agent/config`
- `PATCH /api/v1/agent/config`
- `POST /api/v1/agent/test`
- `GET /api/v1/agent/catalog`

`agent/config` 关键字段：

- `provider`
- `base_url`
- `model`
- `temperature`
- `web_search_proxy_url`（新增，按用户存储）

### 关键环境变量（后端）

基础：

- `MERCURYDESK_DATABASE_URL`
- `MERCURYDESK_SECRET_KEY`
- `MERCURYDESK_FERNET_KEY`
- `MERCURYDESK_CORS_ORIGINS`
- `MERCURYDESK_MEDIA_DIR`

OAuth：

- `MERCURYDESK_GMAIL_CLIENT_ID` / `MERCURYDESK_GMAIL_CLIENT_SECRET`
- `MERCURYDESK_OUTLOOK_CLIENT_ID` / `MERCURYDESK_OUTLOOK_CLIENT_SECRET`
- `MERCURYDESK_GITHUB_CLIENT_ID` / `MERCURYDESK_GITHUB_CLIENT_SECRET`

OpenViking / 记忆：

- `MERCURYDESK_OPENVIKING_ENABLED`
- `MERCURYDESK_OPENVIKING_SEMANTIC_ENABLED`
- `MERCURYDESK_OPENVIKING_DATA_DIR`

Agent Loop：

- `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_TOOL_CALLS`
- `MERCURYDESK_AELIN_AGENT_LOOP_ALLOW_WRITE_TOOLS`
- `MERCURYDESK_AELIN_AGENT_LOOP_ROUND_TIMEOUT_SECONDS`
- `MERCURYDESK_AELIN_AGENT_LOOP_TOTAL_TIMEOUT_SECONDS`

### 配置持久化说明

- 数据库默认 SQLite（当前目录下 `mercurydesk.db`）。
- 应用启动时会做轻量列迁移（例如 `agent_configs.web_search_proxy_url`）。

## Aelin API 快速索引

以下为高频接口，完整参数请看 `backend/app/schemas.py` 与路由文件。

聊天与上下文：

- `POST /api/v1/aelin/chat`
- `POST /api/v1/aelin/chat/stream`
- `GET /api/v1/aelin/context`
- `GET /api/v1/aelin/notifications`

追踪：

- `GET /api/v1/aelin/tracking`
- `PATCH /api/v1/aelin/tracking/targets/{target_id}`
- `POST /api/v1/aelin/tracking/targets/{target_id}/run`
- `GET /api/v1/aelin/tracking/targets/{target_id}/changes`
- `POST /api/v1/aelin/tracking/targets/{target_id}/changes/ack`

文件记忆 / 日记：

- `GET /api/v1/aelin/tracking/file-memory/search`
- `GET /api/v1/aelin/tracking/file-memory/content`
- `GET /api/v1/aelin/tracking/file-memory/tree`

设备：

- `GET /api/v1/aelin/device/capabilities`
- `GET /api/v1/aelin/device/processes`
- `POST /api/v1/aelin/device/mode/apply`

## 搜索与追踪说明

### 联网搜索（WebSearchService）

当前组合检索源包括：

- Bing HTML
- DuckDuckGo Lite
- DuckDuckGo Instant API
- Google News RSS
- Reddit JSON Search
- Hacker News Algolia
- Wikipedia API

当前默认行为（核心链路）：

- 默认 `max_results = 15`
- 追踪/聊天链路抓取正文 `fetch_top_k = 5`
- 会进行去重、打分、必要时 reader/browser 回退抓取

### X/Twitter 现实边界

- Web 检索可以命中部分公开页面，但对实时性和完整性不稳定。
- 对登录墙、反爬和地区限制场景，建议结合代理和可用 Connector。

## 测试与验证

### 后端

```powershell
cd backend
pytest -q
```

### 前端

```powershell
cd frontend
npm run build
```

### 建议的最小回归

1. `POST /api/v1/aelin/chat/stream` 可正常返回事件流
2. `GET/PATCH /api/v1/agent/config` 可读写 `web_search_proxy_url`
3. 追踪 run once 可成功写入快照/变化

## 常见问题排查

### 1) `422 Unprocessable Entity`（聊天流接口）

先检查请求体是否满足 `AelinChatRequest`：

- `query` 非空（或有图片输入）
- `workspace` 长度合法
- `history` 格式为 `{role, content}` 列表

### 2) `sqlite3.OperationalError: database is locked`

- 避免多个进程同时高频写同一 SQLite 文件
- 保证只启动一套主要后端实例
- 如为重度并发场景，建议迁移到 PostgreSQL

### 3) 搜索结果偏少或偏“保守”

- 在 Agent 设置中配置 `web_search_proxy_url`
- 检查网络环境是否可访问对应搜索源
- 对时间敏感问题，Aelin 默认会偏向“证据不足不下结论”

## 相关文档

- `backend/README.md`
- `docs/aelin/vision.md`
- `docs/aelin/prd-v1.md`
- `docs/aelin/memory-model.md`
- `docs/email-forwarding.md`

---

如果你要把 README 再细化成“开发者版 + 使用者版”两份，我建议下一步拆分为：

- `README.md`（面向新用户）
- `docs/dev/README.md`（面向开发者与二次开发）
