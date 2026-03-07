from __future__ import annotations

from app.services.browser_plane import browser_plane_adapter
from tests.aelin_test_utils import _auth_headers, _create_test_client


def test_browser_task_create_and_get_roundtrip():
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_use",
            "scope": "external",
            "action": "navigate",
            "input": {"url": "https://example.com", "scope": "external"},
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()
    assert bool(created_payload.get("ok")) is True
    item = created_payload.get("item") or {}
    assert str(item.get("status") or "") == "pending"
    task_id = str(item.get("task_id") or "")
    assert task_id.startswith("btask-")

    fetched = client.get(
        f"/api/v1/aelin/agent/browser/tasks/{task_id}?workspace=default",
        headers=headers,
    )
    assert fetched.status_code == 200, fetched.text
    fetched_item = (fetched.json() or {}).get("item") or {}
    assert str(fetched_item.get("task_id") or "") == task_id
    assert str((fetched_item.get("input") or {}).get("url") or "") == "https://example.com"


def test_browser_task_resume_marks_completed(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_use",
            "scope": "external",
            "action": "navigate",
            "input": {"url": "https://example.com", "scope": "external"},
        },
        headers=headers,
    )
    task_id = str(((created.json() or {}).get("item") or {}).get("task_id") or "")

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {
            "ok": True,
            "scope": "external",
            "effect_summary": "opened_external:https://example.com",
        },
    )

    resumed = client.post(
        f"/api/v1/aelin/agent/browser/tasks/{task_id}/resume?workspace=default",
        headers=headers,
    )
    assert resumed.status_code == 200, resumed.text
    item = (resumed.json() or {}).get("item") or {}
    assert str(item.get("status") or "") == "completed"
    assert str(((item.get("result") or {}).get("effect_summary")) or "") == "opened_external:https://example.com"


def test_browser_task_resume_records_artifact(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_use",
            "scope": "external",
            "action": "navigate",
            "input": {"url": "https://example.com", "scope": "external"},
        },
        headers=headers,
    )
    task_id = str(((created.json() or {}).get("item") or {}).get("task_id") or "")

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {
            "ok": True,
            "scope": "external",
            "effect_summary": "opened_external:https://example.com",
        },
    )

    client.post(
        f"/api/v1/aelin/agent/browser/tasks/{task_id}/resume?workspace=default",
        headers=headers,
    )
    artifacts = client.get(
        f"/api/v1/aelin/agent/browser/artifacts?workspace=default&task_id={task_id}",
        headers=headers,
    )
    assert artifacts.status_code == 200, artifacts.text
    payload = artifacts.json()
    assert int(payload.get("total") or 0) >= 1
    items = payload.get("items") or []
    assert str(items[0].get("kind") or "") == "task_result"


def test_browser_task_resume_marks_blocked_on_login_checkpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_use",
            "scope": "cdp",
            "action": "navigate",
            "input": {"url": "https://x.com/following", "scope": "cdp"},
        },
        headers=headers,
    )
    task_id = str(((created.json() or {}).get("item") or {}).get("task_id") or "")

    monkeypatch.setattr(
        browser_plane_adapter,
        "use",
        lambda **kwargs: {
            "ok": False,
            "error": "auth_permission_required",
            "login_request_id": "blogin-test123",
            "requires_confirmation": True,
        },
    )

    resumed = client.post(
        f"/api/v1/aelin/agent/browser/tasks/{task_id}/resume?workspace=default",
        headers=headers,
    )
    assert resumed.status_code == 200, resumed.text
    item = (resumed.json() or {}).get("item") or {}
    assert str(item.get("status") or "") == "blocked"
    assert str(item.get("checkpoint_request_id") or "") == "blogin-test123"


def test_browser_snapshot_endpoint_uses_task_context(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_state_get",
            "scope": "cdp",
            "action": "state_get",
            "profile_id": "default:default",
            "input": {"include_dom": True, "max_targets": 10},
        },
        headers=headers,
    )
    task_id = str(((created.json() or {}).get("item") or {}).get("task_id") or "")

    monkeypatch.setattr(
        browser_plane_adapter,
        "snapshot_get",
        lambda **kwargs: {
            "ok": True,
            "scope": "cdp",
            "task_id": kwargs.get("task_id", ""),
            "profile_id": "default:default",
            "url": "https://example.com",
            "title": "Example",
        },
    )

    snap = client.get(
        f"/api/v1/aelin/agent/browser/snapshot?workspace=default&task_id={task_id}&include_dom=true",
        headers=headers,
    )
    assert snap.status_code == 200, snap.text
    payload = snap.json()
    assert bool(payload.get("ok")) is True
    assert str(payload.get("task_id") or "") == task_id
    assert str((payload.get("snapshot") or {}).get("url") or "") == "https://example.com"


def test_browser_instances_and_tabs_endpoints(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "list_instances",
        lambda **kwargs: {
            "ok": True,
            "items": [
                {
                    "instance_id": "binst-1",
                    "profile_id": "default:default",
                    "session_id": "bs-1",
                    "workspace": "default",
                    "mode": "cdp",
                    "status": "ready",
                    "current_tab_id": "btab-1",
                    "created_at": 1.0,
                    "updated_at": 2.0,
                }
            ],
        },
    )
    monkeypatch.setattr(
        browser_plane_adapter,
        "list_tabs",
        lambda **kwargs: {
            "ok": True,
            "instance_id": "binst-1",
            "profile_id": "default:default",
            "items": [
                {
                    "tab_id": "btab-1",
                    "instance_id": "binst-1",
                    "profile_id": "default:default",
                    "session_id": "bs-1",
                    "workspace": "default",
                    "page_index": 0,
                    "url": "https://example.com",
                    "title": "Example",
                    "is_active": True,
                    "status": "open",
                    "created_at": 1.0,
                    "updated_at": 2.0,
                }
            ],
            "total": 1,
        },
    )

    instances = client.get("/api/v1/aelin/agent/browser/instances?workspace=default", headers=headers)
    assert instances.status_code == 200, instances.text
    assert int(instances.json().get("total") or 0) == 1

    tabs = client.get("/api/v1/aelin/agent/browser/tabs?workspace=default", headers=headers)
    assert tabs.status_code == 200, tabs.text
    assert int(tabs.json().get("total") or 0) == 1
    assert str((tabs.json().get("items") or [{}])[0].get("tab_id") or "") == "btab-1"


def test_browser_open_tab_endpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "open_tab",
        lambda **kwargs: {
            "ok": True,
            "instance_id": "binst-1",
            "profile_id": "default:default",
            "item": {
                "tab_id": "btab-2",
                "instance_id": "binst-1",
                "profile_id": "default:default",
                "session_id": "bs-1",
                "workspace": "default",
                "page_index": 1,
                "url": "https://example.com/new",
                "title": "title:https://example.com/new",
                "is_active": True,
                "status": "open",
                "created_at": 1.0,
                "updated_at": 2.0,
            },
        },
    )

    opened = client.post(
        "/api/v1/aelin/agent/browser/tabs/open",
        json={"workspace": "default", "url": "https://example.com/new", "mode": "cdp"},
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    payload = opened.json()
    assert bool(payload.get("ok")) is True
    assert str((payload.get("item") or {}).get("tab_id") or "") == "btab-2"


def test_browser_tab_text_evaluate_and_screenshot_endpoints(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "tab_text",
        lambda **kwargs: {
            "ok": True,
            "scope": "cdp",
            "instance_id": "binst-1",
            "tab_id": "btab-1",
            "profile_id": "default:default",
            "mode": "readable",
            "text": "Example Domain",
            "char_count": 14,
        },
    )
    monkeypatch.setattr(
        browser_plane_adapter,
        "tab_evaluate",
        lambda **kwargs: {
            "ok": True,
            "scope": "cdp",
            "instance_id": "binst-1",
            "tab_id": "btab-1",
            "profile_id": "default:default",
            "value": {"href": "https://example.com"},
        },
    )
    monkeypatch.setattr(
        browser_plane_adapter,
        "tab_screenshot",
        lambda **kwargs: {
            "ok": True,
            "scope": "cdp",
            "instance_id": "binst-1",
            "tab_id": "btab-1",
            "profile_id": "default:default",
            "format": "png",
            "data_url": "data:image/png;base64,ZmFrZQ==",
            "byte_length": 4,
        },
    )

    text_resp = client.get(
        "/api/v1/aelin/agent/browser/tabs/btab-1/text?workspace=default&mode=readable",
        headers=headers,
    )
    assert text_resp.status_code == 200, text_resp.text
    assert str(text_resp.json().get("text") or "") == "Example Domain"

    eval_resp = client.post(
        "/api/v1/aelin/agent/browser/tabs/btab-1/evaluate",
        json={"workspace": "default", "script": "() => window.location.href"},
        headers=headers,
    )
    assert eval_resp.status_code == 200, eval_resp.text
    assert str((eval_resp.json().get("value") or {}).get("href") or "") == "https://example.com"

    shot_resp = client.get(
        "/api/v1/aelin/agent/browser/tabs/btab-1/screenshot?workspace=default&format=png",
        headers=headers,
    )
    assert shot_resp.status_code == 200, shot_resp.text
    snap = shot_resp.json().get("snapshot") or {}
    assert str(snap.get("data_url") or "").startswith("data:image/png;base64,")


def test_browser_artifact_list_endpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "list_artifacts",
        lambda **kwargs: {
            "ok": True,
            "items": [
                {
                    "artifact_id": 1,
                    "workspace": "default",
                    "task_id": "btask-1",
                    "tab_id": "btab-1",
                    "profile_id": "default:default",
                    "kind": "tab_text",
                    "title": "text:readable",
                    "text_content": "Example Domain",
                    "data": {"char_count": 14},
                    "created_at": 1.0,
                }
            ],
        },
    )

    resp = client.get(
        "/api/v1/aelin/agent/browser/artifacts?workspace=default&task_id=btask-1&kind=tab_text",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert int(payload.get("total") or 0) == 1
    assert str((payload.get("items") or [{}])[0].get("kind") or "") == "tab_text"


def test_browser_tab_lock_endpoints(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        browser_plane_adapter,
        "acquire_tab_lock",
        lambda **kwargs: {
            "ok": True,
            "lock": {
                "tab_id": "btab-1",
                "workspace": "default",
                "owner": "agent-A",
                "reason": "summary",
                "expires_at": 300.0,
                "created_at": 1.0,
                "updated_at": 2.0,
            },
        },
    )
    monkeypatch.setattr(
        browser_plane_adapter,
        "list_tab_locks",
        lambda **kwargs: {
            "ok": True,
            "items": [
                {
                    "tab_id": "btab-1",
                    "workspace": "default",
                    "owner": "agent-A",
                    "reason": "summary",
                    "expires_at": 300.0,
                    "created_at": 1.0,
                    "updated_at": 2.0,
                }
            ],
        },
    )
    monkeypatch.setattr(
        browser_plane_adapter,
        "release_tab_lock",
        lambda **kwargs: {
            "ok": True,
            "released": True,
            "lock": {
                "tab_id": "btab-1",
                "workspace": "default",
                "owner": "agent-A",
                "reason": "summary",
                "expires_at": 300.0,
                "created_at": 1.0,
                "updated_at": 2.0,
            },
        },
    )

    locked = client.post(
        "/api/v1/aelin/agent/browser/tabs/btab-1/lock",
        json={"workspace": "default", "owner": "agent-A", "reason": "summary", "ttl_seconds": 300},
        headers=headers,
    )
    assert locked.status_code == 200, locked.text
    assert bool(locked.json().get("ok")) is True

    listed = client.get("/api/v1/aelin/agent/browser/tabs/locks?workspace=default", headers=headers)
    assert listed.status_code == 200, listed.text
    assert int(listed.json().get("total") or 0) == 1

    unlocked = client.post(
        "/api/v1/aelin/agent/browser/tabs/btab-1/unlock",
        json={"workspace": "default", "owner": "agent-A"},
        headers=headers,
    )
    assert unlocked.status_code == 200, unlocked.text
    assert bool(unlocked.json().get("released")) is True


def test_browser_task_resume_blocks_when_tab_locked(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    created = client.post(
        "/api/v1/aelin/agent/browser/tasks",
        json={
            "workspace": "default",
            "kind": "browser_use",
            "scope": "cdp",
            "action": "click",
            "tab_id": "btab-1",
            "input": {"target": "Submit", "scope": "cdp"},
        },
        headers=headers,
    )
    task_id = str(((created.json() or {}).get("item") or {}).get("task_id") or "")

    monkeypatch.setattr(
        browser_plane_adapter,
        "get_tab_lock",
        lambda **kwargs: {
            "ok": True,
            "lock": {
                "tab_id": "btab-1",
                "workspace": "default",
                "owner": "agent-B",
                "reason": "other-agent",
                "expires_at": 300.0,
                "created_at": 1.0,
                "updated_at": 2.0,
            },
        },
    )

    resumed = client.post(
        f"/api/v1/aelin/agent/browser/tasks/{task_id}/resume?workspace=default",
        headers=headers,
    )
    assert resumed.status_code == 200, resumed.text
    item = (resumed.json() or {}).get("item") or {}
    assert str(item.get("status") or "") == "blocked"
    assert str(((item.get("result") or {}).get("error")) or "") == "tab_locked"
