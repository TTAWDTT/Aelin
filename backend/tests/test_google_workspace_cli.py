from __future__ import annotations

import base64
import json
import subprocess

from app.services.foundation.google_workspace_cli import GoogleWorkspaceCliService


def test_auth_status_uses_gws_and_parses_json(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws", config_dir="D:/cfg", timeout_seconds=9.0)

    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "C:/tools/gws.exe")

    calls: list[dict[str, object]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "authenticated": True,
                    "email": "owner@example.com",
                    "scopes": ["gmail.readonly", "drive.readonly"],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("app.services.foundation.google_workspace_cli.subprocess.run", fake_run)

    result = service.auth_status()

    assert result["ok"] is True
    assert result["available"] is True
    assert result["authenticated"] is True
    assert result["email"] == "owner@example.com"
    assert result["scopes"] == ["gmail.readonly", "drive.readonly"]
    assert result["next_action"] == "ready"
    assert result["configured_bin_path"] == "gws"
    assert result["resolved_bin_path"] == "C:/tools/gws.exe"
    # 当能够解析到实际可执行路径时，login_command 应该提示这一真实路径，避免 gws 不在 PATH 时的误导。
    assert result["login_command"] == ["C:/tools/gws.exe", "auth", "login"]
    assert calls and calls[0]["cmd"] == ["C:/tools/gws.exe", "auth", "status"]
    assert calls[0]["env"]["GWS_CONFIG_DIR"] == "D:/cfg"


def test_gmail_list_builds_expected_params(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    captured: list[list[str]] = []

    def fake_run_json(args: list[str], *, timeout_seconds: float | None = None):
        captured.append(args)
        return {"ok": True, "data": {"messages": [{"id": "m1"}, {"id": "m2"}]}}

    monkeypatch.setattr(service, "_run_json", fake_run_json)

    result = service.gmail_list_messages(query="is:unread label:inbox", max_results=7, include_spam_trash=True)

    assert result["ok"] is True
    assert [item["id"] for item in result["items"]] == ["m1", "m2"]
    assert captured
    params = json.loads(captured[0][-1])
    assert captured[0][:-1] == ["gmail", "users", "messages", "list", "--params"]
    assert params["userId"] == "me"
    assert params["maxResults"] == 7
    assert params["q"] == "is:unread label:inbox"
    assert params["includeSpamTrash"] is True


def test_drive_and_calendar_list_extract_items(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    def fake_run_json(args: list[str], *, timeout_seconds: float | None = None):
        if args[:3] == ["drive", "files", "list"]:
            return {"ok": True, "data": {"files": [{"id": "f1", "name": "Roadmap"}]}}
        if args[:3] == ["calendar", "events", "list"]:
            return {"ok": True, "data": {"items": [{"id": "e1", "summary": "Demo"}]}}
        raise AssertionError(args)

    monkeypatch.setattr(service, "_run_json", fake_run_json)

    drive = service.drive_list_files(query="name contains 'Roadmap'", max_results=3)
    events = service.calendar_list_events(calendar_id="primary", max_results=4)

    assert drive["ok"] is True
    assert drive["items"][0]["name"] == "Roadmap"
    assert events["ok"] is True
    assert events["items"][0]["summary"] == "Demo"


def test_gmail_send_message_builds_mime_and_calls_cli(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    captured: dict[str, object] = {}

    def fake_run_json(args: list[str], *, timeout_seconds: float | None = None):
        captured["args"] = args
        captured["body"] = json.loads(args[-1])
        return {"ok": True, "data": {"id": "msg-1"}}

    monkeypatch.setattr(service, "_run_json", fake_run_json)

    result = service.gmail_send_message(
        to=["alice@example.com"],
        cc=["bob@example.com"],
        bcc=[],
        subject="Hello",
        body="Hi there",
    )

    assert result["ok"] is True
    assert isinstance(captured.get("args"), list)
    args = captured["args"]  # type: ignore[assignment]
    assert args[:4] == ["gmail", "users", "messages", "send"]
    assert args[4] == "--json"
    body = captured["body"]  # type: ignore[assignment]
    assert "raw" in body
    raw = str(body["raw"])
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    text = decoded.decode("utf-8", errors="ignore")
    assert "To: alice@example.com" in text
    assert "Cc: bob@example.com" in text
    assert "Subject: Hello" in text
    assert "Hi there" in text


def test_gmail_create_draft_builds_message_wrapper(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    captured: dict[str, object] = {}

    def fake_run_json(args: list[str], *, timeout_seconds: float | None = None):
        captured["args"] = args
        captured["body"] = json.loads(args[-1])
        return {"ok": True, "data": {"id": "draft-1"}}

    monkeypatch.setattr(service, "_run_json", fake_run_json)

    result = service.gmail_create_draft(
        to=["alice@example.com"],
        cc=[],
        bcc=[],
        subject="Draft",
        body="Draft body",
    )

    assert result["ok"] is True
    args = captured["args"]  # type: ignore[assignment]
    assert args[:4] == ["gmail", "users", "drafts", "create"]
    assert args[4] == "--json"
    body = captured["body"]  # type: ignore[assignment]
    assert "message" in body
    raw = str(body["message"]["raw"])
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    text = decoded.decode("utf-8", errors="ignore")
    assert "To: alice@example.com" in text
    assert "Subject: Draft" in text
    assert "Draft body" in text


def test_calendar_create_event_builds_insert_call(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    captured: dict[str, object] = {}

    def fake_run_json(args: list[str], *, timeout_seconds: float | None = None):
        captured["args"] = args
        # args layout: ["calendar","events","insert","--params", params_json, "--json", event_json]
        captured["params"] = json.loads(args[4])
        captured["event"] = json.loads(args[6])
        return {"ok": True, "data": {"id": "evt-1", "summary": "Demo"}}

    monkeypatch.setattr(service, "_run_json", fake_run_json)

    result = service.calendar_create_event(
        calendar_id="primary",
        summary="Demo event",
        description="desc",
        start="2026-03-15T10:00:00+08:00",
        end="2026-03-15T11:00:00+08:00",
        attendees=["a@example.com", "b@example.com"],
    )

    assert result["ok"] is True
    args = captured["args"]  # type: ignore[assignment]
    assert args[:3] == ["calendar", "events", "insert"]
    assert args[3] == "--params"
    assert args[5] == "--json"
    params = captured["params"]  # type: ignore[assignment]
    event = captured["event"]  # type: ignore[assignment]
    assert params["calendarId"] == "primary"
    assert event["summary"] == "Demo event"
    assert event["start"]["dateTime"].startswith("2026-03-15T10:00:00")
    assert event["end"]["dateTime"].startswith("2026-03-15T11:00:00")
    attendees = event.get("attendees") or []
    emails = sorted([row["email"] for row in attendees])
    assert emails == ["a@example.com", "b@example.com"]


def test_service_reports_missing_binary(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")
    # Force _resolve_bin_path to simulate missing CLI binary even if gws is installed.
    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "")
    result = service._run_json(["auth", "status"])
    assert result["ok"] is False
    assert result["error"] == "gws_not_installed"


def test_auth_status_reports_install_guidance_when_binary_missing(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")
    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "")

    result = service.auth_status()

    assert result["ok"] is False
    assert result["error"] == "gws_not_installed"
    assert result["available"] is False
    assert result["next_action"] == "install"
    assert result["login_command"] == ["gws", "auth", "login"]
    assert "未安装 gws" in result["install_hint"]


def test_auth_status_treats_missing_authenticated_as_unauthenticated(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws", config_dir="D:/cfg", timeout_seconds=9.0)

    # 模拟已安装但返回的 JSON 中没有 authenticated 字段。
    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "C:/tools/gws.exe")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    # 没有 authenticated 字段，只返回 email / scopes，这种情况下应视为“未登录”。
                    "email": "owner@example.com",
                    "scopes": ["gmail.readonly"],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("app.services.foundation.google_workspace_cli.subprocess.run", fake_run)

    result = service.auth_status()

    assert result["ok"] is True
    assert result["available"] is True
    assert result["authenticated"] is False
    assert result["next_action"] == "login"


def test_run_json_timeout_returns_error(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    # Pretend gws is installed so _run_json actually invokes subprocess.run.
    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "C:/tools/gws.exe")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 10.0))

    monkeypatch.setattr("app.services.foundation.google_workspace_cli.subprocess.run", fake_run)

    result = service._run_json(["auth", "status"])

    assert result["ok"] is False
    assert result["error"] == "gws_timeout"


def test_run_json_invalid_json_reports_error(monkeypatch):
    service = GoogleWorkspaceCliService(bin_path="gws")

    monkeypatch.setattr(service, "_resolve_bin_path", lambda: "C:/tools/gws.exe")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="this is not json",
            stderr="",
        )

    monkeypatch.setattr("app.services.foundation.google_workspace_cli.subprocess.run", fake_run)

    result = service._run_json(["gmail", "users", "messages", "list", "--params", "{}"])

    assert result["ok"] is False
    assert result["error"] == "gws_invalid_json"
    # raw payload should be present for debugging
    assert "raw" in result

