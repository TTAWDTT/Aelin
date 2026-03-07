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
