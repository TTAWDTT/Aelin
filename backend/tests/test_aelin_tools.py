from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.aelin_tools as aelin_tools
from app.services.aelin_tools import AelinToolHub
from app.models import Base
from app.services.web_search import WebSearchResult


class _DummyMemory:
    pass


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


def _hub(fake_web: _FakeWebSearch, llm_service=None, db=None) -> AelinToolHub:
    return AelinToolHub(
        db=db,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        llm_service=llm_service,  # type: ignore[arg-type]
    )


def _create_db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal()


def test_web_search_tool_search_and_fetch():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    result = hub.execute(
        "web_search",
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


def test_tool_definitions_are_cached_per_hub_instance():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    first = hub.tool_definitions()
    second = hub.tool_definitions()

    assert first is second


def test_tool_definitions_expose_core_tools_only():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    names = [row["function"]["name"] for row in hub.tool_definitions()]

    assert "web_search" in names
    assert "device" in names
    assert "attachment_search" in names
    assert "google_workspace" in names
    assert "screen_get" in names
    assert "context_get" in names
    assert "profile" in names
    assert "plane" not in names


def test_tool_definitions_only_expose_unified_device_tool():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    names = [row["function"]["name"] for row in hub.tool_definitions()]

    assert "device" in names
    assert "screen_get" in names


def test_screen_get_tool_success(monkeypatch):
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

    result = hub.execute("screen_get", {"max_edge": 1024, "format": "jpeg"})
    assert result["ok"] is True
    assert str(result.get("data_url") or "").startswith("data:image/jpeg;base64,")
    assert result["width"] == 1280


def test_device_tool_supports_supported_device_actions(monkeypatch):
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

    status = hub.execute("device", {"action": "status"})
    assert status["ok"] is True
    assert status["desktop_plugin_reachable"] is True

    opened = hub.execute("device", {"action": "open_url", "url": "https://example.com"})
    assert opened["ok"] is True
    assert opened["opened"] is True

    aelin_opened = hub.execute("device", {"action": "open_aelin", "route": "/"})
    assert aelin_opened["ok"] is True
    assert aelin_opened["route"] == "/"


def test_device_open_url_rejects_non_http_schemes(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    opened_urls: list[str] = []

    monkeypatch.setattr(
        aelin_tools,
        "open_desktop_external_url",
        lambda url: opened_urls.append(url) or {"url": url, "opened": True, "detail": "ok"},
    )

    blocked = hub.execute("device", {"action": "open_url", "url": "file:///C:/Windows/System32/notepad.exe"})

    assert blocked["ok"] is False
    assert blocked["error"] == "invalid_url_scheme"
    assert opened_urls == []


def test_device_tool_rejects_unknown_action():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    result = hub.execute("device", {"action": "capabilities"})

    assert result["ok"] is False
    assert "unsupported device action" in str(result.get("error") or "")


def test_attachment_search_uses_available_ids_fallback():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[3, "2", 3, 0],  # type: ignore[list-item]
    )
    result = hub.execute("attachment_search", {"query": "总结附件"})
    assert result["ok"] is True
    assert result["attachment_ids"] == [2, 3]
    assert fake_attachment.calls[0]["attachment_ids"] == [2, 3]


def test_attachment_search_prefers_explicit_ids():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[9, 10],
    )
    result = hub.execute(
        "attachment_search",
        {"query": "翻译", "attachment_ids": [5, "6", -1], "top_k": 6, "mode": "hybrid"},  # type: ignore[list-item]
    )
    assert result["ok"] is True
    assert result["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["top_k"] == 6
    assert fake_attachment.calls[0]["mode"] == "hybrid"


def test_context_get_reuses_shared_memory_primitives_without_snapshot():
    fake_web = _FakeWebSearch()
    calls = {"get_summary": 0, "list_todos": 0}

    class _Memory:
        def get_summary(self, db, user_id, *, workspace: str = "default"):
            calls["get_summary"] += 1
            return "summary"

        def list_todos(self, db, user_id, *, include_done=True, limit=100, workspace: str = "default"):
            calls["list_todos"] += 1
            return [{"id": 1, "title": "todo", "done": False, "updated_at": "2026-03-11T10:00:00+00:00"}]

    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_Memory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
    )

    result = hub.execute("context_get", {"query": "mail", "max_items": 3})

    assert result["ok"] is True
    assert result["summary"] == "summary"
    assert result["focus_items"] == []
    assert result["todos"][0]["title"] == "todo"
    assert calls["get_summary"] == 1
    assert calls["list_todos"] == 1


def test_google_workspace_tool_runtime_and_auth_status(monkeypatch):
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

    fake_service = _FakeGWS()
    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: fake_service)

    runtime = hub.execute("google_workspace", {"action": "runtime"})
    assert runtime["ok"] is True
    assert runtime["scope"] == "runtime"
    assert runtime["available"] is True
    assert runtime["configured_bin_path"] == "gws"

    auth = hub.execute("google_workspace", {"action": "auth_status"})
    assert auth["scope"] == "auth"
    assert auth["ok"] is False
    assert auth["authenticated"] is False
    assert auth["login_command"] == ["gws", "auth", "login"]


def test_google_workspace_tool_gmail_and_drive_and_calendar_success(monkeypatch):
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

    fake_service = _FakeGWS()
    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: fake_service)

    gmail_list = hub.execute(
        "google_workspace",
        {"action": "gmail_list", "query": "is:unread", "max_results": 5, "include_spam_trash": True},
    )
    assert gmail_list["ok"] is True
    assert gmail_list["scope"] == "gmail"
    assert [item["id"] for item in gmail_list["items"]] == ["m1", "m2"]

    gmail_get = hub.execute(
        "google_workspace",
        {"action": "gmail_get", "message_id": "m1", "format": "minimal"},
    )
    assert gmail_get["ok"] is True
    assert gmail_get["scope"] == "gmail"
    assert gmail_get["item"]["id"] == "m1"

    drive = hub.execute(
        "google_workspace",
        {"action": "drive_list", "query": "name contains 'Spec'", "max_results": 3},
    )
    assert drive["ok"] is True
    assert drive["scope"] == "drive"
    assert drive["items"][0]["name"] == "Spec"

    calendar = hub.execute(
        "google_workspace",
        {"action": "calendar_list", "calendar_id": "primary", "max_results": 4},
    )
    assert calendar["ok"] is True
    assert calendar["scope"] == "calendar"
    assert calendar["items"][0]["summary"] == "Demo"


def test_google_workspace_tool_error_paths_and_write_actions(monkeypatch):
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

    fake_service = _FakeGWS()
    monkeypatch.setattr(aelin_tools, "get_google_workspace_cli_service", lambda: fake_service)

    gmail_list = hub.execute("google_workspace", {"action": "gmail_list"})
    assert gmail_list["ok"] is False
    assert gmail_list["scope"] == "gmail"
    assert "gws_failed:list" in str(gmail_list.get("error") or "")

    drive = hub.execute("google_workspace", {"action": "drive_list"})
    assert drive["ok"] is False
    assert drive["scope"] == "drive"

    calendar = hub.execute("google_workspace", {"action": "calendar_list"})
    assert calendar["ok"] is False
    assert calendar["scope"] == "calendar"

    create_event = hub.execute("google_workspace", {"action": "calendar_create_event"})
    assert create_event["ok"] is False
    assert create_event["scope"] == "calendar"
    assert "gws_failed:calendar_insert" in str(create_event.get("error") or "")

    send = hub.execute("google_workspace", {"action": "gmail_send"})
    assert send["ok"] is False
    assert send["scope"] == "gmail"
    assert "gws_failed:gmail_send" in str(send.get("error") or "")

    draft = hub.execute("google_workspace", {"action": "gmail_draft"})
    assert draft["ok"] is False
    assert draft["scope"] == "gmail"
    assert "gws_failed:gmail_draft" in str(draft.get("error") or "")

    unknown = hub.execute("google_workspace", {"action": "unknown_action"})
    assert unknown["ok"] is False
    assert unknown["error"] == "unsupported_action"


def test_deepagents_device_tool_structured_invocation(monkeypatch):
    """Ensure the DeepAgents-facing device tool uses structured input and delegates correctly."""
    from app.services import deepagents_graph as dag
    from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage

    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    calls: list[dict[str, object]] = []

    def _fake_tool_device(tool_hub, args):  # type: ignore[no-untyped-def]
        # Record the arguments for assertions and return a dummy success.
        calls.append({"tool_hub": tool_hub, "args": dict(args)})
        return {"ok": True, "echo": dict(args)}

    monkeypatch.setattr(dag, "tool_device", _fake_tool_device)

    policy = AelinToolPolicy(
        max_calls_per_round=10,
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, usage = dag.build_chat_tools(tool_hub=hub, policy=policy)
    assert isinstance(usage, ToolPolicyUsage)

    device_tool = next(t for t in tools if t.name == "device")

    # Simulate the way DeepAgents would call the tool: structured payload.
    result = device_tool.invoke({"action": "open_url", "url": "https://example.com"})

    assert result["ok"] is True
    assert calls, "device tool should have been invoked at least once"
    recorded_args = calls[0]["args"]  # type: ignore[assignment]
    assert recorded_args["action"] == "open_url"
    assert recorded_args["url"] == "https://example.com"

    # Tool runs should contain a completed device entry.
    assert any(tr["name"] == "device" and tr["status"] == "completed" for tr in tool_runs)


def test_deepagents_memory_files_include_agents_md(monkeypatch):
    """Ensure build_chat_agent mounts /memory/AGENTS.md as a DeepAgents file."""
    from app.services import deepagents_graph as dag
    from app.services.aelin_tool_policy import AelinToolPolicy, ToolPolicyUsage
    from app.services.aelin_tools import AelinToolHub

    fake_web = _FakeWebSearch()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
    )

    # Avoid creating a real ChatModel / DeepAgents graph in this unit test.
    from app.services import deepagents_loop as dloop

    monkeypatch.setattr(dloop, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag, "create_deep_agent", lambda **kwargs: object())

    policy = AelinToolPolicy(
        max_calls_per_round=4,
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    memory_summary = "User profile: likes agents.\nRecent change: migrated to DeepAgents shell."

    agent, usage, tool_runs, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        tool_hub=hub,
        policy=policy,
        memory_summary=memory_summary,
        skills_root=None,
    )

    assert isinstance(usage, ToolPolicyUsage)
    assert isinstance(files, dict)
    assert "/memory/AGENTS.md" in files
    file_data = files["/memory/AGENTS.md"]
    assert isinstance(file_data, dict)
    content = file_data.get("content")
    assert isinstance(content, list) and content
    text = "\n".join(str(line) for line in content)
    assert "User profile: likes agents." in text


def test_deepagents_skills_files_and_sources(monkeypatch, tmp_path):
    """
    Ensure build_chat_agent mounts DeepAgents skills under /skills/aelin/
    and passes a skills root compatible with SkillsMiddleware.
    """
    from app.services import deepagents_graph as dag
    from app.services.aelin_tool_policy import AelinToolPolicy
    from app.services.aelin_tools import AelinToolHub

    fake_web = _FakeWebSearch()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
    )

    # Avoid creating a real ChatModel / DeepAgents graph in this unit test.
    from app.services import deepagents_loop as dloop

    monkeypatch.setattr(dloop, "_build_chat_model", lambda service, provider: object())

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    policy = AelinToolPolicy(
        max_calls_per_round=4,
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    memory_summary = ""

    agent, usage, tool_runs, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        tool_hub=hub,
        policy=policy,
        memory_summary=memory_summary,
        skills_root=None,
    )

    # create_deep_agent should have been called once with a skills root under /skills/aelin/.
    assert isinstance(agent, object)
    skills_param = captured.get("skills")
    # When DeepAgents skills目录存在时，skills 应为包含唯一根路径的列表。
    assert isinstance(skills_param, list)
    assert "/skills/aelin/" in skills_param  # type: ignore[operator]

    # Files mapping should include SKILL.md for each DeepAgents skill.
    assert isinstance(files, dict)
    skill_paths = [p for p in files.keys() if str(p).startswith("/skills/aelin/")]
    # 至少包含 file-tools 与 google-workspace 这两个技能的 SKILL.md。
    assert any("file-tools/SKILL.md" in p for p in skill_paths)
    assert any("google-workspace/SKILL.md" in p for p in skill_paths)
