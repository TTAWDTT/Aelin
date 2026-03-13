from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.aelin_tools as aelin_tools
import app.services.aelin_planes as aelin_planes
import app.services.plane_runtime as plane_runtime
from app.services.aelin_tools import AelinToolHub, _PINCHTAB_SESSIONS, _PINCHTAB_USER_SESSIONS
from app.models import Base
from app.services.web_search import WebSearchResult


class _DummyMemory:
    pass


class _DummyTracking:
    pass


class _DummyFileMemory:
    pass


class _FakeLLMCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        # Record the call and return a minimal JSON plan with a single open+text.
        self.calls.append(kwargs)
        content = '{"steps":[{"action":"open","url":"https://example.com"},{"action":"text"}]}'
        return type(
            "Resp",
            (object,),
            {
                "choices": [
                    type(
                        "Choice",
                        (object,),
                        {"message": type("Msg", (object,), {"content": content})()},
                    )()
                ]
            },
        )()


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


class _FakePinchTabClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def health(self) -> dict[str, object]:
        self.calls.append(("health", {}))
        return {"ok": True, "status": "healthy"}

    def launch_instance(self) -> dict[str, object]:
        self.calls.append(("launch_instance", {}))
        return {"ok": True, "instance_id": "inst-1"}

    def open_tab(self, *, instance_id: str, url: str) -> dict[str, object]:
        self.calls.append(("open_tab", {"instance_id": instance_id, "url": url}))
        return {"ok": True, "tab_id": "tab-1"}

    def snapshot(self, *, tab_id: str) -> dict[str, object]:
        self.calls.append(("snapshot", {"tab_id": tab_id}))
        return {"ok": True, "data": {"title": "Example"}}

    def text(self, *, tab_id: str, mode: str = "readable") -> dict[str, object]:
        self.calls.append(("text", {"tab_id": tab_id, "mode": mode}))
        return {"ok": True, "text": "page text"}

    def action(self, *, tab_id: str, kind: str, ref: str | None = None, **kwargs: object) -> dict[str, object]:
        payload: dict[str, object] = {"tab_id": tab_id, "kind": kind}
        if ref is not None:
            payload["ref"] = ref
        payload.update(kwargs)
        self.calls.append(("action", payload))
        return {"ok": True, "effect": "clicked"}


def _patch_pinchtab_runtime(monkeypatch, fake_client: _FakePinchTabClient) -> None:
    monkeypatch.setattr(aelin_tools, "ensure_pinchtab_started", lambda: {"ok": True, "status": "running"})
    monkeypatch.setattr(aelin_tools, "get_pinchtab_client", lambda: fake_client)


def _hub(fake_web: _FakeWebSearch, llm_service=None, db=None) -> AelinToolHub:
    return AelinToolHub(
        db=db,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
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


def test_web_search_tool_search_and_fetch():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    result = hub.execute(
        "web_search",
        {
            "action": "search_and_fetch",
            "query": "DeepSeek 4.0",
            "max_results": 3,
            "fetch_top_k": 2,
        },
    )
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["action"] == "search_and_fetch"
    assert result["providers"] == ["bing_html"]
    assert result["items"][0]["fetch_mode"] == "http"
    assert fake_web.calls[0] == ("search_and_fetch", "DeepSeek 4.0", 3, 2)


def test_tool_definitions_are_cached_per_hub_instance():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    first = hub.tool_definitions()
    second = hub.tool_definitions()

    assert first is second


def test_tool_definitions_only_expose_unified_device_tool():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    names = [row["function"]["name"] for row in hub.tool_definitions()]

    assert "device" in names
    assert "screen_get" in names
    assert "device_status" not in names
    assert "device_processes" not in names
    assert "device_mode_apply" not in names
    assert "desktop_open_url" not in names
    assert "desktop_open_aelin" not in names


def test_tool_definitions_expose_plane_instead_of_pinchtab_family():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    names = [row["function"]["name"] for row in hub.tool_definitions()]

    assert "plane" in names
    assert "pinchtab" not in names
    assert "pinchtab_agent" not in names
    assert "pinchtab_session" not in names


def test_tool_definitions_expose_skill_tool():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    names = [row["function"]["name"] for row in hub.tool_definitions()]

    assert "skill" in names


def test_plane_registry_exposes_browser_entry_and_catalog_metadata():
    entry = plane_runtime.get_plane_registry_entry("browser")
    assert entry is not None
    assert entry.metadata.slug == "browser"
    assert entry.metadata.backing_system == "PinchTab"
    assert entry.metadata.skill_slug == "pinchtab"

    catalog = aelin_planes.plane_catalog_entries()
    assert catalog
    browser = next(row for row in catalog if row.get("plane") == "browser")
    assert browser["backing_system"] == "PinchTab"
    assert browser["skill_slug"] == "pinchtab"
    prompt = aelin_planes.plane_catalog_prompt()
    assert "usage_skill=pinchtab" in prompt
    assert "catalog 只描述 plane 的能力边界" in prompt


def test_skill_tool_supports_catalog_and_read():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    catalog = hub.execute("skill", {"action": "catalog", "query": "浏览器网页登录"})
    assert catalog["ok"] is True
    assert int(catalog.get("total") or 0) >= 1
    items = catalog.get("items")
    assert isinstance(items, list)
    assert any(str(item.get("slug") or "") == "pinchtab" for item in items if isinstance(item, dict))

    read = hub.execute("skill", {"action": "read", "slug": "pinchtab"})
    assert read["ok"] is True
    assert read["slug"] == "pinchtab"
    assert "[AELIN SKILL]" in str(read.get("prompt") or "")


def test_web_search_tool_missing_query():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    result = hub.execute("web_search", {"action": "search", "query": ""})
    assert result["ok"] is False
    assert "missing query" in str(result.get("error") or "")
    assert fake_web.calls == []


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


def test_device_tool_supports_all_device_actions(monkeypatch):
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
        "device_collect_process_items",
        lambda *, sort_by, limit: [
            SimpleNamespace(pid=321, name="Code.exe", cpu_percent=12.5, memory_mb=640.0, anomaly_score=0.3, safe_to_terminate=True)
        ],
    )
    monkeypatch.setattr(
        aelin_tools,
        "device_apply_mode",
        lambda mode: {
            "mode": mode,
            "status": "applied",
            "summary": f"{mode} ok",
            "steps": ["step-a"],
            "warnings": [],
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

    processes = hub.execute("device", {"action": "processes", "sort_by": "memory", "limit": 5})
    assert processes["ok"] is True
    assert processes["items"][0]["pid"] == 321
    assert processes["sort_by"] == "memory"

    mode = hub.execute("device", {"action": "mode_apply", "mode": "focus"})
    assert mode["ok"] is True
    assert mode["status"] == "applied"
    assert mode["steps"] == ["step-a"]

    opened = hub.execute("device", {"action": "open_url", "url": "https://example.com"})
    assert opened["ok"] is True
    assert opened["opened"] is True

    aelin_opened = hub.execute("device", {"action": "open_aelin", "route": "/processes"})
    assert aelin_opened["ok"] is True
    assert aelin_opened["route"] == "/processes"


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


def test_device_tool_dispatches_to_internal_handlers(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    monkeypatch.setattr(aelin_tools.AelinToolHub, "_tool_device_status", lambda self, args: {"ok": True, "summary": "status"})
    monkeypatch.setattr(aelin_tools.AelinToolHub, "_tool_device_processes", lambda self, args: {"ok": True, "items": [{"pid": 1}]})
    monkeypatch.setattr(aelin_tools.AelinToolHub, "_tool_device_mode_apply", lambda self, args: {"ok": True, "mode": "focus"})
    monkeypatch.setattr(aelin_tools.AelinToolHub, "_tool_desktop_open_url", lambda self, args: {"ok": True, "url": args["url"]})
    monkeypatch.setattr(aelin_tools.AelinToolHub, "_tool_desktop_open_aelin", lambda self, args: {"ok": True, "route": args.get("route", "/")})

    assert hub.execute("device", {"action": "status"})["summary"] == "status"
    assert hub.execute("device", {"action": "processes"})["items"][0]["pid"] == 1
    assert hub.execute("device", {"action": "mode_apply", "mode": "focus"})["mode"] == "focus"
    assert hub.execute("device", {"action": "open_url", "url": "https://example.com"})["url"] == "https://example.com"
    assert hub.execute("device", {"action": "open_aelin", "route": "/processes"})["route"] == "/processes"


def test_device_tool_rejects_unknown_action():
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)

    result = hub.execute("device", {"action": "capabilities"})

    assert result["ok"] is False
    assert result["error"] == "unsupported device action"


def test_attachment_search_uses_available_ids_fallback():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
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
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
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
    calls = {"get_summary": 0, "build_focus_items": 0, "list_todos": 0, "snapshot": 0}

    class _Memory:
        def get_summary(self, db, user_id):
            calls["get_summary"] += 1
            return "summary"

        def build_focus_items(self, db, user_id, *, query="", limit=8):
            calls["build_focus_items"] += 1
            return [
                SimpleNamespace(
                    message_id=11,
                    source="imap",
                    sender="alice",
                    sender_avatar_url=None,
                    title="mail title",
                    received_at="2026-03-11 10:00",
                    score=8.3,
                )
            ]

        def list_todos(self, db, user_id, *, include_done=True, limit=100):
            calls["list_todos"] += 1
            return [{"id": 1, "title": "todo", "done": False, "updated_at": "2026-03-11T10:00:00+00:00"}]

        def snapshot(self, db, user_id, *, query=""):
            calls["snapshot"] += 1
            raise AssertionError("snapshot should not be used")

    hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=7,
        workspace="default",
        memory_service=_Memory(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
    )

    result = hub.execute("context_get", {"query": "mail", "max_items": 3})

    assert result["ok"] is True
    assert result["summary"] == "summary"
    assert result["focus_items"][0]["source_label"] == "Email"
    assert result["todos"][0]["title"] == "todo"
    assert calls["get_summary"] == 1
    assert calls["build_focus_items"] == 1
    assert calls["list_todos"] == 1
    assert calls["snapshot"] == 0


def test_pinchtab_tool_calls_client_methods(monkeypatch):
    fake_web = _FakeWebSearch()
    hub = _hub(fake_web)
    fake_client = _FakePinchTabClient()
    _patch_pinchtab_runtime(monkeypatch, fake_client)

    # health
    result = hub.execute("pinchtab", {"action": "health"})
    assert result["ok"] is True
    assert any(call[0] == "health" for call in fake_client.calls)

    # launch + open_tab
    result = hub.execute("pinchtab", {"action": "launch_instance"})
    assert result["ok"] is True and result.get("instance_id") == "inst-1"

    result = hub.execute(
        "pinchtab",
        {"action": "open_tab", "instance_id": "inst-1", "url": "https://example.com"},
    )
    assert result["ok"] is True and result.get("tab_id") == "tab-1"

    # required parameter validation
    missing = hub.execute("pinchtab", {"action": "open_tab"})
    assert missing["ok"] is False and "missing instance_id or url" in str(missing.get("error") or "")

    # unsupported action
    unsupported = hub.execute("pinchtab", {"action": "unknown"})
    assert unsupported["ok"] is False


def test_pinchtab_agent_executes_plan_with_llm_and_client(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)

    result = hub.execute("pinchtab_agent", {"goal": "打开 example.com 并读取文本"})
    assert result["ok"] is True
    assert result.get("instance_id") == "inst-1"
    assert result.get("tab_id") == "tab-1"
    assert "last_text" in result
    # Ensure the low-level client was actually used.
    called_ops = [name for name, _ in fake_client.calls]
    assert "launch_instance" in called_ops
    assert "open_tab" in called_ops
    assert "text" in called_ops


def test_pinchtab_session_start_and_step_reuse_instance(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()

    # start 会话
    start_result = hub.execute("pinchtab_session", {"action": "start", "goal": "打开 example.com 并读取文本"})
    assert start_result["ok"] is True
    sid = start_result.get("session_id")
    assert isinstance(sid, str) and sid
    assert start_result.get("instance_id") == "inst-1"
    assert start_result.get("tab_id") == "tab-1"

    # step 应该复用同一个 instance，并再次调用 pinchtab_agent
    _ = hub.execute("pinchtab_session", {"action": "step", "session_id": sid, "goal": "继续读取文本"})
    # Fake client 中的 launch_instance 只会在第一次被调用一次。
    launch_calls = [op for op, _ in fake_client.calls if op == "launch_instance"]
    assert launch_calls == ["launch_instance"]


def test_pinchtab_session_rejects_cross_user_access(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    owner_hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    other_hub = AelinToolHub(
        db=None,  # type: ignore[arg-type]
        user_id=2,
        workspace="default",
        memory_service=_DummyMemory(),  # type: ignore[arg-type]
        file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
        web_search_service=fake_web,  # type: ignore[arg-type]
        llm_service=fake_service,  # type: ignore[arg-type]
    )
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()

    start_result = owner_hub.execute("pinchtab_session", {"action": "start", "goal": "打开 example.com 并读取文本"})
    assert start_result["ok"] is True
    sid = str(start_result.get("session_id") or "")
    assert sid

    blocked_status = other_hub.execute("pinchtab_session", {"action": "status", "session_id": sid})
    blocked_step = other_hub.execute("pinchtab_session", {"action": "step", "session_id": sid, "goal": "继续"})
    blocked_close = other_hub.execute("pinchtab_session", {"action": "close", "session_id": sid})

    assert blocked_status["ok"] is False
    assert blocked_step["ok"] is False
    assert blocked_close["ok"] is False
    assert blocked_status["error"] == "unknown_session_id"
    assert blocked_step["error"] == "unknown_session_id"
    assert blocked_close["error"] == "unknown_session_id"
    assert sid in _PINCHTAB_SESSIONS


def test_plane_browser_delegate_and_continue_reuse_same_session(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()
    aelin_planes._PLANE_TASKS.clear()
    aelin_planes._PLANE_USER_TASKS.clear()

    delegated = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})
    assert delegated["ok"] is True
    task_id = str(delegated.get("task_id") or "")
    assert task_id
    assert delegated["plane"] == "browser"
    assert delegated["task_id"] == task_id

    status = hub.execute("plane", {"action": "status", "plane": "browser", "task_id": task_id})
    assert status["ok"] is True
    assert status["task_id"] == task_id

    continued = hub.execute(
        "plane",
        {"action": "continue", "plane": "browser", "task_id": task_id, "goal": "继续读取文本"},
    )
    assert continued["ok"] is True
    assert continued["task_id"] == task_id

    launch_calls = [op for op, _ in fake_client.calls if op == "launch_instance"]
    assert launch_calls == ["launch_instance"]


def test_plane_delegate_reuses_existing_active_task_by_default(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()
    aelin_planes._PLANE_TASKS.clear()
    aelin_planes._PLANE_USER_TASKS.clear()

    first = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})
    assert first["ok"] is True
    task_id = str(first.get("task_id") or "")
    assert task_id
    task = aelin_planes.get_plane_task(task_id, user_id=1, workspace="default", plane="browser")
    assert task is not None
    aelin_planes.set_plane_task(
        task_id,
        {
            **task,
            "state": "running",
            "summary": "browser task still running",
        },
        user_id=1,
        workspace="default",
        plane="browser",
    )

    second = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "继续读取详情"})

    assert second["ok"] is True
    assert second["task_id"] == task_id
    assert second["reused_existing_task"] is True
    assert second["reused_action"] == "continue"

    launch_calls = [op for op, _ in fake_client.calls if op == "launch_instance"]
    assert launch_calls == ["launch_instance"]


def test_plane_delegate_force_new_creates_fresh_task(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()
    aelin_planes._PLANE_TASKS.clear()
    aelin_planes._PLANE_USER_TASKS.clear()

    first = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})
    assert first["ok"] is True
    first_task_id = str(first.get("task_id") or "")
    assert first_task_id
    first_task = aelin_planes.get_plane_task(first_task_id, user_id=1, workspace="default", plane="browser")
    assert first_task is not None
    aelin_planes.set_plane_task(
        first_task_id,
        {
            **first_task,
            "state": "running",
            "summary": "browser task still running",
        },
        user_id=1,
        workspace="default",
        plane="browser",
    )

    second = hub.execute(
        "plane",
        {"action": "delegate", "plane": "browser", "goal": "重新开始一个新网页任务", "force_new": True},
    )

    assert second["ok"] is True
    assert str(second.get("task_id") or "") != first_task_id
    assert second.get("reused_existing_task") in {None, False}


def test_plane_browser_delegate_uses_plane_task_id_instead_of_session_id(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()
    aelin_planes._PLANE_TASKS.clear()
    aelin_planes._PLANE_USER_TASKS.clear()

    delegated = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})

    assert delegated["ok"] is True
    task_id = str(delegated.get("task_id") or "")
    assert task_id
    task = aelin_planes.get_plane_task(task_id, user_id=1, workspace="default", plane="browser")
    assert task is not None
    assert str(task.get("backing_task_id") or "")
    assert str(task.get("backing_task_id") or "") != task_id


def test_plane_tasks_can_be_recovered_from_db_without_memory_registry(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()
    engine, db1 = _create_db_session()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db2 = SessionLocal()

    try:
        hub1 = _hub(fake_web, llm_service=fake_service, db=db1)  # type: ignore[arg-type]
        hub2 = AelinToolHub(
            db=db2,  # type: ignore[arg-type]
            user_id=1,
            workspace="default",
            memory_service=_DummyMemory(),  # type: ignore[arg-type]
            file_memory_bridge=_DummyFileMemory(),  # type: ignore[arg-type]
            web_search_service=fake_web,  # type: ignore[arg-type]
            llm_service=fake_service,  # type: ignore[arg-type]
        )
        _patch_pinchtab_runtime(monkeypatch, fake_client)
        _PINCHTAB_SESSIONS.clear()
        _PINCHTAB_USER_SESSIONS.clear()
        aelin_planes._PLANE_TASKS.clear()
        aelin_planes._PLANE_USER_TASKS.clear()

        delegated = hub1.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})
        assert delegated["ok"] is True
        task_id = str(delegated.get("task_id") or "")
        assert task_id

        aelin_planes._PLANE_TASKS.clear()
        aelin_planes._PLANE_USER_TASKS.clear()

        status = hub2.execute("plane", {"action": "status", "plane": "browser", "task_id": task_id})
        assert status["ok"] is True
        assert status["task_id"] == task_id

        persisted = aelin_planes.get_plane_task(task_id, user_id=1, workspace="default", plane="browser", db=db2)
        assert persisted is not None
        assert str(persisted.get("backing_task_id") or "")
    finally:
        db2.close()
        db1.close()


def test_plane_status_preserves_waiting_user_when_session_snapshot_lacks_login_flags(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()

    hub = _hub(fake_web, llm_service=fake_service)  # type: ignore[arg-type]
    _patch_pinchtab_runtime(monkeypatch, fake_client)
    _PINCHTAB_SESSIONS.clear()
    _PINCHTAB_USER_SESSIONS.clear()
    aelin_planes._PLANE_TASKS.clear()
    aelin_planes._PLANE_USER_TASKS.clear()

    delegated = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 X 并检查登录状态"})
    assert delegated["ok"] is True
    task_id = str(delegated.get("task_id") or "")
    assert task_id

    task = aelin_planes.get_plane_task(task_id, user_id=1, workspace="default", plane="browser")
    assert task is not None
    session_id = str(task.get("backing_task_id") or "")
    assert session_id
    aelin_planes.set_plane_task(
        task_id,
        {
            **task,
            "state": "waiting_user",
            "requires_user_input": True,
            "user_prompt": "请先完成登录",
        },
        user_id=1,
        workspace="default",
        plane="browser",
    )
    aelin_tools._PINCHTAB_SESSIONS[session_id] = {
        "owner_user_id": 1,
        "owner_workspace": "default",
        "instance_id": "inst-1",
        "tab_id": "tab-1",
        "last_goal": "打开 X 并检查登录状态",
        "last_status": "running",
        "last_url": "https://x.com/i/flow/login",
        "last_text": "login page",
        "last_summary": "still waiting",
    }

    status = hub.execute("plane", {"action": "status", "plane": "browser", "task_id": task_id})

    assert status["ok"] is True
    assert status["state"] == "waiting_user"
    assert status["requires_user_input"] is True
    assert status["user_prompt"] == "请先完成登录"


def test_plane_runtime_persists_events_and_artifacts(monkeypatch):
    fake_web = _FakeWebSearch()
    fake_client = _FakePinchTabClient()
    fake_completions = _FakeLLMCompletions()
    fake_service = type(
        "Svc",
        (object,),
        {
            "config": type("Cfg", (object,), {"model": "fake-model"})(),
            "client": type("Cli", (object,), {"chat": type("Chat", (object,), {"completions": fake_completions})()})(),
        },
    )()
    engine, db = _create_db_session()

    try:
        hub = _hub(fake_web, llm_service=fake_service, db=db)  # type: ignore[arg-type]
        _patch_pinchtab_runtime(monkeypatch, fake_client)
        _PINCHTAB_SESSIONS.clear()
        _PINCHTAB_USER_SESSIONS.clear()
        aelin_planes._PLANE_TASKS.clear()
        aelin_planes._PLANE_USER_TASKS.clear()

        delegated = hub.execute("plane", {"action": "delegate", "plane": "browser", "goal": "打开 example.com 并读取文本"})
        assert delegated["ok"] is True
        task_id = str(delegated.get("task_id") or "")
        assert task_id

        status = hub.execute("plane", {"action": "status", "plane": "browser", "task_id": task_id})
        assert status["ok"] is True

        continued = hub.execute(
            "plane",
            {"action": "continue", "plane": "browser", "task_id": task_id, "goal": "继续读取文本"},
        )
        assert continued["ok"] is True

        closed = hub.execute("plane", {"action": "close", "plane": "browser", "task_id": task_id})
        assert closed["ok"] is True

        events = aelin_planes.list_plane_events(task_id, user_id=1, workspace="default", plane="browser", db=db)
        artifacts = aelin_planes.list_plane_artifacts(task_id, user_id=1, workspace="default", plane="browser", db=db)

        event_types = [str(item.get("event_type") or "") for item in events]
        assert "delegated" in event_types
        assert "status_sync" in event_types
        assert "continued" in event_types
        assert "closed" in event_types

        artifact_kinds = [str(item.get("kind") or "") for item in artifacts]
        assert "page_text" in artifact_kinds
        assert "page_location" in artifact_kinds
    finally:
        db.close()
