from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolPolicyUsage,
    build_tool_runtime_context,
)
from app.services.web.web_search import WebSearchResult
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_web import tool_web_search


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


def _tool_context(fake_web: _FakeWebSearch, *, attachment_service=None, available_attachment_ids=None):
    return build_tool_runtime_context(
        db=None,  # type: ignore[arg-type]
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=attachment_service,  # type: ignore[arg-type]
        available_attachment_ids=available_attachment_ids,
    )


def test_web_search_tool_search_and_fetch():
    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    result = tool_web_search(
        context,
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
    context = _tool_context(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[3, "2", 3, 0],  # type: ignore[list-item]
    )

    result = tool_attachment_search(context, {"query": "总结附件"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [2, 3]
    assert fake_attachment.calls[0]["attachment_ids"] == [2, 3]


def test_attachment_search_prefers_explicit_ids():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    context = _tool_context(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[9, 10],
    )

    result = tool_attachment_search(
        context,
        {"query": "翻译", "attachment_ids": [5, "6", -1], "top_k": 6, "mode": "hybrid"},  # type: ignore[list-item]
    )

    assert result["ok"] is True
    assert result["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["attachment_ids"] == [5, 6]
    assert fake_attachment.calls[0]["top_k"] == 6
    assert fake_attachment.calls[0]["mode"] == "hybrid"


def test_screen_get_tool_success(monkeypatch):
    from app.services.tools import tools_device

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(
        tools_device,
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

    result = tool_screen_get(context, {"max_edge": 1024, "format": "jpeg"})
    assert result["ok"] is True
    assert str(result.get("data_url") or "").startswith("data:image/jpeg;base64,")
    assert result["width"] == 1280


def test_device_tool_supports_supported_device_actions(monkeypatch):
    from app.services.tools import tools_device

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(
        tools_device,
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
        tools_device,
        "open_desktop_external_url",
        lambda url: {"url": url, "opened": True, "detail": "ok"},
    )
    monkeypatch.setattr(
        tools_device,
        "activate_desktop_module",
        lambda route: {"route": route, "opened": True, "detail": "ok"},
    )

    status = tool_device(context, {"action": "status"})
    assert status["ok"] is True
    assert status["desktop_plugin_reachable"] is True

    opened = tool_device(context, {"action": "open_url", "url": "https://example.com"})
    assert opened["ok"] is True
    assert opened["opened"] is True

    aelin_opened = tool_device(context, {"action": "open_aelin", "route": "/"})
    assert aelin_opened["ok"] is True
    assert aelin_opened["route"] == "/"


def test_device_open_url_rejects_non_http_schemes(monkeypatch):
    from app.services.tools import tools_device

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    opened_urls: list[str] = []

    monkeypatch.setattr(
        tools_device,
        "open_desktop_external_url",
        lambda url: opened_urls.append(url) or {"url": url, "opened": True, "detail": "ok"},
    )

    blocked = tool_device(context, {"action": "open_url", "url": "file:///C:/Windows/System32/notepad.exe"})

    assert blocked["ok"] is False
    assert blocked["error"] == "invalid_url_scheme"
    assert opened_urls == []


def test_device_tool_rejects_unknown_action():
    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    result = tool_device(context, {"action": "capabilities"})

    assert result["ok"] is False
    assert "unsupported device action" in str(result.get("error") or "")


def test_google_workspace_tool_runtime_and_auth_status(monkeypatch):
    from app.services.tools import tools_gws

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

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

    monkeypatch.setattr(tools_gws, "get_google_workspace_cli_service", lambda: _FakeGWS())

    runtime = tool_google_workspace(context, {"action": "runtime"})
    assert runtime["ok"] is True
    assert runtime["scope"] == "runtime"
    assert runtime["available"] is True

    auth = tool_google_workspace(context, {"action": "auth_status"})
    assert auth["scope"] == "auth"
    assert auth["ok"] is False
    assert auth["authenticated"] is False
    assert auth["login_command"] == ["gws", "auth", "login"]


def test_google_workspace_tool_gmail_and_drive_and_calendar_success(monkeypatch):
    from app.services.tools import tools_gws

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

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

    monkeypatch.setattr(tools_gws, "get_google_workspace_cli_service", lambda: _FakeGWS())

    gmail_list = tool_google_workspace(
        context,
        {"action": "gmail_list", "query": "is:unread", "max_results": 5, "include_spam_trash": True},
    )
    assert gmail_list["ok"] is True
    assert gmail_list["scope"] == "gmail"
    assert [item["id"] for item in gmail_list["items"]] == ["m1", "m2"]

    gmail_get = tool_google_workspace(context, {"action": "gmail_get", "message_id": "m1", "format": "minimal"})
    assert gmail_get["ok"] is True
    assert gmail_get["item"]["id"] == "m1"

    drive = tool_google_workspace(context, {"action": "drive_list", "query": "name contains 'Spec'", "max_results": 3})
    assert drive["ok"] is True
    assert drive["items"][0]["name"] == "Spec"

    calendar = tool_google_workspace(context, {"action": "calendar_list", "calendar_id": "primary", "max_results": 4})
    assert calendar["ok"] is True
    assert calendar["items"][0]["summary"] == "Demo"


def test_google_workspace_tool_error_paths_and_write_actions(monkeypatch):
    from app.services.tools import tools_gws

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

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

    monkeypatch.setattr(tools_gws, "get_google_workspace_cli_service", lambda: _FakeGWS())

    assert tool_google_workspace(context, {"action": "gmail_list"})["scope"] == "gmail"
    assert tool_google_workspace(context, {"action": "drive_list"})["scope"] == "drive"
    assert tool_google_workspace(context, {"action": "calendar_list"})["scope"] == "calendar"
    assert tool_google_workspace(context, {"action": "calendar_create_event"})["scope"] == "calendar"
    assert tool_google_workspace(context, {"action": "gmail_send"})["scope"] == "gmail"
    assert tool_google_workspace(context, {"action": "gmail_draft"})["scope"] == "gmail"
    unknown = tool_google_workspace(context, {"action": "unknown_action"})
    assert unknown["ok"] is False
    assert unknown["error"] == "unsupported_action"


def test_deepagents_build_chat_tools_uses_explicit_registered_tools(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    calls: list[dict[str, object]] = []

    def _fake_tool_device(tool_context, args):  # type: ignore[no-untyped-def]
        calls.append({"tool_context": tool_context, "args": dict(args)})
        return {"ok": True, "echo": dict(args)}

    monkeypatch.setattr(dag, "tool_device", _fake_tool_device)

    limiter = ToolCallLimiter(
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, usage = dag.build_chat_tools(context=context, limiter=limiter)

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
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(dag, "tool_web_search", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    limiter = ToolCallLimiter(
        max_tool_calls=4,
        max_write_calls=1,
        allow_write_tools=False,
    )

    tools, tool_runs, usage = dag.build_chat_tools(context=context, limiter=limiter)
    web_tool = next(t for t in tools if t.name == "web_search")
    result = web_tool.invoke({"action": "search", "query": "deepagents"})

    assert result["ok"] is False
    assert "web_search_failed:boom" in str(result.get("error") or "")
    assert usage.total_calls == 1
    assert tool_runs[0]["call_index"] == 1


def test_deepagents_memory_files_include_agents_md(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    # Avoid hitting real ChatOpenAI / network when constructing the agent.
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag, "create_deep_agent", lambda **kwargs: object())

    limiter = ToolCallLimiter(
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    agent, usage, tool_runs, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=limiter,
        memory_text="# Aelin Session Memory\n\n## 长期记忆\n- likes agents.\n- migrated to DeepAgents shell.",
        skills_root=None,
    )

    assert isinstance(agent, object)
    assert isinstance(usage, ToolPolicyUsage)
    assert isinstance(files, dict)
    assert "/memory/AGENTS.md" in files
    content = files["/memory/AGENTS.md"].get("content")
    assert isinstance(content, list) and "likes agents." in "\n".join(str(line) for line in content)


def test_deepagents_skills_mount_full_directory_tree(monkeypatch, tmp_path):
    from app.services.deepagents import deepagents_graph as dag

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
    context = _tool_context(fake_web)

    # Avoid hitting real ChatOpenAI / network when constructing the agent.
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    limiter = ToolCallLimiter(
        max_tool_calls=8,
        max_write_calls=2,
        allow_write_tools=False,
    )

    _, _, _, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=limiter,
        memory_text="",
        skills_root=skill_root,
    )

    skills_param = captured.get("skills")
    assert isinstance(skills_param, list)
    assert "/skills/aelin/" in skills_param  # type: ignore[operator]
    assert "/skills/aelin/chrome-cdp/SKILL.md" in files
    assert "/skills/aelin/chrome-cdp/scripts/cdp.mjs" in files
    assert "/skills/aelin/chrome-cdp/references/guide.md" in files
    assert "/runtime/capabilities.json" in files
    capabilities_content = files["/runtime/capabilities.json"].get("content")
    assert isinstance(capabilities_content, list)
    capabilities_text = "\n".join(str(line) for line in capabilities_content)
    assert '"mounted_skills"' in capabilities_text
    assert "/skills/aelin/chrome-cdp/" in capabilities_text


def test_deepagents_default_skills_root_points_to_backend_skills_dir():
    from app.services.deepagents import deepagents_graph as dag

    root = dag._backend_root() / "deepagents_skills"
    assert root.as_posix().endswith("/backend/deepagents_skills")


def test_deepagents_system_prompt_adds_capability_and_factuality_rules(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    # Avoid hitting real ChatOpenAI / network when constructing the agent.
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    limiter = ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False)
    dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=limiter,
        memory_text="",
        skills_root=None,
    )

    system_prompt = str(captured.get("system_prompt") or "")
    assert "/runtime/capabilities.json" in system_prompt
    assert "Never claim you searched, opened, read, or cited an external source" in system_prompt


def test_deepagents_loop_preserves_model_answer_without_legacy_open_claim_guard(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    class _FakeAgent:
        def invoke(self, payload):  # noqa: ANN001
            _ = payload
            return {"answer": "我已经为你打开了相关新闻网站，并整理好了结果。"}

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return (
            _FakeAgent(),
            ToolPolicyUsage(),
            [],
            {
                "/runtime/capabilities.json": {
                    "content": [
                        "{",
                        '  "tools": ["web_search", "device"]',
                        "}",
                    ]
                }
            },
        )

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    result = dag.run_deepagents_loop(
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=SimpleNamespace(),
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        query="请联网查一下",
        memory_text="",
        history_turns=[],
    )

    assert result.ok is True
    assert "我已经为你打开了相关新闻网站" in result.answer
    assert "tools=2" in result.capability_summary


def test_deepagents_loop_forwards_images_in_last_user_message(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    captured: dict[str, object] = {}

    class _FakeAgent:
        def invoke(self, payload):  # noqa: ANN001
            captured["payload"] = payload
            return {"answer": "看到了图片"}

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return (
            _FakeAgent(),
            ToolPolicyUsage(),
            [],
            {
                "/runtime/capabilities.json": {
                    "content": [
                        "{",
                        '  "tools": ["web_search", "device"]',
                        "}",
                    ]
                }
            },
        )

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    result = dag.run_deepagents_loop(
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=SimpleNamespace(),
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        query="这张图里有什么？",
        memory_text="",
        history_turns=[],
        images=[
            {
                "name": "demo.png",
                "data_url": "data:image/png;base64,QUJDRA==",
            }
        ],
    )

    assert result.ok is True
    payload = dict(captured["payload"])
    messages = list(payload["messages"])
    last = dict(messages[-1])
    assert last["role"] == "user"
    assert isinstance(last["content"], list)
    assert last["content"][0] == {"type": "text", "text": "这张图里有什么？"}
    assert last["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,QUJDRA=="},
    }


def test_deepagents_loop_preserves_system_history(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    captured: dict[str, object] = {}

    class _FakeAgent:
        def invoke(self, payload):  # noqa: ANN001
            captured["payload"] = payload
            return {"answer": "ok"}

    def _fake_build_chat_agent(**kwargs):  # noqa: ANN001
        _ = kwargs
        return (
            _FakeAgent(),
            ToolPolicyUsage(),
            [],
            {
                "/runtime/capabilities.json": {
                    "content": [
                        "{",
                        '  "tools": ["web_search", "device"]',
                        "}",
                    ]
                }
            },
        )

    monkeypatch.setattr(dag, "build_chat_agent", _fake_build_chat_agent)
    result = dag.run_deepagents_loop(
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=SimpleNamespace(),
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        query="继续",
        memory_text="",
        history_turns=[
            {"role": "system", "content": "你是系统消息"},
            {"role": "user", "content": "你好"},
        ],
    )

    assert result.ok is True
    payload = dict(captured["payload"])
    assert payload["messages"] == [
        {"role": "system", "content": "你是系统消息"},
        {"role": "user", "content": "你好"},
        {"role": "user", "content": "继续"},
    ]


def test_deepagents_build_chat_tools_abort_when_cancelled(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    limiter = ToolCallLimiter(max_tool_calls=4, max_write_calls=1, allow_write_tools=False)
    cancel_token = SimpleNamespace(cancelled=True)

    tools, _tool_runs, _usage = dag.build_chat_tools(
        context=context,
        limiter=limiter,
        cancel_token=cancel_token,
    )
    web_tool = next(t for t in tools if t.name == "web_search")

    with pytest.raises(dag.DeepAgentsCancelled):
        web_tool.invoke({"action": "search", "query": "deepagents"})

