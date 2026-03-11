from __future__ import annotations

from types import SimpleNamespace

import app.services.feishu_bot as feishu_bot_module
import app.services.remote_control as remote_control
from app.services.remote_control import RemoteExecutionResult
from app.settings import settings
from tests.aelin_test_utils import _auth_headers, _create_test_client


def test_remote_control_execute_screenshot_and_history(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        remote_control,
        "capture_device_screen",
        lambda **kwargs: {
            "captured_at": "2026-03-10T08:00:00Z",
            "width": 1440,
            "height": 900,
            "saved_path": "C:/Users/test/Pictures/Aelin/captures/screen-demo.jpg",
            "name": "screen-demo.jpg",
        },
    )

    resp = client.post(
        "/api/v1/aelin/remote-control/execute",
        json={"text": "截图", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    assert "已保存到" in str(data.get("reply_text") or "")
    item = data.get("item") or {}
    assert item.get("command_type") == "screenshot"
    assert item.get("status") == "succeeded"

    history = client.get("/api/v1/aelin/remote-control/commands?workspace=default", headers=headers)
    assert history.status_code == 200, history.text
    items = history.json().get("items") or []
    assert items
    assert items[0].get("command_type") == "screenshot"


def test_remote_control_rejects_unknown_command(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    resp = client.post(
        "/api/v1/aelin/remote-control/execute",
        json={"text": "删库跑路", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is False
    assert "可用指令" in str(data.get("reply_text") or "")
    item = data.get("item") or {}
    assert item.get("status") == "rejected"
    assert item.get("command_type") == "unknown"


def test_remote_control_open_url(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        remote_control,
        "open_desktop_external_url",
        lambda url: {"url": url, "opened": True, "detail": "ok"},
    )

    resp = client.post(
        "/api/v1/aelin/remote-control/execute",
        json={"text": "打开网址 https://example.com", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    assert "https://example.com" in str(data.get("reply_text") or "")
    item = data.get("item") or {}
    assert item.get("command_type") == "open_url"
    assert item.get("risk_level") == "medium"


def test_feishu_bot_group_prefix_gate(monkeypatch):
    service = feishu_bot_module.FeishuBotService()
    sent_messages: list[tuple[str, str]] = []
    executed: list[str] = []

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type, exc, tb
            return None

    monkeypatch.setattr(feishu_bot_module, "create_session", lambda: _FakeSession())
    monkeypatch.setattr(
        feishu_bot_module,
        "resolve_remote_control_user",
        lambda db: SimpleNamespace(id=1, email="local@aelin.local"),
    )

    def _fake_execute(*args, **kwargs):
        executed.append(str(kwargs.get("text") or ""))
        return SimpleNamespace(id=1), RemoteExecutionResult(
            ok=True,
            status="succeeded",
            summary="ok",
            reply_text="电脑状态正常",
            result={"ok": True},
        )

    monkeypatch.setattr(feishu_bot_module, "execute_remote_command", _fake_execute)
    monkeypatch.setattr(service, "_send_text", lambda chat_id, text: sent_messages.append((chat_id, text)))
    monkeypatch.setattr(settings, "feishu_bot_command_prefix", "/aelin")
    monkeypatch.setattr(settings, "feishu_bot_group_require_prefix", True)
    monkeypatch.setattr(settings, "feishu_bot_allowed_open_ids_csv", "")
    monkeypatch.setattr(settings, "feishu_bot_allowed_chat_ids_csv", "")

    payload_without_prefix = {
        "event": {
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"状态"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_1"},
                "sender_type": "user",
                "sender_name": "Tester",
            },
        }
    }
    service.handle_message_payload(payload_without_prefix)
    assert executed == []
    assert sent_messages == []

    payload_with_prefix = {
        "event": {
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_1",
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"/aelin 状态"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_1"},
                "sender_type": "user",
                "sender_name": "Tester",
            },
        }
    }
    service.handle_message_payload(payload_with_prefix)
    assert executed == ["/aelin 状态"]
    assert sent_messages == [("oc_1", "电脑状态正常")]

