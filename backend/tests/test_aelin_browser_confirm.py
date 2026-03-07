from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import app.routers.aelin as aelin_router
import app.routers.aelin_chat as aelin_chat_router
import app.services.aelin_browser_confirm_followup as confirm_followup
import app.services.browser_plane as browser_plane_module
from app.services.browser_automation import browser_automation_service
from app.services.browser_plane import browser_plane_adapter
from tests.aelin_test_utils import _auth_headers, _create_test_client

def test_aelin_browser_confirm_restarts_and_retries_when_cdp_restart_required(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    calls = {"count": 0}

    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        _ = user_id, workspace, action, args, scope, profile_id
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": False, "error": "browser_restart_required_for_cdp"}
        return {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked:Profile"}

    monkeypatch.setattr(browser_plane_adapter, "use", _fake_use)
    monkeypatch.setattr(
        browser_plane_adapter,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0, **kwargs: {
            "ok": True,
            "terminated_pids": [12345],
            "killed_pids": [],
            "failed_pids": [],
        },
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "Profile", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert calls["count"] == 2
    tool_result = data.get("tool_result") or {}
    restart = tool_result.get("restart") or {}
    assert bool(restart.get("attempted")) is True
    assert bool(restart.get("ok")) is True
    assert list(restart.get("terminated_pids") or []) == [12345]

def test_aelin_browser_confirm_preserves_selector_args(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    captured: dict[str, Any] = {}

    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["action"] = action
        captured["args"] = dict(args or {})
        captured["scope"] = scope
        captured["profile_id"] = profile_id
        return {"ok": True, "action": action, "scope": scope, "effect_summary": "typed"}

    monkeypatch.setattr(browser_plane_adapter, "use", _fake_use)

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "type",
            "next_call": {
                "tool": "browser_use",
                "action": "type",
                "args": {"selector": "input[name='q']", "value": "aelin", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert str(captured.get("action") or "") == "type"
    assert str(captured.get("scope") or "") == "cdp"
    sent_args = captured.get("args") if isinstance(captured.get("args"), dict) else {}
    assert str(sent_args.get("selector") or "") == "input[name='q']"
    assert bool(sent_args.get("confirm")) is True

def test_confirmed_browser_call_uses_safe_executor_inside_running_loop(monkeypatch):
    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        _ = user_id, workspace, action, args, scope, profile_id
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return {"ok": True, "action": action, "scope": scope, "effect_summary": "clicked"}
        raise RuntimeError("should_not_run_on_event_loop_thread")

    monkeypatch.setattr(browser_plane_module.browser_automation_service, "use", _fake_use)

    async def _run():
        return aelin_chat_router._execute_confirmed_browser_call(
            tool_name="browser_use",
            action="click",
            scope="cdp",
            clean_args={"target": "Profile", "scope": "cdp", "confirm": True},
            user_id=1,
            workspace="default",
        )

    result = asyncio.run(_run())
    assert bool(result.get("ok")) is True
    assert str(result.get("scope") or "") == "cdp"

def test_aelin_browser_confirm_resolves_login_state(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    login_state = browser_automation_service.mark_login_pending(
        user_id=1,
        workspace="default",
        domain="x.com",
        next_call={"tool": "browser_use", "action": "navigate", "args": {"url": "https://x.com/following", "scope": "cdp"}},
    )

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {"ok": True, "action": "navigate", "scope": "cdp", "effect_summary": "navigated", "profile_id": "default:browser"},
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "navigate",
            "login_request_id": str(login_state.get("request_id") or ""),
            "next_call": {
                "tool": "browser_use",
                "action": "navigate",
                "args": {"url": "https://x.com/following", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    resolved = data.get("login_state") if isinstance(data.get("login_state"), dict) else {}
    assert resolved.get("status") == "continued"
    assert resolved.get("domain") == "x.com"

def test_aelin_browser_login_checkpoints_endpoint_lists_pending_items():
    client = _create_test_client()
    headers = _auth_headers(client)

    state = browser_automation_service.mark_login_pending(
        user_id=1,
        workspace="default",
        domain="x.com",
        next_call={"tool": "browser_use", "action": "navigate", "args": {"url": "https://x.com/following", "scope": "cdp"}},
    )
    browser_automation_service.attach_login_resume_context(
        user_id=1,
        workspace="default",
        request_id=str(state.get("request_id") or ""),
        resume_query="继续总结我的关注列表",
        resume_request={"query": "继续总结我的关注列表", "workspace": "default"},
        continue_after_confirm=True,
    )

    resp = client.get("/api/v1/aelin/agent/browser/login-checkpoints?workspace=default", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert int(data.get("total") or 0) >= 1
    items = data.get("items") if isinstance(data.get("items"), list) else []
    target = next((item for item in items if item.get("request_id") == state.get("request_id")), None)
    assert isinstance(target, dict)
    assert target.get("status") == "awaiting_login"
    assert target.get("resume_query") == "继续总结我的关注列表"

def test_aelin_browser_confirm_can_resume_from_stored_login_checkpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    state = browser_automation_service.mark_login_pending(
        user_id=1,
        workspace="default",
        domain="x.com",
        next_call={"tool": "browser_use", "action": "navigate", "args": {"url": "https://x.com/following", "scope": "cdp"}},
    )
    browser_automation_service.attach_login_resume_context(
        user_id=1,
        workspace="default",
        request_id=str(state.get("request_id") or ""),
        resume_query="继续总结我的关注列表",
        resume_request={"query": "继续总结我的关注列表", "workspace": "default"},
        continue_after_confirm=False,
    )

    captured: dict[str, Any] = {}

    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["action"] = action
        captured["args"] = dict(args or {})
        captured["scope"] = scope
        captured["profile_id"] = profile_id
        return {"ok": True, "action": action, "scope": scope, "effect_summary": "navigated"}

    monkeypatch.setattr(browser_plane_adapter, "use", _fake_use)

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "login_request_id": str(state.get("request_id") or ""),
            "continue_after_confirm": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert str(captured.get("action") or "") == "navigate"
    assert str((captured.get("args") or {}).get("url") or "") == "https://x.com/following"
    login_state = data.get("login_state") if isinstance(data.get("login_state"), dict) else {}
    assert login_state.get("status") == "confirmed"

def test_aelin_browser_confirm_retries_when_first_result_is_restart_failed(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    calls = {"count": 0}

    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        _ = user_id, workspace, action, args, scope, profile_id
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "ok": False,
                "error": "browser_restart_failed_for_cdp",
                "restart": {
                    "attempted": True,
                    "ok": False,
                    "error": "cdp_conflict_process_still_running",
                    "remaining_pids": [111],
                },
            }
        return {"ok": True, "action": "scroll", "scope": "cdp", "effect_summary": "scrolled"}

    monkeypatch.setattr(browser_plane_adapter, "use", _fake_use)
    monkeypatch.setattr(
        browser_plane_adapter,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0, **kwargs: {
            "ok": True,
            "terminated_pids": [111],
            "killed_pids": [],
            "failed_pids": [],
        },
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "scroll",
            "next_call": {
                "tool": "browser_use",
                "action": "scroll",
                "args": {"direction": "down", "amount": 600, "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert calls["count"] == 2
    tool_result = data.get("tool_result") or {}
    restart = tool_result.get("restart") or {}
    assert bool(restart.get("attempted")) is True
    assert bool(restart.get("ok")) is True
    assert list(restart.get("terminated_pids") or []) == [111]

def test_aelin_browser_confirm_retries_when_first_result_is_cdp_unavailable_launch_timeout(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    calls = {"count": 0}

    def _fake_use(*, user_id, workspace, action, args, scope, profile_id=""):
        _ = user_id, workspace, action, args, scope, profile_id
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": False, "error": "cdp_unavailable:cdp_launch_timeout"}
        return {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked"}

    monkeypatch.setattr(browser_plane_adapter, "use", _fake_use)
    monkeypatch.setattr(
        browser_plane_adapter,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0, **kwargs: {
            "ok": True,
            "terminated_pids": [],
            "killed_pids": [],
            "failed_pids": [],
        },
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "个人资料", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert calls["count"] == 2
    tool_result = data.get("tool_result") or {}
    restart = tool_result.get("restart") or {}
    assert bool(restart.get("attempted")) is True
    assert bool(restart.get("ok")) is True

def test_aelin_browser_confirm_auto_continues_with_resume_query(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked"},
    )

    captured: dict[str, Any] = {}

    def _fake_dispatch(payload, db, current_user, event_cb=None):
        _ = db, current_user, event_cb
        captured["query"] = str(payload.query or "")
        return aelin_router.AelinChatResponse(
            answer="continuation-ok",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(confirm_followup, "dispatch_followup_chat", lambda payload, user_id: _fake_dispatch(payload, None, None))

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "resume_query": "继续刚才的任务并给出结果",
            "continue_after_confirm": True,
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "个人资料", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert bool(data.get("continued")) is True
    assert str(captured.get("query") or "") == "继续刚才的任务并给出结果"
    followup = data.get("followup_result") or {}
    assert str(followup.get("answer") or "") == "continuation-ok"
    assert bool(data.get("requires_followup")) is False

def test_aelin_browser_confirm_skips_followup_when_auto_continue_is_disabled(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked"},
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "continue_after_confirm": False,
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "个人资料", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert bool(data.get("continued")) is False
    assert bool(data.get("requires_followup")) is False
    assert (data.get("followup_result") or {}) == {}

def test_aelin_browser_confirm_marks_followup_pending_when_auto_continue_fails(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked"},
    )
    monkeypatch.setattr(
        confirm_followup,
        "dispatch_followup_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("resume failed")),
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "resume_query": "继续刚才的任务并给出结果",
            "continue_after_confirm": True,
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "个人资料", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert bool(data.get("continued")) is False
    assert bool(data.get("requires_followup")) is True
    assert str(data.get("continuation_error") or "") == "resume failed"

def test_aelin_browser_confirm_auto_continues_with_resume_request(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {"ok": True, "action": "click", "scope": "cdp", "effect_summary": "clicked"},
    )

    captured: dict[str, Any] = {}

    def _fake_dispatch(payload, db, current_user, event_cb=None):
        _ = db, current_user, event_cb
        captured["query"] = str(payload.query or "")
        captured["history"] = [dict(item) for item in list(payload.history or [])]
        captured["images"] = [dict(item) for item in list(payload.images or [])]
        return aelin_router.AelinChatResponse(
            answer="continuation-resume-request-ok",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(confirm_followup, "dispatch_followup_chat", lambda payload, user_id: _fake_dispatch(payload, None, None))

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "click",
            "resume_request": {
                "query": "继续读取关注列表",
                "workspace": "default",
                "history": [{"role": "user", "content": "我已经登陆了"}],
                "images": [{"data_url": "data:image/png;base64,AAA", "name": "following.png"}],
            },
            "continue_after_confirm": True,
            "next_call": {
                "tool": "browser_use",
                "action": "click",
                "args": {"target": "个人资料", "scope": "cdp"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert bool(data.get("continued")) is True
    assert str(captured.get("query") or "") == "继续读取关注列表"
    assert captured.get("history") == [{"role": "user", "content": "我已经登陆了"}]
    images = captured.get("images") if isinstance(captured.get("images"), list) else []
    assert images and str(images[0].get("name") or "") == "following.png"

def test_aelin_browser_confirm_supports_browser_state_get_and_retries_after_restart(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    calls = {"count": 0}

    def _fake_state_get(*, user_id, workspace, scope, include_dom, include_a11y, max_targets, max_items, pid, profile_id=""):
        _ = user_id, workspace, scope, include_dom, include_a11y, max_targets, max_items, pid, profile_id
        calls["count"] += 1
        return {"ok": True, "scope": "cdp", "url": "https://x.com/home", "title": "X", "session_id": "bs-test"}

    monkeypatch.setattr(browser_plane_adapter, "state_get", _fake_state_get)
    monkeypatch.setattr(
        browser_plane_adapter,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0, **kwargs: {
            "ok": True,
            "probe_reason": "missing_websocket_debugger_url",
            "terminated_pids": [321],
            "killed_pids": [],
            "failed_pids": [],
        },
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "state_get",
            "next_call": {
                "tool": "browser_state_get",
                "action": "state_get",
                "args": {"scope": "cdp", "include_dom": True, "include_a11y": False, "max_targets": 20},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is True
    assert calls["count"] == 1
    tool_result = data.get("tool_result") or {}
    assert str(tool_result.get("scope") or "") == "cdp"
    restart = tool_result.get("restart") or {}
    assert bool(restart.get("attempted")) is True
    assert bool(restart.get("ok")) is True
    assert str(restart.get("probe_reason") or "") == "missing_websocket_debugger_url"

def test_aelin_browser_confirm_state_get_skips_initial_retry_when_restart_fails(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    calls = {"count": 0}

    def _fake_state_get(*, user_id, workspace, scope, include_dom, include_a11y, max_targets, max_items, pid, profile_id=""):
        _ = user_id, workspace, scope, include_dom, include_a11y, max_targets, max_items, pid, profile_id
        calls["count"] += 1
        return {"ok": True, "scope": "cdp", "url": "https://x.com/home", "title": "X", "session_id": "bs-test"}

    monkeypatch.setattr(browser_plane_adapter, "state_get", _fake_state_get)
    monkeypatch.setattr(
        browser_plane_adapter,
        "force_restart_to_cdp",
        lambda timeout_seconds=12.0, **kwargs: {
            "ok": False,
            "error": "cdp_launch_timeout",
            "probe_reason": "url_error:timed out",
            "terminated_pids": [],
            "killed_pids": [],
            "failed_pids": [],
        },
    )

    resp = client.post(
        "/api/v1/aelin/agent/browser/confirm",
        json={
            "workspace": "default",
            "action_kind": "confirm_browser_action",
            "action": "state_get",
            "next_call": {
                "tool": "browser_state_get",
                "action": "state_get",
                "args": {"scope": "cdp", "include_dom": True, "include_a11y": False, "max_targets": 20},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert bool(data.get("ok")) is False
    assert calls["count"] == 0
    tool_result = data.get("tool_result") or {}
    assert str(tool_result.get("error") or "") == "cdp_launch_timeout"
    restart = tool_result.get("restart") or {}
    assert bool(restart.get("attempted")) is True
    assert bool(restart.get("ok")) is False

def test_aelin_notifications_include_pending_browser_login_item():
    client = _create_test_client()
    headers = _auth_headers(client)

    state = browser_automation_service.mark_login_pending(
        user_id=1,
        workspace="default",
        domain="x.com",
        next_call={"tool": "browser_use", "action": "navigate", "args": {"url": "https://x.com/following", "scope": "cdp"}},
    )
    browser_automation_service.attach_login_resume_context(
        user_id=1,
        workspace="default",
        request_id=str(state.get("request_id") or ""),
        resume_query="继续总结我的关注列表",
        resume_request={"query": "继续总结我的关注列表", "workspace": "default"},
        continue_after_confirm=True,
    )

    resp = client.get("/api/v1/aelin/notifications?limit=20", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = data.get("items") if isinstance(data.get("items"), list) else []
    browser_item = next((item for item in items if str(item.get("source") or "") == "browser_login"), None)
    assert isinstance(browser_item, dict)
    assert str(browser_item.get("action_kind") or "") == "confirm_browser_action"
    payload = browser_item.get("action_payload") if isinstance(browser_item.get("action_payload"), dict) else {}
    assert str(payload.get("login_request_id") or "") == str(state.get("request_id") or "")
