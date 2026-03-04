# Aelin

Aelin is a long-memory AI assistant system built for daily collaboration: chat, tool use, tracking, and desktop runtime.

- 中文版: [中文](#中文)
- English: [English](#english)

---

## 中文

### 项目简介
Aelin 是一个以“可持续协作”为目标的 AI 助手工程，而不是只做一次性问答。当前仓库包含 Web 与 Desktop 两种运行形态，并内置 Agent Loop、工具调用、长期记忆与追踪能力。

### 核心能力
- 聊天与多模态输入：支持文本、图片输入与流式输出。
- Agent Loop 工具执行：支持 `context_get`、`diary`、`profile`、`tracking`、`device`、`web_search`、`screen_get`、`browser_state_get`、`browser_use` 等。
- Computer Use 基础链路：支持手动截图输入 + `screen_get` 自主读屏；支持浏览器状态读取与受控/外部浏览器导航。
- 记忆与追踪：支持长期文件记忆（OpenViking 兼容结构）与目标追踪变更记录。

### 仓库结构
- `backend/`: FastAPI + SQLAlchemy + Agent 服务与调度。
- `backend/tests/`: Pytest 测试集。
- `frontend/`: React 19 + Vite + TypeScript。
- `desktop/`: Electron 桌面壳与打包脚本。
- `docs/`: 架构、规划与测试文档。
- `data/`: 本地运行数据与文件记忆目录。

### 快速启动
```powershell
# Backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Desktop (optional)
cd desktop
npm install
npm run dev
```

### 常用命令
```powershell
# Backend tests
cd backend
pytest -q

# Frontend build
cd frontend
npm run build

# Desktop package
cd desktop
npm run dist
```

### 关键环境变量（示例）
- `MERCURYDESK_SECRET_KEY`, `MERCURYDESK_FERNET_KEY`
- `MERCURYDESK_DATABASE_URL`, `MERCURYDESK_CORS_ORIGINS`
- `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
- `MERCURYDESK_BROWSER_TOOL_CDP_ENABLED`
- `MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT`
- `MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE`

### 贡献与协作
- 提交规范建议使用 Conventional Commits（如 `feat(scope): ...`、`fix(scope): ...`）。
- 开 PR 前至少执行：`pytest -q` 与相关前端/桌面构建。
- 详细协作规范见 [AGENTS.md](AGENTS.md)。

### 相关文档
- [docs/INDEX.md](docs/INDEX.md)
- [docs/agent_loop_manual_test_cases.md](docs/agent_loop_manual_test_cases.md)
- [docs/computer_use.md](docs/computer_use.md)
- [backend/README.md](backend/README.md)

---

## English

### Overview
Aelin is designed as a collaboration-first AI assistant system, not just a one-shot chatbot. This monorepo includes web and desktop runtimes, plus an agent loop, tool calling, long-term memory, and tracking workflows.

### Core Capabilities
- Chat + multimodal input: text/image input with streaming responses.
- Agent-loop tool execution: `context_get`, `diary`, `profile`, `tracking`, `device`, `web_search`, `screen_get`, `browser_state_get`, `browser_use`, and more.
- Computer-use baseline: manual screenshot input + autonomous `screen_get`; browser state inspection and controlled/external browser navigation.
- Memory and tracking: OpenViking-compatible file-memory structure and continuous change tracking.

### Repository Layout
- `backend/`: FastAPI API, SQLAlchemy models, agent services, schedulers.
- `backend/tests/`: Pytest test suite.
- `frontend/`: React 19 + Vite + TypeScript UI.
- `desktop/`: Electron runtime and packaging scripts.
- `docs/`: Architecture, planning, and test notes.
- `data/`: Local runtime data and file-memory workspace.

### Quick Start
```powershell
# Backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Desktop (optional)
cd desktop
npm install
npm run dev
```

### Common Commands
```powershell
# Backend tests
cd backend
pytest -q

# Frontend build
cd frontend
npm run build

# Desktop package
cd desktop
npm run dist
```

### Key Environment Variables (examples)
- `MERCURYDESK_SECRET_KEY`, `MERCURYDESK_FERNET_KEY`
- `MERCURYDESK_DATABASE_URL`, `MERCURYDESK_CORS_ORIGINS`
- `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
- `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
- `MERCURYDESK_BROWSER_TOOL_CDP_ENABLED`
- `MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT`
- `MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE`

### Contribution
- Prefer Conventional Commits (`feat(scope): ...`, `fix(scope): ...`).
- Run at least `pytest -q` and relevant frontend/desktop builds before opening a PR.
- Contributor workflow details: [AGENTS.md](AGENTS.md).

### Docs
- [docs/INDEX.md](docs/INDEX.md)
- [docs/agent_loop_manual_test_cases.md](docs/agent_loop_manual_test_cases.md)
- [docs/computer_use.md](docs/computer_use.md)
- [backend/README.md](backend/README.md)
