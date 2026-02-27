# Aelin

<div align="center">
  <img src="desktop/build/icon.png" width="108" alt="Aelin Logo" />
  <h3>长期记忆型 AI 助手</h3>
  <p>Chat + Tracking + File Memory + Agent Loop</p>
  <p>
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Frontend-React%2019-20232A?style=flat-square&logo=react&logoColor=61DAFB" alt="React 19" />
    <img src="https://img.shields.io/badge/Desktop-Electron-2B2E3A?style=flat-square&logo=electron&logoColor=9FEAF9" alt="Electron" />
    <img src="https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
    <img src="https://img.shields.io/badge/Agent-Tool%20Calling-6C63FF?style=flat-square" alt="Agent Tool Calling" />
    <img src="https://img.shields.io/badge/RAG-OpenViking%20Compatible-1E88E5?style=flat-square" alt="OpenViking Compatible" />
  </p>
</div>

---

## 为什么是 Aelin

**Aelin 的目标不是“聊天机器人”，而是“可持续协作的个人 AI 系统”**：

- 聊天时可直接调用工具检索上下文、日记、追踪和设备状态
- 回答可附带证据链，不依赖纯猜测
- 支持长期文件记忆（OpenViking 兼容结构）
- 支持持续追踪并生成变化记录

---

## 导航

- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [快速启动](#快速启动)
- [桌面版](#桌面版)
- [配置说明](#配置说明)
- [Aelin API 索引](#aelin-api-索引)
- [搜索与追踪说明](#搜索与追踪说明)
- [测试与验证](#测试与验证)
- [常见问题排查](#常见问题排查)
- [相关文档](#相关文档)

---

## 核心能力

### Chat-first 入口

- 默认首页是 Aelin 聊天入口
- 支持流式回复、上下文注入、历史对话、图像输入
- 返回可执行动作（如打开追踪、定位日记命中）

### 多源接入

- IMAP 邮箱
- GitHub 通知（OAuth / Token）
- RSS / Blog
- Bilibili / X / Weibo / 小红书等链路
- 邮件转发入口（Forward Inbound）

### 长期记忆 + 日记系统

- 会话记忆摘要（focus items / notes / todos）
- Tracking File Memory（OpenViking 兼容）
- 日记文件树检索、内容读取、前端呈现

### 追踪系统

- 追踪目标 CRUD
- 定时调度与手动 run once
- 快照存储与变更记录
- ack / 批量 ack

### Agent Loop + 工具调用

- 默认支持 Agent Loop
- 读工具可并行，写工具策略可控
- 工具族：`context_get`、`diary`、`profile`、`tracking`、`device`、`web_search`

---

## 系统架构

### Monorepo 结构

- `backend/`：FastAPI + SQLAlchemy + 调度器 + Agent 核心服务
- `frontend/`：React + Vite + TypeScript
- `desktop/`：Electron 桌面壳
- `docs/`：产品与工程文档
- `data/`：本地文件记忆目录

### 后端关键文件

- 路由：
  - `backend/app/routers/aelin.py`
  - `backend/app/routers/agent.py`
- Agent：
  - `backend/app/services/aelin_agent_loop.py`
  - `backend/app/services/aelin_tools.py`
  - `backend/app/services/aelin_tool_policy.py`
- 搜索/追踪：
  - `backend/app/services/web_search.py`
  - `backend/app/services/tracking_autonomy.py`
- 记忆桥接：
  - `backend/app/services/openviking_bridge.py`

---

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

访问：

```text
http://127.0.0.1:5173
```

### 3) 首次建议配置

1. 在设置中配置 Agent（Provider / Model / API Key）
2. 连接数据源（IMAP / OAuth / RSS）
3. 需要跨区域联网搜索时，设置 `web_search_proxy_url`

---

## 桌面版

目录：`desktop/`

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

输出目录：`desktop/release/` 或 `desktop/release-dist/`

若 Python 不在 PATH：

```powershell
$env:MERCURYDESK_PYTHON="C:\\path\\to\\python.exe"
```

---

## 配置说明

### Agent 配置接口

- `GET /api/v1/agent/config`
- `PATCH /api/v1/agent/config`
- `POST /api/v1/agent/test`
- `GET /api/v1/agent/catalog`

配置关键字段：

- `provider`
- `base_url`
- `model`
- `temperature`
- `web_search_proxy_url`（按用户存储）

### 常用环境变量（后端）

基础：

- `MERCURYDESK_DATABASE_URL`
- `MERCURYDESK_SECRET_KEY`
- `MERCURYDESK_FERNET_KEY`
- `MERCURYDESK_CORS_ORIGINS`

OAuth：

- `MERCURYDESK_GMAIL_CLIENT_ID` / `MERCURYDESK_GMAIL_CLIENT_SECRET`
- `MERCURYDESK_OUTLOOK_CLIENT_ID` / `MERCURYDESK_OUTLOOK_CLIENT_SECRET`
- `MERCURYDESK_GITHUB_CLIENT_ID` / `MERCURYDESK_GITHUB_CLIENT_SECRET`

Agent Loop：

- `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_TOOL_CALLS`
- `MERCURYDESK_AELIN_AGENT_LOOP_ALLOW_WRITE_TOOLS`

记忆：

- `MERCURYDESK_OPENVIKING_ENABLED`
- `MERCURYDESK_OPENVIKING_SEMANTIC_ENABLED`
- `MERCURYDESK_OPENVIKING_DATA_DIR`

---

## Aelin API 索引

聊天：

- `POST /api/v1/aelin/chat`
- `POST /api/v1/aelin/chat/stream`
- `GET /api/v1/aelin/context`

追踪：

- `GET /api/v1/aelin/tracking`
- `PATCH /api/v1/aelin/tracking/targets/{target_id}`
- `POST /api/v1/aelin/tracking/targets/{target_id}/run`
- `GET /api/v1/aelin/tracking/targets/{target_id}/changes`
- `POST /api/v1/aelin/tracking/targets/{target_id}/changes/ack`

文件记忆与日记：

- `GET /api/v1/aelin/tracking/file-memory/search`
- `GET /api/v1/aelin/tracking/file-memory/content`
- `GET /api/v1/aelin/tracking/file-memory/tree`

设备：

- `GET /api/v1/aelin/device/capabilities`
- `GET /api/v1/aelin/device/processes`
- `POST /api/v1/aelin/device/mode/apply`

---

## 搜索与追踪说明

### 当前联网搜索源（WebSearchService）

- Bing HTML
- DuckDuckGo Lite
- DuckDuckGo Instant API
- Google News RSS
- Reddit JSON Search
- Hacker News Algolia
- Wikipedia API

默认策略（当前主链路）：

- `max_results = 15`
- `fetch_top_k = 5`
- 去重 + 打分 + 回退抓取（reader/browser）

### 关于 X/Twitter

- 无登录或受限网络时，公开页面可见性有限
- 对时效强、门槛高的信息，建议配合代理与可用 Connector

---

## 测试与验证

后端：

```powershell
cd backend
pytest -q
```

前端构建：

```powershell
cd frontend
npm run build
```

建议回归：

1. `POST /api/v1/aelin/chat/stream` 正常返回
2. `GET/PATCH /api/v1/agent/config` 能读写 `web_search_proxy_url`
3. 追踪 run once 可写入快照/变化

---

## 常见问题排查

### 1) `422 Unprocessable Entity`（聊天接口）

优先检查请求体是否符合 `AelinChatRequest`：

- `query` 非空（或包含图片输入）
- `workspace` 合法
- `history` 为 `{role, content}` 列表

### 2) `sqlite3.OperationalError: database is locked`

- 避免多进程并发写同一 SQLite 文件
- 避免重复启动后端实例
- 高并发场景建议迁移 PostgreSQL

### 3) 搜索结果偏少或偏保守

- 在设置中配置 `web_search_proxy_url`
- 检查当前网络能否访问搜索源
- 时间敏感问题默认更保守，证据不足会拒绝给结论

---

## 相关文档

- `backend/README.md`
- `docs/aelin/vision.md`
- `docs/aelin/prd-v1.md`
- `docs/aelin/memory-model.md`
- `docs/email-forwarding.md`
