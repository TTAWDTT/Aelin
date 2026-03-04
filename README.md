# Aelin

<div align="center">

  [![English](https://img.shields.io/badge/lang-English-blue)](README.en.md)
  [![简体中文](https://img.shields.io/badge/lang-简体中文-green)](README.zh-CN.md)

  <img src="desktop/build/icon.png" alt="Aelin Logo" width="120" height="120">

  **A collaboration-first AI assistant with chat, memory, tracking, and computer-use tooling**

  [![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](backend/README.md)
  [![Frontend](https://img.shields.io/badge/Frontend-React%2019-20232A?style=flat-square&logo=react&logoColor=61DAFB)](frontend/package.json)
  [![Desktop](https://img.shields.io/badge/Desktop-Electron-2B2E3A?style=flat-square&logo=electron&logoColor=9FEAF9)](desktop/package.json)
  [![Database](https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](backend/README.md)
  [![Agent Loop](https://img.shields.io/badge/Agent-Tool%20Calling-6C63FF?style=flat-square)](docs/agent_loop_manual_test_cases.md)
</div>

---

## Features

- **Agent Chat + Multimodal** - Text/image chat with streaming responses.
- **Tool-Driven Agent Loop** - Built-in tools for context, diary, profile, tracking, device, web search, screen read, and browser actions.
- **Computer Use Baseline** - Manual screenshot input + autonomous `screen_get`; browser state read and controlled/external navigation.
- **Long-Term Memory** - OpenViking-compatible file-memory structure.
- **Continuous Tracking** - Target tracking, snapshots, and change records.
- **Desktop Runtime** - Electron shell for local agent usage.

## Repository Layout

- `backend/` - FastAPI API, SQLAlchemy models, services, schedulers.
- `backend/tests/` - Pytest suite.
- `frontend/` - React 19 + Vite + TypeScript app.
- `desktop/` - Electron runtime and packaging.
- `docs/` - Architecture, plans, and test notes.
- `data/` - Local runtime data and file-memory workspace.

## Quick Start

### 1) Backend

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### 2) Frontend

```powershell
cd frontend
npm install
npm run dev
```

### 3) Desktop (Optional)

```powershell
cd desktop
npm install
npm run dev
```

## Common Commands

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

## Configuration Highlights

- Core security/config:
  - `MERCURYDESK_SECRET_KEY`
  - `MERCURYDESK_FERNET_KEY`
  - `MERCURYDESK_DATABASE_URL`
  - `MERCURYDESK_CORS_ORIGINS`
- Agent loop:
  - `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
  - `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
- Browser tools:
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENABLED`
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT`
  - `MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE`

Do not commit API keys, OAuth secrets, or local database artifacts.

## Documentation

- Chinese README: [README.zh-CN.md](README.zh-CN.md)
- English README: [README.en.md](README.en.md)
- Contributor guide: [AGENTS.md](AGENTS.md)
- Backend notes: [backend/README.md](backend/README.md)
- Docs index: [docs/INDEX.md](docs/INDEX.md)
- Manual test cases: [docs/agent_loop_manual_test_cases.md](docs/agent_loop_manual_test_cases.md)
