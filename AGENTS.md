# AGENTS.md

## Project Snapshot

Aelin is a DeepAgents-powered AI workspace with three main surfaces:

- `backend/`: FastAPI product APIs plus a LangGraph Agent Server graph.
- `frontend/`: React 19 + Vite + TypeScript chat UI.
- `desktop/`: Electron runtime, local desktop bridge, and packaging.

Current development is on `experiment/deepagents-native-shell`. Treat this branch as the "official Agent Server + DeepAgents native stream + thin Aelin product shell" line of development.

## Non-Negotiable Architecture Guardrails

Keep these boundaries intact when making changes:

- Do not reintroduce the old custom Aelin chat loop, custom SSE protocol, `tool_trace`, `reply`, or `memory_summary` style compatibility layers into the main chat path.
- The primary chat flow is:
  - frontend `useStream(...)`
  - LangGraph Agent Server `/assistants`, `/threads`, `/runs/stream`
  - [`backend/agent_server/graph.py`](/Users/TTAWDTT/Github/Aelin/backend/agent_server/graph.py)
  - [`backend/app/services/deepagents/deepagents_graph.py`](/Users/TTAWDTT/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)
- Runtime memory for chat should stay anchored to `/memory/AGENTS.md` content resolved per user/workspace. Do not quietly add separate hidden context channels back into the main loop.
- Aelin-specific backend routes should stay thin and product-focused:
  - `/api/v1/agent/*`
  - `/api/v1/attachments/*`
  - `/api/v1/aelin/device/*`
  - `/api/v1/aelin/remote-control/*`
- Frontend execution state should continue to derive from official run/message/tool metadata, not from parsing assistant prose or reviving legacy stop-reason semantics.
- New skills belong under `backend/deepagents_skills/<skill-name>/SKILL.md` and should be mounted through the DeepAgents skill mechanism rather than hardcoded into prompts.

## Repo Map

### Backend

- [`backend/agent_server/graph.py`](/Users/TTAWDTT/Github/Aelin/backend/agent_server/graph.py): LangGraph graph factory and per-run runtime resolution.
- [`backend/agent_server/auth.py`](/Users/TTAWDTT/Github/Aelin/backend/agent_server/auth.py): Agent Server auth integration.
- [`backend/app/main.py`](/Users/TTAWDTT/Github/Aelin/backend/app/main.py): FastAPI app for product APIs mounted alongside Agent Server.
- [`backend/app/services/deepagents/`](/Users/TTAWDTT/Github/Aelin/backend/app/services/deepagents): graph assembly, runtime resolution, tool policy, delivery paths, cancellation, output shaping.
- [`backend/app/services/tools/`](/Users/TTAWDTT/Github/Aelin/backend/app/services/tools): tool wrappers for web, attachments, device, execute, Google Workspace, artifacts.
- [`backend/tests/`](/Users/TTAWDTT/Github/Aelin/backend/tests): pytest coverage for graph/runtime/tool behavior and API contracts.

### Frontend

- [`frontend/src/features/chat/`](/Users/TTAWDTT/Github/Aelin/frontend/src/features/chat): main chat feature, stream consumption, execution pane, artifacts, stores.
- [`frontend/src/app/`](/Users/TTAWDTT/Github/Aelin/frontend/src/app): app shell, routes, layout.
- [`frontend/src/shared/`](/Users/TTAWDTT/Github/Aelin/frontend/src/shared): API clients, reusable hooks/components, shared stores.

### Desktop

- [`desktop/src/main.cjs`](/Users/TTAWDTT/Github/Aelin/desktop/src/main.cjs): intentionally thin Electron entrypoint.
- [`desktop/src/aelin_desktop_runtime.cjs`](/Users/TTAWDTT/Github/Aelin/desktop/src/aelin_desktop_runtime.cjs): real desktop runtime, backend/frontend bootstrapping, pet window, plugin API, tray/menu wiring.
- [`desktop/scripts/`](/Users/TTAWDTT/Github/Aelin/desktop/scripts): build and packaging helpers.

### Docs

- [`docs/deepagents_arch.md`](/Users/TTAWDTT/Github/Aelin/docs/deepagents_arch.md): source of truth for the current DeepAgents-native architecture.
- [`docs/deepagents_native_shell_todo_20260324.md`](/Users/TTAWDTT/Github/Aelin/docs/deepagents_native_shell_todo_20260324.md): migration history and constraints for this branch direction.
- [`docs/aelin-docs-foundation/`](/Users/TTAWDTT/Github/Aelin/docs/aelin-docs-foundation): stable product/integration docs.
- [`docs/archive/`](/Users/TTAWDTT/Github/Aelin/docs/archive): historical material only. Prefer archiving over deleting.

## How To Run

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m langgraph dev --config langgraph.json --host 127.0.0.1 --port 8000 --no-browser
```

Windows alternative:

```powershell
./scripts/dev-backend.ps1
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Desktop

```bash
cd desktop
npm install
npm run dev
```

## Validation Checklist

Run the smallest relevant checks for the area you changed:

- Backend:

```bash
cd backend
pytest -q
```

- Frontend:

```bash
cd frontend
npm run build
npm run test:unit
```

- Desktop syntax smoke:

```bash
cd desktop
find src scripts -type f -name "*.cjs" -print0 | xargs -0 -n1 node --check
```

Notes:

- CI on [`ci.yml`](/Users/TTAWDTT/Github/Aelin/.github/workflows/ci.yml) only runs on pushes/PRs against `main`, with path-based splitting for backend, frontend, and desktop.
- Desktop packaging commands are heavier:
  - `npm run pack`
  - `npm run dist`
  - `npm run dist:full`

## Change Guidance

When editing this repo, prefer these habits:

- Start from the current architecture docs, not old archived plans.
- If a chat change touches both sides, trace the full path:
  - frontend `useChatStream`
  - Agent Server thread/run APIs
  - runtime resolver
  - DeepAgents graph/tool registration
- Keep `sessionId == threadId` semantics intact unless there is a deliberate migration plan.
- Preserve the `AELIN_*` env prefix. `MERCURYDESK_*` exists only as a compatibility fallback.
- Be careful in `backend/deepagents_skills/`: many folders contain bundled third-party assets or schemas. Edit only the specific files needed.
- Keep desktop entrypoints thin. New Electron runtime logic should usually live in extracted runtime modules, not back in `main.cjs`.
- If you touch execute/artifact delivery behavior, preserve the workspace and outputs path boundaries enforced by the DeepAgents delivery path helpers.

## AGENTS.md Naming Trap

This repository-level [`AGENTS.md`](/Users/TTAWDTT/Github/Aelin/AGENTS.md) is a contributor/instruction file for people and coding agents working on the repo.

It is not the same thing as the runtime-mounted `/memory/AGENTS.md` used by DeepAgents during chat runs. The runtime version is user/workspace memory content resolved by the backend. Do not assume changing this repo file will automatically change live chat memory.
