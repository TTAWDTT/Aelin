# Aelin (English)

Aelin is a collaboration-first AI assistant system with chat, tool calling, memory, tracking, and desktop runtime.

## 1. Project Positioning
- Not a one-shot chatbot, but a long-running personal AI collaboration system.
- Built around an agent loop with policy-controlled tool execution.
- Supports both web and desktop runtimes.

## 2. Core Capabilities
- Chat and multimodal input: text/image input with streaming responses.
- Tool execution: `context_get`, `diary`, `profile`, `tracking`, `device`, `web_search`, `screen_get`, `browser_state_get`, `browser_use`.
- Computer-use baseline: manual screenshot input + autonomous `screen_get`; controlled/external browser navigation and state reads.
- Long-term memory and tracking: OpenViking-compatible file-memory structure plus continuous change tracking.

## 3. Repository Layout
- `backend/`: FastAPI API, SQLAlchemy, agent services, schedulers.
- `backend/tests/`: Pytest suite.
- `frontend/`: React 19 + Vite + TypeScript.
- `desktop/`: Electron runtime and packaging scripts.
- `docs/`: architecture, plans, and testing docs.
- `data/`: local runtime data and file-memory workspace.

## 4. Quick Start
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
- Common environment variables:
  - `MERCURYDESK_SECRET_KEY`
  - `MERCURYDESK_FERNET_KEY`
  - `MERCURYDESK_DATABASE_URL`
  - `MERCURYDESK_CORS_ORIGINS`
  - `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
  - `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENABLED`
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT`
  - `MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE`
- Do not commit API keys, OAuth secrets, or local DB artifacts.

## 7. Contribution Notes
- Prefer Conventional Commits: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`.
- Before opening a PR, run at least `pytest -q` and relevant frontend/desktop builds.
- Collaboration rules: [AGENTS.md](AGENTS.md).

## 8. References
- [README.zh-CN.md](README.zh-CN.md)
- [backend/README.md](backend/README.md)
- [docs/INDEX.md](docs/INDEX.md)
- [docs/agent_loop_manual_test_cases.md](docs/agent_loop_manual_test_cases.md)

