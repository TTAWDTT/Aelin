# Aelin

<div align="center">

  [![English](https://img.shields.io/badge/lang-English-blue)](README.en.md)
  [![简体中文](https://img.shields.io/badge/lang-简体中文-green)](README.zh-CN.md)

  <img src="desktop/build/icon.png" alt="Aelin Logo" width="120" height="120">

  **A DeepAgents-powered AI workspace with chat, tools, memory, and desktop runtime**

  [![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](backend/requirements.txt)
  [![Frontend](https://img.shields.io/badge/Frontend-React%2019-20232A?style=flat-square&logo=react&logoColor=61DAFB)](frontend/package.json)
  [![Desktop](https://img.shields.io/badge/Desktop-Electron-2B2E3A?style=flat-square&logo=electron&logoColor=9FEAF9)](desktop/package.json)
  [![Memory](https://img.shields.io/badge/Memory-AGENTS.md-2563EB?style=flat-square)](docs/deepagents_arch.md)
</div>

---

## Features

- **DeepAgents Chat Core** - Aelin now uses DeepAgents as the single agent loop.
- **Built-in Tools** - `web_search`, `attachment_search`, `google_workspace`, `device`, `screen_get`.
- **File-Based Memory** - Long-term memory is mounted from `/memory/AGENTS.md`.
- **Skills Runtime** - Built-in skills live in `backend/deepagents_skills/`, with optional external skill mounting.
- **Desktop Runtime** - Electron shell for local usage and device integration.

## Repository Layout

- `backend/` - FastAPI API, DeepAgents glue, tools, services, tests.
- `frontend/` - React 19 + Vite + TypeScript app.
- `desktop/` - Electron runtime and packaging.
- `docs/` - architecture notes, guides, and cleanup history.
- `data/` - local runtime data and file-memory workspace.

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

### 3) Desktop

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

## Configuration

- Preferred env prefix: `AELIN_*`
- Backward-compatible fallback: `MERCURYDESK_*`
- Common keys:
  - `AELIN_SECRET_KEY`
  - `AELIN_FERNET_KEY`
  - `AELIN_DATABASE_URL`
  - `AELIN_CORS_ORIGINS`
  - `AELIN_LLM_REQUEST_TIMEOUT_SECONDS`
  - `AELIN_DEEPAGENTS_EXTRA_SKILLS_DIR`
  - `AELIN_DESKTOP_PLUGIN_BASE_URL`
  - `AELIN_GOOGLE_WORKSPACE_CLI_BIN`

Do not commit API keys, OAuth secrets, or local database artifacts.

## Documentation

- Chinese README: [README.zh-CN.md](README.zh-CN.md)
- English README: [README.en.md](README.en.md)
- Contributor guide: [AGENTS.md](AGENTS.md)
- Docs index: [docs/INDEX.md](docs/INDEX.md)
- DeepAgents architecture: [docs/deepagents_arch.md](docs/deepagents_arch.md)
- DeepAgents skills guide: [docs/deepagents_skills_guide.md](docs/deepagents_skills_guide.md)
- Google Workspace guide: [docs/gws.md](docs/gws.md)
