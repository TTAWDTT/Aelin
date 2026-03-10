# Browser Plane Auth & Risk Guards Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract browser auth and high‑risk action guard logic from `BrowserAutomationService` into focused helper modules while preserving external behavior and APIs.

**Architecture:** Keep `BrowserAutomationService` as the single orchestration entrypoint used by `browser_plane_adapter`, but delegate login checkpoint management and high‑risk action confirmation payload building to two new helpers (`BrowserAuthGuard`, `BrowserRiskGuard`). State (login_states/trusted_auth_domains) remains owned by `BrowserAutomationService` and injected into the auth helper to avoid cyclic imports. Public methods like `mark_login_pending`, `get_login_state`, and `resolve_login_pending` are preserved as thin proxies.

**Tech Stack:** Python 3, FastAPI backend, Playwright (sync), SQLite via SQLAlchemy.

---

### Task 1: Inspect current auth and risk guard logic

**Files:**
- Read: `backend/app/services/browser_automation.py:1`
- Read: `backend/app/services/browser_plane_store.py:1`

**Steps:**
- Locate `BrowserLoginState` dataclass and all methods dealing with login checkpoints (`mark_login_pending`, `get_login_state`, `attach_login_resume_context`, `list_login_states`, `cancel_login_pending`, `resolve_login_pending`).
- Locate `_RISK_KEYWORDS` and `_is_high_risk` plus the confirmation payload block in `use`.
- Verify which call sites depend on these public methods (e.g. via `browser_plane_adapter` and `/agent/browser/*` routers).

### Task 2: Create `browser_runtime_auth_guard.py` module

**Files:**
- Create: `backend/app/services/browser_runtime_auth_guard.py`
- Modify: `backend/app/services/browser_automation.py:1`

**Steps:**
- Move `BrowserLoginState` dataclass definition into the new module unchanged.
- Implement a `BrowserAuthGuard` class that:
  - Accepts references to `login_states` and `trusted_auth_domains` dicts and a shared `threading.RLock` in `__init__`.
  - Implements methods `mark_login_pending`, `get_login_state`, `attach_login_resume_context`, `list_login_states`, `cancel_login_pending`, and `resolve_login_pending` by moving existing logic from `BrowserAutomationService`, keeping all interactions with `browser_plane_store` and logging.
  - On `resolve_login_pending`, updates `trusted_auth_domains[(user_id, workspace, profile_id)]` with the resolved domain (lower‑cased), wrapped in best‑effort error handling.
- In `browser_automation.py`, remove the local `BrowserLoginState` definition and import it plus `BrowserAuthGuard` from the new module.

### Task 3: Wire `BrowserAuthGuard` into `BrowserAutomationService`

**Files:**
- Modify: `backend/app/services/browser_automation.py:1`

**Steps:**
- Ensure `BrowserAutomationService.__init__` still defines:
  - `self._login_states: dict[str, BrowserLoginState] = {}`.
  - `self._trusted_auth_domains: dict[tuple[int, str, str], set[str]] = {}`.
- Instantiate `self._auth_guard = BrowserAuthGuard(login_states=self._login_states, trusted_auth_domains=self._trusted_auth_domains, lock=self._lock)`.
- Replace the original login‑checkpoint methods with thin proxies that delegate to `self._auth_guard.*`, preserving method names and signatures so that `browser_plane_adapter` and tests continue to work unchanged.

### Task 4: Create `browser_runtime_risk_guard.py` module

**Files:**
- Create: `backend/app/services/browser_runtime_risk_guard.py`
- Modify: `backend/app/services/browser_automation.py:1`

**Steps:**
- Move `_RISK_KEYWORDS` constant and `_is_high_risk` logic into the new module.
- Implement a `BrowserRiskGuard` class with:
  - `check_high_risk(action: str, args: dict[str, Any]) -> dict[str, Any] | None` that:
    - Extracts `target/value/url` from `args`.
    - Returns `None` if `confirm` is already true or `_is_high_risk` returns False.
    - Otherwise builds and returns the same `confirmation_required` payload currently assembled in `BrowserAutomationService.use` (including `next_call.tool="browser_use"` and updated `args["confirm"]=True`).
- In `BrowserAutomationService.__init__`, instantiate `self._risk_guard = BrowserRiskGuard()`.

### Task 5: Refactor `BrowserAutomationService.use` to use guards

**Files:**
- Modify: `backend/app/services/browser_automation.py:1`

**Steps:**
- Remove the inline high‑risk confirmation block and replace it with a call to `self._risk_guard.check_high_risk(action=act, args=args)`, returning the payload when not `None`.
- Keep the sensitive‑domain guard (`_SENSITIVE_AUTH_DOMAINS` and `_is_sensitive_auth_domain`) in `BrowserAutomationService` for now, but ensure all login checkpoint work is executed via `self._auth_guard` (i.e. calls to `mark_login_pending` and `resolve_login_pending` are proxies).
- Confirm the `use` return payload remains structurally identical for existing paths (navigate/click/type/scroll/wait across scopes).

### Task 6: Run focused backend tests

**Files:**
- Test: `backend/tests/test_browser_automation.py`
- Test: `backend/tests/test_aelin_browser_confirm.py`
- Test: `backend/tests/test_aelin_tools.py`

**Steps:**
- From `backend/`, run:
  - `pytest backend/tests/test_browser_automation.py -q`
  - `pytest backend/tests/test_aelin_browser_confirm.py -q`
  - `pytest backend/tests/test_aelin_tools.py -q`
- If the host Python environment still hits the known `asyncio/_overlapped` issue before collection, capture the error message and note it in the eventual PR body as an environment limitation, not a regression.

### Task 7: Prepare chore PR

**Files:**
- Modify (staged): `backend/app/services/browser_automation.py`
- Add (staged): `backend/app/services/browser_runtime_auth_guard.py`
- Add (staged): `backend/app/services/browser_runtime_risk_guard.py`
- Add (staged): `docs/plans/2026-03-08-browser-plane-auth-risk-guards.md`

**Steps:**
- Ensure only relevant source and plan files are staged (exclude `.codex/`, logs, databases, and other unrelated artifacts).
- Commit with message: `chore(browser-plane): extract auth and risk guards`.
- Use `gh pr create --base main --head TTAWDTT/browser-plane-cleanup --title "chore(browser-plane): extract auth and risk guards"` and include a PR body summarizing the refactor and test commands (with any environment caveats).

