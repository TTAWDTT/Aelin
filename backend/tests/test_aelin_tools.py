from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
from app.services.aelin_tools import AelinToolHub
from app.services.web_search import WebSearchResult
from app.services.tools_device import tool_device, tool_screen_get
from app.services.tools_files import tool_attachment_search
from app.services.tools_gws import tool_google_workspace
from app.services.tools_web import tool_web_search


class _FakeWebSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def search(self, query: str, *, max_results: int = 6):
        self.calls.append(("search", query, int(max_results), 0))
        return [
            WebSearchResult(
                title="Search Title",
                url="https://example.com/a",
                snippet="snippet a",
                provider="duckduckgo_lite",
                fetch_mode="none",
                rank=1,
            )
        ]

    def search_and_fetch(self, query: str, *, max_results: int = 6, fetch_top_k: int = 3):
        self.calls.append(("search_and_fetch", query, int(max_results), int(fetch_top_k)))
        return [
            WebSearchResult(
                title="Fetched Title",
                url="https://example.com/b",
                snippet="snippet b",
                provider="bing_html",
                fetch_mode="http",
                rank=1,
                fetched_excerpt="fetched excerpt",
            )
        ]


class _FakeAttachmentService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, db, *, user_id: int, workspace: str, query: str, attachment_ids: list[int], top_k: int, mode: str):
        self.calls.append(
            {
                "db": db,
                "user_id": user_id,
                "workspace": workspace,
                "query": query,
                "attachment_ids": list(attachment_ids),
                "top_k": top_k,
                "mode": mode,
            }
        )
        return {
            "ok": True,
            "attachment_ids": list(attachment_ids),
            "total": 1,
            "content": "[1] chunk text",
            "hits": [
                {
                    "chunk_id": 11,
                    "text": "chunk text",
                    "score": 1.0,
                    "citation": {"attachment_id": attachment_ids[0], "file_name": "demo.docx"},
                    "metadata": {"loc": {"page": 1}},
                }
            ],
        }


def _hub(fake_web: _FakeWebSearch, *, llm_service=None, attachment_service=None, available_attachment_ids=None) -> AelinToolHub:
    return AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=attachment_service,  # type: ignore[arg-type]
        available_attachment_ids=available_attachment_ids,
        llm_service=llm_service,  # type: ignore[arg-type]
    )


def test_web_search_tool_search_and_fetch():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    result = tool_web_search(
        hub,
        {
            "action": "search_and_fetch",
            "query": "DeepAgents 架构",
            "max_results": 3,
            "fetch_top_k": 2,
        },
    )

    assert result["ok"] is True
    assert result["total"] == 1
    assert result["action"] == "search_and_fetch"
    assert result["providers"] == ["bing_html"]
    assert result["items"][0]["fetch_mode"] == "http"
    assert fake_web.calls[0] == ("search_and_fetch", "DeepAgents 架构", 3, 2)


def test_attachment_search_uses_available_ids_fallback():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = _hub(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[3, "2", 3, 0],  # type: ignore[list-item]
    )

    result = tool_attachment_search(hub, {"query": "总结附件"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [2, 3]
    assert fake_attachment.calls[0]["attachment_ids"] == [2, 3]


def test_attachment_search_prefers_explicit_ids():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = _hub(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[9, 10],
    )

    result = tool_attachment_search(
        hub,
        {"query": "翻译", "attachment_ids": [5, "6", -1], "top_k": 6, "mode": "hybrid"},  # type: ignore[list-item]
    )

    assert result["ok"] is True
    assert result["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["top_k"] == 6
    assert fake_attachment.calls[0]["mode"] == "hybrid"


def test_screen_get_tool_success(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools,
        "device_capture_screen",
        lambda **kwargs: {
            "data_url": "data:image/jpeg;base64,QUJDRA==",
            "name": "screen-demo.jpg",
            "width": 1280,
            "height": 720,
            "source_display": "1",
            "captured_at": "2026-03-04T01:00:00Z",
        },
    )

    result = tool_screen_get(hub, {"max_edge": 1024, "format": "jpeg"})
    assert result["ok"] is True
    assert str(result.get("data_url") or "").startswith("data:image/jpeg;base64,")
    assert result["width"] == 1280


def test_device_tool_supports_supported_device_actions(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(
        aelin_tools,
        "device_status_snapshot",
        lambda: {
            "platform": "windows",
            "capabilities": {"desktop_open_url": True, "desktop_activate_module": False},
            "notes": ["note-a"],
            "desktop_plugin_reachable": True,
            "desktop_plugin_configured": True,
        },
    )
    monkeypatch.setattr(
        aelin_tools,
        "open_desktop_external_url",
        lambda url: {"url": url, "opened": True, "detail": "ok"},
    )
    monkeypatch.setattr(
        aelin_tools,
        "activate_desktop_module",
        lambda route: {"route": route, "url": f"http://desktop.local{route}", "opened": True, "detail": "ok"},
    )

    status = tool_device(hub, {"action": "status"})
    assert status["ok"] is True
    assert status["desktop_plugin_reachable"] is True

    opened = tool_device(hub, {"action": "open_url", "url": "https://example.com"})
    assert opened["ok"] is True
    assert opened["opened"] is True

    aelin_opened = tool_device(hub, {"action": "open_aelin", "route": "/"})
    assert aelin_opened["ok"] is True
    assert aelin_opened["route"] == "/"


def test_device_open_url_rejects_non_http_schemes(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    opened_urls: list[str] = []

    monkeypatch.setattr(
        aelin_tools,
        "open_desktop_external_url",
        lambda url: opened_urls.append(url) or {"url": url, "opened": True, "detail": "ok"},
    )

    blocked = tool_device(hub, {"action": "open_url", "url": "file:///C:/Windows/System32/notepad.exe"})

    assert blocked["ok"] is False
    assert blocked["error"] == "invalid_url_scheme"
    assert opened_urls == []


def test_device_tool_rejects_unknown_action():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    result = tool_device(hub, {"action": "capabilities"})

    assert result["ok"] is False
    assert "unsupported device action" in str(result.get("error") or "")


def test_google_workspace_tool_runtime_and_auth_status(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    class _FakeGWS:
        def runtime_status(self):
            return {
                "ok": True,
                "available": True,
                "configured_bin_path": "gws",
                "resolved_bin_path": "C:/tools/gws.exe",
            }

        def auth_status(self):
            return {
                "ok": False,
                "authenticated": False,
                "available": True,
            }

        def login_command(self):
            return ["gws", "auth", "login"]

    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: _FakeGWS())

    runtime = tool_google_workspace(hub, {"action": "runtime"})
    assert runtime["ok"] is True
    assert runtime["scope"] == "runtime"
    assert runtime["available"] is True

    auth = tool_google_workspace(hub, {"action": "auth_status"})
    assert auth["scope"] == "auth"
    assert auth["ok"] is False
    assert auth["authenticated"] is False
    assert auth["login_command"] == ["gws", "auth", "login"]


def test_google_workspace_tool_gmail_and_drive_and_calendar_success(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    class _FakeGWS:
        def runtime_status(self):
            return {"ok": True, "available": True}

        def gmail_list_messages(self, **kwargs):
            return {"ok": True, "items": [{"id": "m1"}, {"id": "m2"}], "raw": {"messages": []}}

        def gmail_get_message(self, **kwargs):
            return {"ok": True, "item": {"id": "m1", "snippet": "hello"}, "raw": {"id": "m1"}}

        def drive_list_files(self, **kwargs):
            return {"ok": True, "items": [{"id": "f1", "name": "Spec"}], "raw": {"files": []}}

        def calendar_list_events(self, **kwargs):
            return {"ok": True, "items": [{"id": "e1", "summary": "Demo"}], "raw": {"items": []}}

    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: _FakeGWS())

    gmail_list = tool_google_workspace(
        hub,
        {"action": "gmail_list", "query": "is:unread", "max_results": 5, "include_spam_trash": True},
    )
    assert gmail_list["ok"] is True
    assert gmail_list["scope"] == "gmail"
    assert [item["id"] for item in gmail_list["items"]] == ["m1", "m2"]

    gmail_get = tool_google_workspace(hub, {"action": "gmail_get", "message_id": "m1", "format": "minimal"})
    assert gmail_get["ok"] is True
    assert gmail_get["item"]["id"] == "m1"

    drive = tool_google_workspace(hub, {"action": "drive_list", "query": "name contains 'Spec'", "max_results": 3})
    assert drive["ok"] is True
    assert drive["items"][0]["name"] == "Spec"

    calendar = tool_google_workspace(hub, {"action": "calendar_list", "calendar_id": "primary", "max_results": 4})
    assert calendar["ok"] is True
    assert calendar["items"][0]["summary"] == "Demo"


def test_google_workspace_tool_error_paths_and_write_actions(monkeypatch):
    from app.services import aelin_tools

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    class _FakeGWS:
        def gmail_list_messages(self, **kwargs):
            return {"ok": False, "error": "gws_failed:list"}

        def drive_list_files(self, **kwargs):
            return {"ok": False, "error": "gws_failed:drive"}

        def calendar_list_events(self, **kwargs):
            return {"ok": False, "error": "gws_failed:calendar"}

        def calendar_create_event(self, **kwargs):
            return {"ok": False, "error": "gws_failed:calendar_insert"}

        def gmail_send_message(self, **kwargs):
            return {"ok": False, "error": "gws_failed:gmail_send"}

        def gmail_create_draft(self, **kwargs):
            return {"ok": False, "error": "gws_failed:gmail_draft"}

    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: _FakeGWS())

    assert tool_google_workspace(hub, {"action": "gmail_list"})["scope"] == "gmail"
    assert tool_google_workspace(hub, {"action": "drive_list"})["scope"] == "drive"
    assert tool_google_workspace(hub, {"action": "calendar_list"})["scope"] == "calendar"
    assert tool_google_workspace(hub, {"action": "calendar_create_event"})["scope"] == "calendar"
    assert tool_google_workspace(hub, {"action": "gmail_send"})["scope"] == "gmail"
    assert tool_google_workspace(hub, {"action": "gmail_draft"})["scope"] == "gmail"
    unknown = tool_google_workspace(hub, {"action": "unknown_action"})
    assert unknown["ok"] is False
    assert unknown["error"] == "unsupported_action"


def test_deepagents_build_chat_tools_uses_explicit_registered_tools(monkeypatch):
    from app.services import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    calls: list[dict[str, object]] = []

    def _fake_tool_device(tool_hub, args):  # type: ignore[no-untyped-def]
        calls.append({"tool_hub": tool_hub, "args": dict(args)})
        return {"ok": True, "echo": dict(args)}

    monkeypatch.setattr(dag, "tool_device", _fake_tool_device)

    policy = AelinToolPolicy(
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, usage = dag.build_chat_tools(tool_hub=hub, policy=policy)

    assert isinstance(usage, ToolPolicyUsage)
    assert [tool.name for tool in tools] == [
        "web_search",
        "attachment_search",
        "google_workspace",
        "device",
        "screen_get",
    ]

    device_tool = next(t for t in tools if t.name == "device")
    result = device_tool.invoke({"action": "open_url", "url": "https://example.com"})

    assert result["ok"] is True
    assert calls
    assert calls[0]["args"] == {"action": "open_url", "url": "https://example.com"}
    assert any(tr["name"] == "device" and tr["status"] == "completed" for tr in tool_runs)


def test_deepagents_build_chat_tools_wraps_generic_tool_exceptions(monkeypatch):
    from app.services import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(dag, "tool_web_search", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    policy = AelinToolPolicy(
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )

    tools, tool_runs, usage = dag.build_chat_tools(tool_hub=hub, policy=policy)
    web_tool = next(t for t in tools if t.name == "web_search")
    result = web_tool.invoke({"action": "search", "query": "deepagents"})

    assert result["ok"] is False
    assert "web_search_failed:boom" in str(result.get("error") or "")
    assert usage.total_calls == 1
    assert tool_runs[0]["call_index"] == 1


def test_deepagents_memory_files_include_agents_md(monkeypatch):
    from app.services import deepagents_graph as dag
    from app.services import deepagents_loop as dloop

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(dloop, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag, "create_deep_agent", lambda **kwargs: object())

    policy = AelinToolPolicy(
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    agent, usage, tool_runs, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        tool_hub=hub,
        policy=policy,
        memory_summary="User profile: likes agents.\nRecent change: migrated to DeepAgents shell.",
        skills_root=None,
    )

    assert isinstance(agent, object)
    assert isinstance(usage, ToolPolicyUsage)
    assert isinstance(files, dict)
    assert "/memory/AGENTS.md" in files
    content = files["/memory/AGENTS.md"].get("content")
    assert isinstance(content, list) and "User profile: likes agents." in "\n".join(str(line) for line in content)


def test_deepagents_skills_mount_full_directory_tree(monkeypatch, tmp_path):
    from app.services import deepagents_graph as dag
    from app.services import deepagents_loop as dloop

    skill_root = Path(tmp_path) / "skills"
    chrome_skill = skill_root / "chrome_cdp"
    scripts_dir = chrome_skill / "scripts"
    refs_dir = chrome_skill / "references"
    scripts_dir.mkdir(parents=True)
    refs_dir.mkdir(parents=True)

    (chrome_skill / "SKILL.md").write_text(
        "---\nname: chrome-cdp\ndescription: Browser automation skill\n---\n\nUse scripts/cdp.mjs.\n",
        encoding="utf-8",
    )
    (scripts_dir / "cdp.mjs").write_text("console.log('ok')\n", encoding="utf-8")
    (refs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(dloop, "_build_chat_model", lambda service, provider: object())

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    policy = AelinToolPolicy(
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    _, _, _, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        tool_hub=hub,
        policy=policy,
        memory_summary="",
        skills_root=skill_root,
    )

    skills_param = captured.get("skills")
    assert isinstance(skills_param, list)
    assert "/skills/aelin/" in skills_param  # type: ignore[operator]
    assert "/skills/aelin/chrome-cdp/SKILL.md" in files
    assert "/skills/aelin/chrome-cdp/scripts/cdp.mjs" in files
    assert "/skills/aelin/chrome-cdp/references/guide.md" in files
