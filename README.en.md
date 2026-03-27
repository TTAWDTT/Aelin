# Aelin (English)

Aelin is now an AI workspace built around DeepAgents as the single agent core, with chat, tools, file-based memory, skill mounting, and desktop runtime support.

## 1. Project Positioning

- Aelin is the product shell; DeepAgents is the only agent loop.
- The runtime is designed around factual tool outcomes instead of a separate legacy planner layer.
- Supports both web and desktop runtimes.
- Backend = an official LangGraph Agent Server (`/assistants`, `/threads`, `/runs`) with Aelin product APIs mounted alongside it (`/api/v1/aelin/*`, `/api/v1/agent/*`); for extending behavior, prefer editing the DeepAgents graph/skills and refer to both `docs/deepagents_arch.md` and the official DeepAgents documentation.

## 2. Core Capabilities

- Chat with streaming responses.
- DeepAgents tools: `web_search`, `attachment_search`, `google_workspace`, `device`, `screen_get`.
- File-based long-term memory mounted from `/memory/AGENTS.md`.
- Skills mounted from `backend/deepagents_skills/`, with optional external skill roots.
- Desktop integration through Electron and the local desktop plugin.

## 3. Repository Layout

- `backend/`: FastAPI API, DeepAgents glue, tool implementations, tests.
- `frontend/`: React 19 + Vite + TypeScript.
- `desktop/`: Electron runtime and packaging scripts.
- `docs/`: architecture notes, guides, and cleanup history.
- `data/`: local runtime data and file-memory workspace.

## 4. Quick Start

```powershell
# Backend
cd backend
python -m pip install -r requirements.txt
python -m langgraph dev --config langgraph.json --host 127.0.0.1 --port 8000 --no-browser

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Desktop
cd desktop
npm install
npm run dev
```

## 5. Common Development Commands

```powershell
# Backend tests
cd backend
pytest -q

# Frontend build
cd frontend
npm run build

# Desktop packaging
cd desktop
npm run dist
```

## 6. Configuration and Security

- Preferred env prefix: `AELIN_*`
- Backward-compatible fallback: `MERCURYDESK_*`
- Common settings:
  - `AELIN_SECRET_KEY`
  - `AELIN_FERNET_KEY`
  - `AELIN_DATABASE_URL`
  - `AELIN_CORS_ORIGINS`
  - `AELIN_LLM_REQUEST_TIMEOUT_SECONDS`
  - `AELIN_LLM_VERIFY_SSL`
  - `AELIN_DEEPAGENTS_EXTRA_SKILLS_DIR`
  - `AELIN_DESKTOP_PLUGIN_BASE_URL`
  - `AELIN_GOOGLE_WORKSPACE_CLI_BIN`

Do not commit API keys, OAuth secrets, or local DB artifacts.

## 7. Contribution Notes

- Prefer Conventional Commits: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`.
- Before opening a PR, run at least `pytest -q` and relevant frontend/desktop builds.
- Collaboration rules: [AGENTS.md](AGENTS.md).

## 8. References

- [README.zh-CN.md](README.zh-CN.md)
- [docs/INDEX.md](docs/INDEX.md)
- [docs/deepagents_arch.md](docs/deepagents_arch.md)
- [docs/deepagents_skills_guide.md](docs/deepagents_skills_guide.md)
- [docs/gws.md](docs/gws.md)
