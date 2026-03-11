# Pinchtab Integration & Browser/Tracking Removal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Pinchtab the only browser/computer-use path for Aelin and completely remove browser plane and tracking subsystems, while keeping generic file-memory logic and keeping the system lightweight.

**Architecture:** Aelin’s agent loop will call a single `pinchtab` tool that wraps a hardened `PinchTabClient`. All legacy browser plane and tracking code, models, and routes will be removed, leaving only generic memory/file-memory components. Operators run Pinchtab as a separate local service and configure `pinchtab_base_url`.

**Tech Stack:** FastAPI, Python 3, SQLAlchemy, Pytest, Go (for vendored Pinchtab), Electron (desktop shell).

---

## Task 1: Commit design & plan docs

**Files:**
- Create: `docs/plans/2026-03-09-pinchtab-integration-and-browser-tracking-removal-design.md` (already created)
- Create: `docs/plans/2026-03-09-pinchtab-integration-and-browser-tracking-removal-plan.md` (this file)

**Step 1: Verify docs contents**

Manually skim both new files to ensure they match the agreed design and implementation outline.

**Step 2: Git add docs**

Run:

```bash
cd backend/..
git add docs/plans/2026-03-09-pinchtab-integration-and-browser-tracking-removal-design.md docs/plans/2026-03-09-pinchtab-integration-and-browser-tracking-removal-plan.md
```

**Step 3: Commit**

Run:

```bash
git commit -m "docs: add pinchtab integration and browser/tracking removal design"
```

Expected: One new commit on `TTAWDTT/plane-multi-service-poc` containing only these docs.

---

## Task 2: Harden Pinchtab client (Commit 1)

**Files:**
- Modify: `backend/app/services/pinchtab_client.py`
- Modify/Add tests: `backend/tests/test_pinchtab_client.py`

### Step 1: Inspect current Pinchtab client and tests

1. Open `backend/app/services/pinchtab_client.py` and understand:
   - Current `PinchTabClient` methods and error handling.
   - How `_get` and `_post` are implemented.
2. Open `backend/tests/test_pinchtab_client.py` and note:
   - Existing tests for `open_tab` behavior.
   - Existing tests for `launch_instance` polling.

### Step 2: Extend `launch_instance` with timeout and better error semantics

Implementation sketch for `backend/app/services/pinchtab_client.py`:

```python
import time

class PinchTabClient:
    def __init__(self, base_url: str, *, launch_max_attempts: int = 10, launch_poll_interval: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.launch_max_attempts = launch_max_attempts
        self.launch_poll_interval = launch_poll_interval

    def launch_instance(self) -> dict:
        out = self._post("/instances/launch", {})
        if not out.get("ok"):
            return out

        payload = out.get("payload") or {}
        inst_id = payload.get("id")
        if not inst_id:
            return {"ok": False, "error": "pinchtab_missing_instance_id", "raw": out}

        last_status = None
        for _ in range(self.launch_max_attempts):
            inst = self._get_instance(inst_id)
            if not inst.get("ok"):
                last_status = inst
                time.sleep(self.launch_poll_interval)
                continue

            data = inst.get("payload") or {}
            last_status = data.get("status")
            if last_status == "running":
                return {"ok": True, "instance_id": inst_id}

            time.sleep(self.launch_poll_interval)

        return {
            "ok": False,
            "error": "pinchtab_instance_not_ready",
            "instance_id": inst_id,
            "last_status": last_status,
        }
```

Adjust the exact structure to fit the existing client style.

### Step 3: Add retry behavior for `open_tab`

Implementation sketch in `backend/app/services/pinchtab_client.py`:

```python
class PinchTabClient:
    def __init__(self, base_url: str, *, open_tab_max_attempts: int = 3, open_tab_retry_interval: float = 0.5, **kwargs):
        # existing fields...
        self.open_tab_max_attempts = open_tab_max_attempts
        self.open_tab_retry_interval = open_tab_retry_interval

    def open_tab(self, instance_id: str, url: str) -> dict:
        last_error = None
        for attempt in range(self.open_tab_max_attempts):
            out = self._post(f"/instances/{instance_id}/tabs/open", {"url": url})
            if out.get("ok"):
                payload = out.get("payload") or {}
                tab_id = payload.get("tabId") or payload.get("id")
                if not tab_id:
                    return {"ok": False, "error": "pinchtab_missing_tab_id", "raw": out}
                return {"ok": True, "tab_id": tab_id}

            last_error = out
            # consider only retrying on certain error codes if needed
            time.sleep(self.open_tab_retry_interval)

        if last_error is not None:
            return last_error
        return {"ok": False, "error": "pinchtab_open_tab_failed"}
```

### Step 4: Add tests for timeout and retry behavior

Update `backend/tests/test_pinchtab_client.py`:

1. Add a test that simulates an instance never reaching `"running"`:

```python
def test_launch_instance_times_out_and_reports_not_ready(monkeypatch):
    calls = {"count": 0}

    class _ClientUnderTest(PinchTabClient):
        def _post(self, path, body):
            assert path == "/instances/launch"
            return {"ok": True, "payload": {"id": "i-1"}}

        def _get_instance(self, instance_id):
            calls["count"] += 1
            return {"ok": True, "payload": {"status": "starting"}}

    client = _ClientUnderTest("http://example", launch_max_attempts=3, launch_poll_interval=0.0)
    out = client.launch_instance()
    assert out["ok"] is False
    assert out["error"] == "pinchtab_instance_not_ready"
    assert out["instance_id"] == "i-1"
    assert calls["count"] == 3
```

2. Add a test that exercises `open_tab` retry logic:

```python
def test_open_tab_retries_on_failure(monkeypatch):
    calls = {"count": 0}

    class _ClientUnderTest(PinchTabClient):
        def _post(self, path, body):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"ok": False, "error": "pinchtab_http_error: 500"}
            return {"ok": True, "payload": {"tabId": "t-1"}}

    client = _ClientUnderTest("http://example", open_tab_max_attempts=3, open_tab_retry_interval=0.0)
    out = client.open_tab("i-1", "https://example.com")
    assert out["ok"] is True
    assert out["tab_id"] == "t-1"
    assert calls["count"] == 2
```

Adjust names to be consistent with existing tests.

### Step 5: Run tests

Run:

```bash
cd backend
pytest -q tests/test_pinchtab_client.py
```

Expected: All tests in `test_pinchtab_client.py` pass.

### Step 6: Commit

Run:

```bash
cd backend/..
git add backend/app/services/pinchtab_client.py backend/tests/test_pinchtab_client.py
git commit -m "feat(pinchtab): harden client launch and open_tab behavior"
```

---

## Task 3: Pinchtab as the only browser tool in agent tools/policy/loop (Commit 2)

**Files:**
- Modify: `backend/app/services/aelin_tools.py`
- Modify: `backend/app/services/aelin_tool_policy.py`
- Modify: `backend/app/services/aelin_loop_tools.py`
- Modify (as needed): `backend/app/services/aelin_agent_loop.py`
- Modify (as needed): `backend/app/services/aelin_core.py`
- Modify (as needed): `backend/app/services/aelin_chat_planning.py`
- Modify (as needed): `backend/app/services/aelin_chat_memory.py`
- Tests:
  - Modify: `backend/tests/test_aelin_tools.py`
  - Modify: `backend/tests/test_aelin_tool_policy.py`
  - Modify: `backend/tests/test_aelin_agent_loop.py`

### Step 1: Inspect current pinchtab tool integration

1. Open `backend/app/services/aelin_tools.py`:
   - Confirm the `pinchtab` tool definition and actions.
   - Check that no `browser_plane_*` tools are still present.
2. Open `backend/app/services/aelin_tool_policy.py`:
   - Confirm `pinchtab` is classified as a write tool.
   - Look for any remaining references to browser plane tools.
3. Open `backend/app/services/aelin_loop_tools.py`:
   - Understand how it assembles the tool list for different contexts.
   - Identify any old browser plane tool names or flags.

### Step 2: Update agent tools to expose only `pinchtab` for browser use

In `backend/app/services/aelin_tools.py`:

1. Ensure the only browser/computer-use tool is named `pinchtab`.
2. Remove any definitions or branches related to `browser_plane_*` or legacy browser tools.
3. Ensure `_tool_pinchtab` is the only path used for browser actions and that it:
   - Validates required arguments for each `action`.
   - Calls the correct `PinchTabClient` methods.
   - Returns structured error responses on invalid inputs or client errors.

### Step 3: Ensure tool policy treats pinchtab correctly

In `backend/app/services/aelin_tool_policy.py`:

1. Confirm `classify_tool_call("pinchtab", ...)` returns a write classification.
2. Remove any legacy conditions that reference browser plane tools.
3. Ensure `AelinToolPolicy` write quotas include `pinchtab` consistently with other write tools.

### Step 4: Make loop tools/agent loop planning use only pinchtab

In `backend/app/services/aelin_loop_tools.py`:

1. Find the function(s) that assemble available tools for the agent loop.
2. Remove any browser plane tools from the lists.
3. Verify that `pinchtab` is included wherever browser/computer-use tools are allowed.

In `backend/app/services/aelin_agent_loop.py`, `aelin_core.py`, `aelin_chat_planning.py`, `aelin_chat_memory.py`:

1. Search for `browser_plane`, `browser_` (excluding pinchtab), and tracking-related references.
2. Remove or update any logic that:
   - Chooses between multiple browser implementations.
   - Emits tool calls with legacy browser tool names.
3. Ensure that planning code that decides “should we use a browser” now:
   - Only ever emits `pinchtab` tool calls.
   - Follows the expected sequence: `launch_instance` → `open_tab` → `snapshot`/`text`/`click`.

### Step 5: Update tests

In `backend/tests/test_aelin_tools.py`:

1. Remove or update any tests that still reference old browser plane tools.
2. Add or adjust tests to:
   - Confirm `pinchtab` tool wiring and argument validation.

In `backend/tests/test_aelin_tool_policy.py`:

1. Remove tests for browser plane tool classification.
2. Ensure tests confirm that:
   - `pinchtab` is a write tool.
   - Write quotas for `pinchtab` behave as expected.

In `backend/tests/test_aelin_agent_loop.py`:

1. Remove browser plane specific assertions.
2. Ensure at least one test asserts that:

```python
{"name": "pinchtab", "arguments": '{"action":"click","tab_id":"t1","ref":"btn"}'}
```

   is present (or similar) to verify the loop uses `pinchtab`.

### Step 6: Run tests

Run:

```bash
cd backend
pytest -q tests/test_aelin_tools.py tests/test_aelin_tool_policy.py tests/test_aelin_agent_loop.py
```

Expected: All tests pass.

### Step 7: Commit

Run:

```bash
cd backend/..
git add backend/app/services/aelin_tools.py backend/app/services/aelin_tool_policy.py backend/app/services/aelin_loop_tools.py backend/app/services/aelin_agent_loop.py backend/app/services/aelin_core.py backend/app/services/aelin_chat_planning.py backend/app/services/aelin_chat_memory.py backend/tests/test_aelin_tools.py backend/tests/test_aelin_tool_policy.py backend/tests/test_aelin_agent_loop.py
git commit -m "feat(aelin-loop): route browser use exclusively through pinchtab"
```

---

## Task 4: Remove browser plane & tracking subsystems (Commit 3)

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Delete/confirm delete: browser plane and tracking services/routers already marked `D` in git status.
- Modify: `backend/app/services/aelin_core.py`
- Modify: `backend/app/services/aelin_chat_planning.py`
- Modify: `backend/app/services/aelin_chat_memory.py`
- Modify: `backend/app/services/openviking_bridge.py`
- Modify: `backend/app/services/agent_memory.py`
- Modify: `backend/app/services/agent_memory_utils.py`
- Modify: `backend/app/services/aelin_media_pipeline.py`
- Modify: `desktop/src/main.cjs`
- Modify: `desktop/src/window-presets.cjs`
- Tests: remove/confirm delete any remaining tracking/browser plane tests.

### Step 1: Remove ORM models

In `backend/app/models.py`:

1. Search for tracking models:
   - `TrackingTarget`, `TrackingSnapshot`, `TrackingChange`.
2. Search for browser plane models:
   - `browser_plane_checkpoints`, `browser_plane_tasks`, `browser_plane_instances`, `browser_plane_tabs`, `browser_plane_tab_locks`, `browser_plane_artifacts`, etc.
3. Remove these classes and related relationships.
4. Leave a brief comment near other models if useful, e.g.:

```python
# Note: legacy tracking/browser-plane tables may still exist in some databases, but
# the application layer no longer defines ORM models or uses them.
```

### Step 2: Remove schemas

In `backend/app/schemas.py`:

1. Use search (e.g. `rg "Tracking" backend/app/schemas.py`) to find tracking-only schemas.
2. Remove Pydantic models that are only used by tracking or browser plane features.
3. Ensure any remaining schemas compile without referencing removed models.

### Step 3: Clean up core/planning/memory services

In `backend/app/services/aelin_core.py`:

1. Remove helper functions that depend directly on tracking/browser plane models, for example:
   - `_build_cached_tracking_snapshot`
   - `_build_planner_tracking_snapshot`
   - `_detect_forced_tracking_create`
2. Remove branches that auto-generate tracking actions (e.g. `open_tracking`).
3. Keep generic file-memory or conversation memory logic that is still useful.

In `backend/app/services/aelin_chat_planning.py`:

1. Remove fields like `tracking_snapshot`, `tracking_intent`, or `should_suggest_tracking`.
2. Simplify planners to focus on:
   - General tool use.
   - Memory and retrieval that is not tracking-specific.

In `backend/app/services/aelin_chat_memory.py`:

1. Remove tracking-specific memory handling (e.g. saving tracking snapshots).
2. Keep generic memory management (chat history, document references, etc.).

### Step 4: Simplify or remove file-memory bridges

In `backend/app/services/openviking_bridge.py`:

1. Inspect `TrackingFileMemoryBridge` and related functions.
2. If they are only used by tracking:
   - Remove the class and any references to it.
3. If there is a useful generic pattern:
   - Extract a simpler `FileMemoryBridge` that:
     - Operates on generic file memory representations.
     - Does not depend on tracking models or tracking-specific embeddings.

Update any callers in `agent_memory.py`, `agent_memory_utils.py`, or `aelin_media_pipeline.py` to use the generic bridge (or remove the calls if they were tracking-only).

### Step 5: Clean up desktop routing

In `desktop/src/main.cjs` and `desktop/src/window-presets.cjs`:

1. Remove any `/tracking` windows or routes.
2. Ensure desktop bootstrap does not try to open tracking-specific pages.

### Step 6: Remove leftover tests and references

1. Ensure browser plane/tracking tests are deleted or excluded:
   - `backend/tests/test_aelin_browser_confirm.py`
   - `backend/tests/test_aelin_browser_tasks.py`
   - `backend/tests/test_browser_automation.py`
   - `backend/tests/test_browser_exec.py`
   - Any other tracking-only tests.
2. Search across the repo for `tracking_` and `browser_plane`:

```bash
rg "tracking_" backend
rg "browser_plane" backend desktop
```

3. Remove or adjust any remaining references so that code compiles.

### Step 7: Run tests

Run:

```bash
cd backend
pytest -q
```

Expected: Full backend test suite passes.

Optionally, for desktop:

```bash
cd desktop
npm install
npm run build
```

Expected: Desktop build does not reference tracking routes.

### Step 8: Commit

Run:

```bash
cd backend/..
git add backend/app/models.py backend/app/schemas.py backend/app/services/aelin_core.py backend/app/services/aelin_chat_planning.py backend/app/services/aelin_chat_memory.py backend/app/services/openviking_bridge.py backend/app/services/agent_memory.py backend/app/services/agent_memory_utils.py backend/app/services/aelin_media_pipeline.py desktop/src/main.cjs desktop/src/window-presets.cjs
git add -u  # include deleted tracking/browser plane files and tests
git commit -m "chore: remove browser plane and tracking subsystems"
```

---

## Task 5: Docs & runtime strategy (Commit 4)

**Files:**
- Modify: `docs/computer_use.md`
- Modify: `docs/aelin_computer_use_v1_spec_20260303.md`
- Optionally modify: `docs/architecture_v2.md`

### Step 1: Update computer_use.md

In `docs/computer_use.md`:

1. Describe the new architecture where:
   - Aelin uses Pinchtab as the sole browser/computer-use provider.
   - The main flow is `launch_instance` → `open_tab` → `snapshot` / `text` / `click`.
2. Document how to configure and run Pinchtab:

```text
1. Build or install Pinchtab (e.g. from backend/pinchtab_probe_2 or via a package).
2. Run Pinchtab locally (default: http://127.0.0.1:9867).
3. Set the environment variable for Aelin backend, e.g.:
   - PINCHTAB_BASE_URL=http://127.0.0.1:9867
4. Start Aelin backend; the agent loop will now call Pinchtab for browser actions.
```

3. Remove or update any references to:
   - The old browser plane.
   - Tracking-specific browser automation.

### Step 2: Update aelin_computer_use_v1_spec_20260303.md

In `docs/aelin_computer_use_v1_spec_20260303.md`:

1. Ensure the spec matches the new Pinchtab-only flow:
   - Tools and actions reflect `pinchtab` tool names.
2. Clarify:
   - Any assumptions about Pinchtab availability.
   - Error behaviors (e.g. what happens when Pinchtab is down).
3. Remove any residual references to browser plane or tracking-specific automation.

### Step 3: Optionally update architecture_v2.md

In `docs/architecture_v2.md` (if browser/tracking are mentioned):

1. Replace old browser plane diagrams/sections with:
   - A simplified diagram showing Aelin → Pinchtab → web.
2. Note that tracking subsystem has been removed in this branch.

### Step 4: Commit

Run:

```bash
cd backend/..
git add docs/computer_use.md docs/aelin_computer_use_v1_spec_20260303.md docs/architecture_v2.md
git commit -m "docs: document pinchtab-based computer use and removal of tracking/browser-plane"
```

---

## Task 6: End-to-end verification and optional helpers (Commit 5)

**Files:**
- Optional new helper script: `backend/scripts/run_pinchtab_and_aelin_dev.sh` (or `.ps1` for Windows)
- Optional docs snippet: update `docs/Next Step.md` or another dev guide.

### Step 1: Verify Go environment and Pinchtab tests

Run:

```bash
cd backend/pinchtab_probe_2
go version
go test ./...
```

Expected:
- `go version` prints a valid version.
- All tests in `pinchtab_probe_2` pass.

### Step 2: Build and run Pinchtab locally

From `backend/pinchtab_probe_2`:

```bash
go build ./cmd/pinchtab
./pinchtab  # or pinchtab.exe on Windows
```

Confirm it listens on port `9867` (or configured port).

### Step 3: Run Aelin backend with Pinchtab

In a separate terminal:

```bash
cd backend
set PINCHTAB_BASE_URL=http://127.0.0.1:9867  # Windows PowerShell / cmd equivalent
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Step 4: Manual browser-use sanity check

1. Use an API client or UI to send a test conversation that requires browser actions.
2. Observe backend logs:
   - Confirm only `pinchtab` tools are invoked.
   - Confirm a sensible sequence: `launch_instance` → `open_tab` → `snapshot`/`text`/`click`.

### Step 5: Optional helper script

Create `backend/scripts/run_pinchtab_and_aelin_dev.ps1` with:

```powershell
Start-Process -FilePath "pinchtab.exe" -WorkingDirectory "..\pinchtab_probe_2"
$env:PINCHTAB_BASE_URL = "http://127.0.0.1:9867"
python -m uvicorn app.main:app --reload --port 8000
```

Adjust paths as needed for the local environment.

### Step 6: Commit (optional)

If helper scripts or doc snippets were added:

```bash
cd backend/..
git add backend/scripts/run_pinchtab_and_aelin_dev.ps1 docs/Next Step.md
git commit -m "chore: add dev helper for running pinchtab with aelin"
```

---

Plan complete and saved to `docs/plans/2026-03-09-pinchtab-integration-and-browser-tracking-removal-plan.md`. In this session we will effectively follow a "subagent-driven" approach manually by executing each task in order: docs commit, Pinchtab client hardening, pinchtab-only agent loop wiring, subsystem removal, docs refresh, and final end-to-end verification, all on the current branch `TTAWDTT/plane-multi-service-poc`.

