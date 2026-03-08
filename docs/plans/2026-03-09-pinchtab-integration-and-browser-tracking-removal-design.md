# Pinchtab Integration & Browser/Tracking Removal Design

## Background

The `TTAWDTT/plane-multi-service-poc` branch is exploring a lighter, multi-plane external services architecture for Aelin. The previous "browser plane" subsystem and tracking subsystem provided rich automation and long-running tracking, but they introduce extra complexity and are no longer desired in this branch. Instead, Aelin should delegate all browser/computer-use capabilities to a single local service: Pinchtab.

This document focuses on:

- Making Pinchtab the single browser/computer-use path for Aelin.
- Fully removing browser plane and tracking subsystems from the application layer.
- Keeping only the minimal, generic file-memory logic that is still useful.
- Keeping the overall architecture lightweight and easy to operate.

All work described here happens on the current branch, not on `main`.

## Goals

1. **Single browser path via Pinchtab**
   - All "browser" / "computer use" behavior in the agent loop is expressed as `pinchtab` tool calls.
   - The tool chain is standardized as:
     - `launch_instance`
     - `open_tab`
     - then repeated `snapshot` / `text` / `click` as needed.
   - No remaining references to `browser_plane_*` tools or the old browser plane orchestration.

2. **Remove browser plane and tracking subsystems (logic-level)**
   - Delete browser plane and tracking services, routers, and tests.
   - Remove tracking and browser-plane-specific ORM models and Pydantic schemas.
   - Remove UI routing and desktop entry points that point to tracking views.
   - It is acceptable for legacy database tables to remain; the application layer will no longer reference them.

3. **Retain and simplify generic file-memory logic**
   - Keep file-memory / embeddings functionality that is useful independently of tracking (for example general document memory).
   - Remove or refactor any "file memory bridges" that exist solely to support tracking-specific behavior.

4. **Harden Pinchtab client and tool policy while staying lightweight**
   - Make `PinchTabClient` resilient: realistic timeouts, limited retries, and clear error codes.
   - Ensure `pinchtab` is treated as a write tool and controlled by the existing Aelin tool policy.
   - Keep packaging and runtime simple: Aelin does not try to manage browser plane deployments and only expects a reachable Pinchtab HTTP endpoint.

5. **Document and verify end-to-end "Pinchtab controlled by Aelin" flow**
   - Provide documentation on how to install/run Pinchtab for local development.
   - Document how to configure `settings.pinchtab_base_url`.
   - Verify via tests and at least one manual flow that the agent loop uses only the `pinchtab` tool chain to perform browser actions.

## Out of Scope

- Implementing additional Pinchtab features beyond what is needed for Aelin's current browser/computer-use scenarios.
- Making schema-level migrations or dropping legacy database tables.
- Re-introducing a second browser plane implementation; this branch explicitly aims for a single Pinchtab-based path.

## Architecture Overview

### High-Level Data Flow

1. **User request**
   - The user asks Aelin to perform a task that may require browsing or computer-use behaviors.

2. **Agent loop planning & memory**
   - Aelin's planning and memory services decide whether the task requires browser interaction.
   - Instead of choosing between multiple browser planes, the planner only has the `pinchtab` tool available for browser actions.

3. **Pinchtab tool execution**
   - `aelin_tools` exposes a `pinchtab` tool with actions such as:
     - `health`
     - `launch_instance`
     - `open_tab`
     - `snapshot`
     - `text`
     - `click`
   - The tool uses `PinchTabClient` to perform HTTP calls against the Pinchtab service (by default `http://127.0.0.1:9867`, configurable via settings).
   - The agent loop orchestrates a sequence of these actions to complete the browser portion of the task.

4. **Result integration**
   - The results from Pinchtab (`snapshot` images, `text` output, action status) feed back into the Aelin agent loop.
   - The agent loop continues planning and tool use (including memory and non-browser tools) until the task is complete.

### Pinchtab Client & Tool Policy

- `PinchTabClient` wraps the Pinchtab HTTP API.
  - `launch_instance`:
    - Calls `/instances/launch` to create a new instance.
    - Polls `/instances/{id}` until `status == "running"` or a timeout is reached.
    - On success, returns `{ "ok": True, "instance_id": ... }`.
    - On timeout or persistent error, returns `{ "ok": False, "error": "pinchtab_instance_not_ready", ... }`.
  - `open_tab`:
    - Calls `/instances/{instance_id}/tabs/open`.
    - Accepts either `tabId` or `id` from the Pinchtab response.
    - Will include limited retries on transient errors (e.g. network hiccups), then fail with a clear error code.
  - `snapshot`, `text`, `action` (`click` etc.) are thin wrappers to the corresponding Pinchtab API endpoints.

- Tool policy:
  - `aelin_tool_policy` treats `pinchtab` as a write tool.
  - Write quotas and allowlists apply to `pinchtab` just like other write tools.
  - Any logic about "should the agent be allowed to take browser actions" is centralized here.

## Browser Plane & Tracking Removal

### Components to Remove

1. **Routers and services**
   - Tracking router and services:
     - `backend/app/routers/aelin_tracking.py`
     - Tracking autonomy services and helpers.
   - Browser plane services:
     - `backend/app/services/browser_plane*.py`
     - `browser_automation.py`, `browser_exec.py`, runtime and lock stores, auth/risk guards, etc.

2. **Tests**
   - Tests specifically covering browser plane and tracking:
     - `test_aelin_browser_confirm.py`
     - `test_aelin_browser_tasks.py`
     - `test_browser_automation.py`
     - `test_browser_exec.py`
     - Tracking-specific tests if any remain.

3. **ORM models and schemas**
   - Tracking models:
     - `TrackingTarget`, `TrackingSnapshot`, `TrackingChange`.
   - Browser plane models:
     - `browser_plane_checkpoints`, `browser_plane_tasks`, `browser_plane_instances`, `browser_plane_tabs`, `browser_plane_tab_locks`, `browser_plane_artifacts`, etc.
   - Pydantic schemas that are only used by tracking or browser plane features.

4. **Desktop entry points**
   - Desktop/electron code for tracking views:
     - `desktop/src/main.cjs`
     - `desktop/src/window-presets.cjs`
   - Any `/tracking` windows or routes are removed.

### Components to Keep or Refactor

1. **Generic file memory**
   - File-memory related code that is useful independently of tracking should be kept and de-coupled from tracking-specific types.

2. **File-memory bridges**
   - `openviking_bridge.py`:
     - If `TrackingFileMemoryBridge` is only used for tracking, it can be removed.
     - If there is value in a generic "FileMemoryBridge", it can be simplified to operate on generic file-memory structures and kept under a more generic name.

3. **Agent memory and media pipeline**
   - `agent_memory.py`, `agent_memory_utils.py`, `aelin_media_pipeline.py` should be updated to:
     - Stop referencing tracking-specific fields and types.
     - Continue to support general memory and file-based workflows where applicable.

## Pinchtab Runtime & Packaging Strategy

- Aelin will not attempt to clone or build the old browser plane runtime as part of any packaging or startup path.
- Regarding Pinchtab:
  - The repository includes a vendored development copy under `backend/pinchtab_probe_2` that can be used to:
    - Run `go test ./...` for validation.
    - Build and run a local Pinchtab binary for development.
  - For production or typical user installs, Aelin expects:
    - A Pinchtab service available on some host/port.
    - `settings.pinchtab_base_url` (and its corresponding environment variable) pointing to that service.
  - Aelin's backend does not manage Pinchtab's lifecycle directly; operators are responsible for starting/stopping Pinchtab.

## Testing & Verification Strategy

1. **Unit tests for Pinchtab client**
   - Extend `tests/test_pinchtab_client.py`:
     - Cover timeout behavior in `launch_instance`.
     - Cover retry behavior in `open_tab`.
     - Ensure error codes remain stable and informative.

2. **Agent tools & policy tests**
   - Extend or adjust:
     - `tests/test_aelin_tools.py`
     - `tests/test_aelin_tool_policy.py`
   - Ensure:
     - `pinchtab` is classified as a write tool.
     - Only `pinchtab` (and not browser plane tools) is available for browser/computer-use behavior.

3. **Agent loop tests**
   - Update `tests/test_aelin_agent_loop.py` to:
     - Assert that browser-related behavior goes through `pinchtab` tools only.
     - Remove any expectations around browser plane tools.

4. **Regression tests after removal**
   - Run the full backend test suite (`pytest -q`) after:
     - Removing browser plane and tracking models/schemas/services.
     - Updating memory/media related services.

5. **End-to-end sanity check**
   - For local development:
     - Build and run Pinchtab from `backend/pinchtab_probe_2` (or use an installed Pinchtab).
     - Set `pinchtab_base_url` appropriately.
     - Start Aelin backend with Uvicorn.
     - Execute at least one "needs browser" conversation and confirm:
       - Only `pinchtab` tools are invoked.
       - The sequence matches the expected `launch_instance` → `open_tab` → `snapshot`/`text`/`click` pattern.

## Implementation Phasing (High Level)

The implementation will be done in small, focused commits on the current branch:

1. **Commit 1: Pinchtab client hardening**
   - Improve `PinchTabClient` timeout and retry behavior.
   - Add or adjust tests in `tests/test_pinchtab_client.py`.

2. **Commit 2: Agent loop & tools use Pinchtab exclusively**
   - Update agent tools, tool policy, and loop planning to expose and use only the `pinchtab` browser tool.
   - Update related tests to expect `pinchtab` only.

3. **Commit 3: Remove browser plane & tracking subsystems**
   - Remove models, schemas, services, routers, and desktop routes for browser plane and tracking.
   - Keep and de-couple generic file memory logic that is still useful.

4. **Commit 4: Docs & runtime strategy**
   - Update computer-use / architecture docs to describe the Pinchtab-only path and how to run it.

5. **Commit 5 (optional): E2E convenience**
   - Add small scripts or documentation snippets to make it easy to run Pinchtab + Aelin together for local testing.

This document is the design basis for the implementation plan and the subsequent commits on this branch.

