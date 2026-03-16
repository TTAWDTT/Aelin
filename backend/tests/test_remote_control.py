from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.feishu_bot as feishu_bot_module
import app.services.qq_bot as qq_bot_module
import app.services.remote_control as remote_control
from app.schemas import AelinChatResponse
from app.settings import settings
from tests.aelin_test_utils import _auth_headers, _create_test_client


def test_remote_control_execute_routes_into_agent_loop_dispatch(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)
    captured: dict[str, object] = {}

    def _fake_dispatch(payload, db, current_user, **kwargs):
        _ = db, current_user, kwargs
        captured["source"] = payload.source
        captured["query"] = payload.query
        captured["workspace"] = payload.workspace
        captured["source_metadata"] = payload.source_metadata
        return AelinChatResponse(
            answer="remote ok",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(remote_control, "dispatch_aelin_chat", _fake_dispatch)

    resp = client.post(
        "/api/v1/aelin/remote-control/execute",
        json={
            "text": "帮我看下当前电脑状态",
            "workspace": "default",
            "source": "feishu_remote",
            "source_user_name": "Tester",
            "source_chat_id": "oc_xxx",
            "source_message_id": "om_xxx",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("status") == "completed"
    response = data.get("response") or {}
    assert response.get("answer") == "remote ok"
    assert captured["source"] == "feishu_remote"
    assert captured["query"] == "帮我看下当前电脑状态"
    assert captured["workspace"] == "default"
    assert (captured["source_metadata"] or {}).get("source_chat_id") == "oc_xxx"


def test_remote_control_execute_reports_agent_loop_failure(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    def _fake_dispatch(payload, db, current_user, **kwargs):
        _ = payload, db, current_user, kwargs
        return AelinChatResponse(
            answer="当前会话仅使用 Agent Loop，但本轮未获得可用结果。请稍后重试，或检查模型配置后再试。",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[
                {
                    "stage": "agent_loop",
                    "status": "failed",
                    "detail": "agent_loop_no_result",
                    "count": 0,
                    "ts": 0,
                }
            ],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(remote_control, "dispatch_aelin_chat", _fake_dispatch)

    resp = client.post(
        "/api/v1/aelin/remote-control/execute",
        json={"text": "帮我做一件事", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("status") == "agent_loop_no_result"


def test_remote_control_status_exposes_unified_device_contract(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        remote_control,
        "device_status_snapshot",
        lambda: {
            "platform": "windows",
            "capabilities": {"desktop_open_url": True},
            "notes": ["note-a"],
            "desktop_plugin_reachable": True,
        },
    )

    resp = client.get("/api/v1/aelin/remote-control/status", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("enabled") is True
    assert data.get("desktop_plugin_reachable") is True
    assert data.get("supported_tools") == ["device", "screen_get"]
    assert data.get("supported_device_actions") == [
        "status",
        "open_url",
        "open_aelin",
    ]


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
        payload = kwargs.get("payload")
        executed.append(str(getattr(payload, "text", "") or ""))
        return AelinChatResponse(
            answer="电脑状态正常",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(feishu_bot_module, "execute_remote_control_request", _fake_execute)
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


def test_qq_bot_private_message_routes_into_remote_control(monkeypatch):
    service = qq_bot_module.QQBotService()
    executed: list[str] = []

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type, exc, tb
            return None

    monkeypatch.setattr(qq_bot_module, "create_session", lambda: _FakeSession())
    monkeypatch.setattr(
        qq_bot_module,
        "resolve_remote_control_user",
        lambda db, **kwargs: SimpleNamespace(id=1, email="local@aelin.local"),
    )

    def _fake_execute(*args, **kwargs):
        payload = kwargs.get("payload")
        executed.append(str(getattr(payload, "text", "") or ""))
        return AelinChatResponse(
            answer="qq ok",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(qq_bot_module, "execute_remote_control_request", _fake_execute)
    monkeypatch.setattr(settings, "qq_bot_allowed_user_ids_csv", "")
    monkeypatch.setattr(settings, "qq_bot_allowed_group_ids_csv", "")
    monkeypatch.setattr(settings, "qq_bot_group_require_prefix", True)

    reply = service.handle_message_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "message_id": 1001,
            "self_id": 3905815465,
            "user_id": 123456,
            "raw_message": "status",
            "sender": {"nickname": "Tester"},
        }
    )
    assert executed == ["status"]
    assert reply is not None
    assert reply.message_type == "private"
    assert reply.user_id == 123456
    assert reply.text == "qq ok"


def test_qq_bot_group_prefix_gate(monkeypatch):
    service = qq_bot_module.QQBotService()
    executed: list[str] = []

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type, exc, tb
            return None

    monkeypatch.setattr(qq_bot_module, "create_session", lambda: _FakeSession())
    monkeypatch.setattr(
        qq_bot_module,
        "resolve_remote_control_user",
        lambda db, **kwargs: SimpleNamespace(id=1, email="local@aelin.local"),
    )

    def _fake_execute(*args, **kwargs):
        payload = kwargs.get("payload")
        executed.append(str(getattr(payload, "text", "") or ""))
        return AelinChatResponse(
            answer="group ok",
            expression="exp-04",
            citations=[],
            actions=[],
            tool_trace=[],
            memory_summary="",
            generated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(qq_bot_module, "execute_remote_control_request", _fake_execute)
    monkeypatch.setattr(settings, "qq_bot_command_prefix", "/aelin")
    monkeypatch.setattr(settings, "qq_bot_group_require_prefix", True)
    monkeypatch.setattr(settings, "qq_bot_allowed_user_ids_csv", "")
    monkeypatch.setattr(settings, "qq_bot_allowed_group_ids_csv", "")

    reply_without_prefix = service.handle_message_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 1002,
            "self_id": 3905815465,
            "user_id": 123456,
            "group_id": 654321,
            "raw_message": "status",
            "sender": {"nickname": "Tester"},
        }
    )
    assert reply_without_prefix is None
    assert executed == []

    reply_with_prefix = service.handle_message_payload(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 1003,
            "self_id": 3905815465,
            "user_id": 123456,
            "group_id": 654321,
            "raw_message": "/aelin status",
            "sender": {"nickname": "Tester"},
        }
    )
    assert reply_with_prefix is not None
    assert reply_with_prefix.message_type == "group"
    assert reply_with_prefix.group_id == 654321
    assert reply_with_prefix.text == "group ok"
    assert executed == ["/aelin status"]
