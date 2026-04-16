from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import app.services.artifact_files as artifact_files
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import set_config_context
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AttachmentDocument, Base
from app.services.deepagents.delivery_paths import get_delivery_paths
from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    ToolPolicyUsage,
    build_tool_runtime_context,
)
from app.services.web.web_search import WebSearchResult
from app.services.tools.tools_device import tool_device, tool_screen_get
from app.services.tools.tools_execute import tool_execute
from app.services.tools.tools_files import tool_attachment_search
from app.services.tools.tools_gws import tool_google_workspace
from app.services.tools.tools_present_files import tool_present_files
from app.services.tools.tools_visual_artifact import tool_render_poster_artifact
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


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _file_data_text(file_data: object) -> str:
    if not isinstance(file_data, dict):
        return ""
    content = file_data.get("content")
    if isinstance(content, list):
        return "\n".join(str(line) for line in content)
    return str(content or "")


def _tool_context(fake_web: _FakeWebSearch, *, attachment_service=None, available_attachment_ids=None):
    return build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=attachment_service,  # type: ignore[arg-type]
        available_attachment_ids=available_attachment_ids,
        session_factory=_FakeSession,
    )


def _db_session_factory_with_attachments(*rows: dict[str, object]):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        for row in rows:
            db.add(AttachmentDocument(**row))
        db.commit()
    finally:
        db.close()
    return SessionLocal


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
        available_attachment_ids=[5, 6, 9, 10],
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


def test_attachment_search_reads_scoped_ids_from_runnable_config():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    context = _tool_context(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[],
    )

    with set_config_context({"configurable": {"attachment_ids": [8, "9", 0, -1]}}) as ctx:
        result = ctx.run(tool_attachment_search, context, {"query": "项目代号"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [8, 9]
    assert fake_attachment.calls[0]["attachment_ids"] == [8, 9]


def test_attachment_search_reads_scoped_ids_from_langgraph_runtime(monkeypatch):
    from app.services.tools import tools_files

    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    context = _tool_context(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[],
    )

    monkeypatch.setattr(
        tools_files,
        "get_runtime",
        lambda *_args, **_kwargs: SimpleNamespace(
            context=SimpleNamespace(attachment_ids=[41, "42", 0, -1])
        ),
    )

    result = tool_attachment_search(context, {"query": "项目代号"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [41, 42]
    assert fake_attachment.calls[0]["attachment_ids"] == [41, 42]


def test_attachment_search_falls_back_to_thread_scoped_recent_attachments():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    session_factory = _db_session_factory_with_attachments(
        {
            "user_id": 1,
            "workspace": "default",
            "session_id": "thread-a",
            "file_name": "alpha.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "a" * 64,
            "storage_path": "/tmp/a.pdf",
            "parse_status": "ready",
            "summary": "alpha",
            "metadata_json": "{}",
        },
        {
            "user_id": 1,
            "workspace": "default",
            "session_id": "thread-b",
            "file_name": "beta.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "b" * 64,
            "storage_path": "/tmp/b.pdf",
            "parse_status": "ready",
            "summary": "beta",
            "metadata_json": "{}",
        },
    )
    context = build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[],
        session_factory=session_factory,
    )

    with set_config_context({"configurable": {"thread_id": "thread-a"}}) as ctx:
        result = ctx.run(tool_attachment_search, context, {"query": "项目代号"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [1]
    assert fake_attachment.calls[0]["attachment_ids"] == [1]


def test_attachment_search_falls_back_to_recent_workspace_attachments_without_thread_id():
    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    session_factory = _db_session_factory_with_attachments(
        {
            "user_id": 1,
            "workspace": "default",
            "session_id": "",
            "file_name": "alpha.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "c" * 64,
            "storage_path": "/tmp/c.pdf",
            "parse_status": "ready",
            "summary": "alpha",
            "metadata_json": "{}",
        },
        {
            "user_id": 1,
            "workspace": "default",
            "session_id": "",
            "file_name": "beta.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "d" * 64,
            "storage_path": "/tmp/d.pdf",
            "parse_status": "ready",
            "summary": "beta",
            "metadata_json": "{}",
        },
        {
            "user_id": 1,
            "workspace": "other",
            "session_id": "",
            "file_name": "other.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "e" * 64,
            "storage_path": "/tmp/e.pdf",
            "parse_status": "ready",
            "summary": "other",
            "metadata_json": "{}",
        },
    )
    context = build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[],
        session_factory=session_factory,
    )

    result = tool_attachment_search(context, {"query": "交付物"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [1, 2]
    assert fake_attachment.calls[0]["attachment_ids"] == [1, 2]


def test_attachment_search_caches_non_empty_storage_scope(monkeypatch):
    from app.services.tools import tools_files

    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    session_factory = _db_session_factory_with_attachments(
        {
            "user_id": 1,
            "workspace": "default",
            "session_id": "thread-cache",
            "file_name": "alpha.pdf",
            "file_ext": "pdf",
            "mime_type": "application/pdf",
            "size_bytes": 10,
            "sha256": "f" * 64,
            "storage_path": "/tmp/f.pdf",
            "parse_status": "ready",
            "summary": "alpha",
            "metadata_json": "{}",
        },
    )
    context = build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[],
        session_factory=session_factory,
    )

    tools_files.clear_attachment_scope_cache_for_tests()
    monkeypatch.setattr(tools_files.settings, "deepagents_attachment_scope_cache_ttl_seconds", 60.0)

    with set_config_context({"configurable": {"thread_id": "thread-cache"}}) as ctx:
        first = ctx.run(tool_attachment_search, context, {"query": "第一次"})

    assert first["ok"] is True
    assert first["attachment_ids"] == [1]

    db = session_factory()
    try:
        db.query(AttachmentDocument).delete()
        db.commit()
    finally:
        db.close()

    with set_config_context({"configurable": {"thread_id": "thread-cache"}}) as ctx:
        second = ctx.run(tool_attachment_search, context, {"query": "第二次"})

    assert second["ok"] is True
    assert second["attachment_ids"] == [1]


def test_attachment_search_does_not_cache_empty_storage_fallback(monkeypatch):
    from app.services.tools import tools_files

    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    session_factory = _db_session_factory_with_attachments()
    context = build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        attachment_service=fake_attachment,  # type: ignore[arg-type]
        available_attachment_ids=[],
        session_factory=session_factory,
    )

    tools_files.clear_attachment_scope_cache_for_tests()
    monkeypatch.setattr(tools_files.settings, "deepagents_attachment_scope_cache_ttl_seconds", 60.0)

    result = tool_attachment_search(context, {"query": "第一次"})
    assert result["ok"] is False
    assert result["error"] == "missing attachment_ids"

    db = session_factory()
    try:
        db.add(
            AttachmentDocument(
                user_id=1,
                workspace="default",
                session_id="",
                file_name="late.pdf",
                file_ext="pdf",
                mime_type="application/pdf",
                size_bytes=10,
                sha256="g" * 64,
                storage_path="/tmp/g.pdf",
                parse_status="ready",
                summary="late",
                metadata_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()

    second = tool_attachment_search(context, {"query": "第二次"})
    assert second["ok"] is True
    assert second["attachment_ids"] == [1]


def test_screen_get_tool_success(monkeypatch):
    from app.services.tools import tools_device

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(
        tools_device.device_actions,
        "capture_device_screen",
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
        tools_device.device_actions,
        "build_device_status_contract",
        lambda: {
            "platform": "windows",
            "capabilities": {"desktop_open_url": True, "desktop_activate_module": False},
            "notes": ["note-a"],
            "desktop_plugin_reachable": True,
            "desktop_plugin_configured": True,
        },
    )
    monkeypatch.setattr(
        tools_device.device_actions,
        "open_desktop_external_url",
        lambda url: {"url": url, "opened": True, "detail": "ok"},
    )
    monkeypatch.setattr(
        tools_device.device_actions,
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
        tools_device.device_actions,
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


def test_execute_tool_returns_command_result(monkeypatch):
    from app.services.tools import tools_execute

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(
        tools_execute,
        "execute_command_result",
        lambda args: {
            "ok": True,
            "command": str(args.get("command") or ""),
            "cwd": str(args.get("cwd") or ""),
            "exit_code": 0,
            "stdout": "pytest passed",
            "stderr": "",
            "timed_out": False,
            "summary": "command succeeded",
        },
    )

    result = tool_execute(context, {"command": "pytest -q", "cwd": "D:/Github/Aelin/backend"})

    assert result["ok"] is True
    assert result["command"] == "pytest -q"
    assert result["stdout"] == "pytest passed"


def test_execute_tool_defaults_cwd_to_delivery_workspace(monkeypatch):
    from app.services.tools import tools_execute

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    captured: dict[str, object] = {}

    def _fake_execute_command_result(args):  # type: ignore[no-untyped-def]
        captured.update(dict(args))
        return {"ok": True, "cwd": str(args.get("cwd") or "")}

    monkeypatch.setattr(tools_execute, "execute_command_result", _fake_execute_command_result)

    result = tool_execute(context, {"command": "python build.py"})
    delivery_paths = get_delivery_paths(workspace="default", user_id=1)

    assert result["ok"] is True
    assert captured["cwd"] == str(delivery_paths.workspace_dir)


def test_execute_tool_maps_virtual_cwd_to_delivery_root(monkeypatch):
    from app.services.tools import tools_execute

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    captured: dict[str, object] = {}

    def _fake_execute_command_result(args):  # type: ignore[no-untyped-def]
        captured.update(dict(args))
        return {"ok": True, "cwd": str(args.get("cwd") or "")}

    monkeypatch.setattr(tools_execute, "execute_command_result", _fake_execute_command_result)

    result = tool_execute(context, {"command": "python build.py", "cwd": "/outputs"})
    delivery_paths = get_delivery_paths(workspace="default", user_id=1)

    assert result["ok"] is True
    assert captured["cwd"] == str(delivery_paths.outputs_dir)


def test_execute_command_result_returns_compact_local_artifacts(monkeypatch, tmp_path):
    from app.services.device import device_actions

    fake_repo_root = tmp_path / "allowed-repo"
    fake_media_root = tmp_path / "allowed-media"
    fake_attachment_root = tmp_path / "allowed-attachments"
    fake_repo_root.mkdir(parents=True, exist_ok=True)
    fake_media_root.mkdir(parents=True, exist_ok=True)
    fake_attachment_root.mkdir(parents=True, exist_ok=True)
    artifact_path = fake_repo_root / "output" / "poster.png"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"fake-png")

    monkeypatch.setattr(artifact_files, "_REPO_ROOT", fake_repo_root)
    monkeypatch.setattr(artifact_files.settings, "media_dir", str(fake_media_root))
    monkeypatch.setattr(artifact_files.settings, "aelin_attachment_storage_dir", str(fake_attachment_root))

    monkeypatch.setattr(
        device_actions,
        "execute_desktop_command",
        lambda **kwargs: {
            "command": str(kwargs.get("command") or ""),
            "cwd": str(kwargs.get("cwd") or ""),
            "exit_code": 0,
            "stdout": "done",
            "stderr": "",
            "timed_out": False,
            "summary": "command succeeded with exit code 0 and produced 1 artifact(s)",
            "artifacts": [
                {
                    "path": str(artifact_path),
                    "relative_path": "output/poster.png",
                    "name": "poster.png",
                    "mime_type": "image/png",
                    "size_bytes": 16,
                    "preview_kind": "image-data-url",
                    "content": "data:image/png;base64,ZmFrZQ==",
                    "binary_base64": "ZmFrZQ==",
                }
            ],
        },
    )

    result = device_actions.execute_command_result(
        {"command": "python build.py", "cwd": "D:/Github/Aelin"}
    )

    assert result["ok"] is True
    assert result["artifact_count"] == 1
    artifact = result["artifacts"][0]
    assert artifact["path"] == str(artifact_path)
    assert artifact["relative_path"] == "output/poster.png"
    assert artifact["name"] == "poster.png"
    assert artifact["mime_type"] == "image/png"
    assert artifact["size_bytes"] == 16
    assert artifact["preview_kind"] == "image-data-url"
    assert artifact["content"] == ""
    assert artifact["created_at"] == ""
    assert str(artifact["modified_at"] or "").strip()


def test_present_files_tool_returns_output_artifacts(monkeypatch, tmp_path):
    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    output_file = tmp_path / "outputs" / "report.docx"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(b"fake-docx")

    fake_media_root = tmp_path / "media"
    fake_attachment_root = tmp_path / "attachments"
    fake_media_root.mkdir(parents=True, exist_ok=True)
    fake_attachment_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(artifact_files, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(artifact_files.settings, "media_dir", str(fake_media_root))
    monkeypatch.setattr(artifact_files.settings, "aelin_attachment_storage_dir", str(fake_attachment_root))

    monkeypatch.setattr(
        "app.services.tools.tools_present_files.get_delivery_paths",
        lambda **_kwargs: get_delivery_paths(workspace="default", user_id=1, create=False),
    )
    monkeypatch.setattr(
        "app.services.tools.tools_present_files.resolve_virtual_or_local_path",
        lambda path_value, _paths, **_kwargs: output_file if str(path_value or "").strip() else output_file,
    )

    result = tool_present_files(context, {"filepaths": ["/outputs/report.docx"]})

    assert result["ok"] is True
    assert result["artifact_count"] == 1
    assert result["file_paths"] == [str(output_file)]
    assert result["artifacts"][0]["path"] == str(output_file)


def test_render_poster_artifact_tool_returns_compact_previewable_artifact(monkeypatch, tmp_path):
    from app.services import visual_artifacts

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    monkeypatch.setattr(visual_artifacts, "_REPO_ROOT", Path(tmp_path))

    result = tool_render_poster_artifact(
        context,
        {
            "brief": "帮我为同济大学樱花季赏花活动创作一张海报，要求最终输出为png或.pdf文件，画面纯净精致，无元素重叠，构图完美",
            "preferred_format": "png",
        },
    )

    assert result["ok"] is True
    assert result["artifact_count"] == 2
    artifact = result["artifacts"][0]
    assert artifact["preview_kind"] == "image-data-url"
    assert artifact["content"] == ""
    assert artifact["relative_path"].startswith("output/generated-posters/")
    assert Path(artifact["path"]).is_file()


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

        def auth_status(self):
            return {"ok": True, "authenticated": True}

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
        def runtime_status(self):
            return {"ok": True, "available": True}

        def auth_status(self):
            return {"ok": True, "authenticated": True}

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
    assert tool_google_workspace(
        context,
        {
            "action": "calendar_create_event",
            "event_summary": "Demo",
            "event_start": "2026-03-26T10:00:00Z",
            "event_end": "2026-03-26T11:00:00Z",
        },
    )["scope"] == "calendar"
    assert tool_google_workspace(
        context,
        {
            "action": "gmail_send",
            "email_to": ["a@example.com"],
            "email_subject": "Hi",
            "email_body": "Hello",
        },
    )["scope"] == "gmail"
    assert tool_google_workspace(
        context,
        {
            "action": "gmail_draft",
            "email_to": ["a@example.com"],
            "email_subject": "Draft",
            "email_body": "Hello",
        },
    )["scope"] == "gmail"
    unknown = tool_google_workspace(context, {"action": "unknown_action"})
    assert unknown["ok"] is False
    assert "unsupported_action" in str(unknown["error"])


def test_memory_search_tool_returns_structured_hits():
    from app.services.tools.tools_memory import tool_memory_search

    class _FakeMemoryService:
        def search_memory(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["query"] == "OpenClaw memory"
            return [
                {
                    "path": "/memory/projects.md",
                    "title": "OpenClaw-style memory refactor",
                    "preview": "Compact projection plus retrieval.",
                    "score": 7.2,
                    "updated_at": "2026-04-07T00:00:00+00:00",
                    "canonical_id": "project:1",
                    "target": "projects.md",
                    "source": "agents_md",
                    "kind": "project",
                    "topic_path": "projects",
                    "entry_kind": "note",
                }
            ]

    fake_web = _FakeWebSearch()
    context = build_tool_runtime_context(
        user_id=1,
        workspace="default",
        web_search_service=fake_web,  # type: ignore[arg-type]
        memory_service=_FakeMemoryService(),  # type: ignore[arg-type]
        session_factory=_FakeSession,
    )

    result = tool_memory_search(context, {"query": "OpenClaw memory", "kinds": ["project"], "top_k": 4})

    assert result["ok"] is True
    assert result["total"] == 1
    assert result["items"][0]["kind"] == "project"
    assert result["items"][0]["path"] == "/memory/projects.md"


def test_deepagents_build_chat_tools_uses_explicit_registered_tools(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    calls: list[dict[str, object]] = []

    def _fake_tool_memory_search(tool_context, args):  # type: ignore[no-untyped-def]
        calls.append({"tool_context": tool_context, "args": dict(args)})
        return {"ok": True, "echo": dict(args)}

    monkeypatch.setattr(dag, "tool_memory_search", _fake_tool_memory_search)

    limiter = ToolCallLimiter(
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, usage = dag.build_chat_tools(context=context, limiter=limiter)

    assert isinstance(usage, ToolPolicyUsage)
    assert [tool.name for tool in tools] == [
        "memory_search",
        "web_search",
        "attachment_search",
        "google_workspace",
        "device",
        "screen_get",
        "present_files",
    ]

    memory_tool = next(t for t in tools if t.name == "memory_search")
    result = memory_tool.invoke({"query": "OpenClaw memory", "kinds": ["project"]})

    assert result["ok"] is True
    assert calls
    assert calls[0]["args"] == {
        "query": "OpenClaw memory",
        "kinds": ["project"],
        "top_k": 6,
    }
    assert any(tr["name"] == "memory_search" and tr["status"] == "completed" for tr in tool_runs)


def test_deepagents_build_chat_tools_registers_execute_when_enabled(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    calls: list[dict[str, object]] = []

    def _fake_tool_execute(tool_context, args):  # type: ignore[no-untyped-def]
        calls.append({"tool_context": tool_context, "args": dict(args)})
        return {
            "ok": True,
            "command": str(args.get("command") or ""),
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "timed_out": False,
            "summary": "command succeeded",
        }

    monkeypatch.setattr(dag, "tool_execute", _fake_tool_execute)
    monkeypatch.setattr(dag.settings, "desktop_plugin_execute_enabled", True)

    limiter = ToolCallLimiter(
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, _usage = dag.build_chat_tools(context=context, limiter=limiter)

    assert "execute" in [tool.name for tool in tools]
    execute_tool = next(t for t in tools if t.name == "execute")
    result = execute_tool.invoke({"command": "pytest -q", "cwd": "D:/Github/Aelin/backend"})

    assert result["ok"] is True
    assert calls
    assert calls[0]["args"] == {"command": "pytest -q", "cwd": "D:/Github/Aelin/backend"}
    assert any(tr["name"] == "execute" and tr["status"] == "completed" for tr in tool_runs)


def test_deepagents_build_chat_tools_registers_present_files(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    calls: list[dict[str, object]] = []

    def _fake_tool_present_files(tool_context, args):  # type: ignore[no-untyped-def]
        calls.append({"tool_context": tool_context, "args": dict(args)})
        return {
            "ok": True,
            "summary": "presented 1 file(s)",
            "file_paths": ["D:/Github/Aelin/output/deepagents/user-1/default/outputs/demo.png"],
            "artifact_count": 1,
            "artifacts": [
                {
                    "path": "D:/Github/Aelin/output/deepagents/user-1/default/outputs/demo.png",
                    "relative_path": "output/deepagents/user-1/default/outputs/demo.png",
                    "name": "demo.png",
                    "mime_type": "image/png",
                    "size_bytes": 1024,
                    "preview_kind": "image-data-url",
                    "content": "data:image/png;base64,QUJDRA==",
                    "created_at": "2026-03-31T10:00:00+08:00",
                    "modified_at": "2026-03-31T10:00:00+08:00",
                }
            ],
        }

    monkeypatch.setattr(dag, "tool_present_files", _fake_tool_present_files)

    limiter = ToolCallLimiter(
        max_tool_calls=20,
        max_write_calls=10,
        allow_write_tools=True,
    )

    tools, tool_runs, _usage = dag.build_chat_tools(context=context, limiter=limiter)

    assert "present_files" in [tool.name for tool in tools]
    present_tool = next(t for t in tools if t.name == "present_files")
    result = present_tool.invoke({"filepaths": ["/outputs/demo.png"]})

    assert result["ok"] is True
    assert calls
    assert calls[0]["args"] == {"filepaths": ["/outputs/demo.png"]}
    assert any(
        tr["name"] == "present_files" and tr["status"] == "completed"
        for tr in tool_runs
    )


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


def test_deepagents_read_tool_retry_recovers_from_transient_failure(monkeypatch):
    from app.services.deepagents.assembly import tool_registry

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    limiter = ToolCallLimiter(max_tool_calls=4, max_write_calls=1, allow_write_tools=False)
    usage = ToolPolicyUsage()
    tool_runs: list[dict[str, object]] = []
    calls = {"count": 0}

    monkeypatch.setattr(tool_registry.settings, "deepagents_read_tool_retry_attempts", 1)
    monkeypatch.setattr(tool_registry.settings, "deepagents_read_tool_retry_backoff_seconds", 0.0)

    def _flaky_handler(_context, _args):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": False, "error": "web_search_timeout: upstream 504"}
        return {"ok": True, "total": 1, "summary": "found 1 web result"}

    result = tool_registry._invoke_tool(
        name="web_search",
        args={"action": "search", "query": "deepagents"},
        handler=_flaky_handler,
        context=context,
        limiter=limiter,
        usage=usage,
        tool_runs=tool_runs,  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert calls["count"] == 2
    assert "after 2 attempts" in str(tool_runs[0]["summary"])


def test_deepagents_write_tool_does_not_retry_transient_failures(monkeypatch):
    from app.services.deepagents.assembly import tool_registry

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    limiter = ToolCallLimiter(max_tool_calls=4, max_write_calls=2, allow_write_tools=True)
    usage = ToolPolicyUsage()
    tool_runs: list[dict[str, object]] = []
    calls = {"count": 0}

    monkeypatch.setattr(tool_registry.settings, "deepagents_read_tool_retry_attempts", 3)
    monkeypatch.setattr(tool_registry.settings, "deepagents_read_tool_retry_backoff_seconds", 0.0)

    def _flaky_handler(_context, _args):  # noqa: ANN001
        calls["count"] += 1
        return {"ok": False, "error": "execute_timeout: upstream 504"}

    result = tool_registry._invoke_tool(
        name="execute",
        args={"command": "pytest -q"},
        handler=_flaky_handler,
        context=context,
        limiter=limiter,
        usage=usage,
        tool_runs=tool_runs,  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert calls["count"] == 1


def test_deepagents_http_timeout_never_undercuts_model_node_budget(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    service = SimpleNamespace(timeout_seconds=180.0)
    monkeypatch.setattr(dag.settings, "deepagents_stream_idle_timeout_seconds", 45.0)
    monkeypatch.setattr(dag.settings, "deepagents_run_timeout_seconds", 120.0)

    timeout = dag._build_deepagents_http_timeout(service)  # type: ignore[arg-type]

    assert timeout.connect == 180.0
    assert timeout.read == 120.0
    assert timeout.write == 180.0
    assert timeout.pool == 180.0


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
    assert "/memory/memory_index.json" in files
    content = _file_data_text(files["/memory/AGENTS.md"])
    assert "likes agents." in content
    assert any(path.startswith("/memory/") and path != "/memory/AGENTS.md" for path in files)


def test_deepagents_backend_factory_seeds_runtime_files(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag.settings, "deepagents_extra_skills_dir", "")

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    _agent, _usage, _tool_runs, files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        memory_text="# Memory\nremember this",
        skills_root=None,
    )

    backend_factory = captured.get("backend")
    assert callable(backend_factory)

    runtime = SimpleNamespace(state={})
    backend = backend_factory(runtime)

    runtime_files = runtime.state.get("files", {})
    if runtime_files:
        assert "/memory/AGENTS.md" in runtime_files
        assert "/runtime/capabilities.json" in runtime_files

    responses = backend.download_files(["/memory/AGENTS.md", "/runtime/capabilities.json"])
    decoded = [
        response.content.decode("utf-8") if response.content is not None else ""
        for response in responses
    ]
    assert "remember this" in decoded[0]
    assert '"available_attachment_ids"' in decoded[1]
    assert '"memory_index"' in decoded[1]
    assert _file_data_text(files["/memory/AGENTS.md"]) in decoded[0]
    if runtime_files:
        assert _file_data_text(runtime_files["/memory/AGENTS.md"]) in decoded[0]


def test_deepagents_backend_factory_preserves_async_downloads(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag.settings, "deepagents_extra_skills_dir", "")

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        memory_text="# Memory\nremember async",
        skills_root=None,
    )

    backend_factory = captured.get("backend")
    assert callable(backend_factory)

    runtime = SimpleNamespace(state={})
    backend = backend_factory(runtime)

    assert hasattr(backend, "adownload_files")

    responses = asyncio.run(
        backend.adownload_files(["/memory/AGENTS.md", "/runtime/capabilities.json"])
    )
    decoded = [
        response.content.decode("utf-8") if response.content is not None else ""
        for response in responses
    ]
    assert "remember async" in decoded[0]
    assert '"memory_index"' in decoded[1]


def test_deepagents_build_chat_agent_registers_model_timeout_middleware(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.model_timeout_middleware import (
        DeepAgentsModelRetryMiddleware,
        DeepAgentsModelTimeoutMiddleware,
        DeepAgentsToolAvailabilityMiddleware,
        DeepAgentsToolMessageSanitizerMiddleware,
    )

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag.settings, "deepagents_run_timeout_seconds", 33.0)
    monkeypatch.setattr(dag.settings, "deepagents_run_budget_seconds", 240.0)
    monkeypatch.setattr(dag.settings, "deepagents_model_transient_error_retries", 2)
    monkeypatch.setattr(dag.settings, "deepagents_model_transient_error_backoff_seconds", 0.5)
    monkeypatch.setattr(dag.settings, "desktop_plugin_execute_enabled", False)

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        memory_text="",
        skills_root=None,
    )

    middleware = list(captured.get("middleware") or [])
    assert len(middleware) == 4
    assert isinstance(middleware[0], DeepAgentsToolMessageSanitizerMiddleware)
    assert isinstance(middleware[1], DeepAgentsToolAvailabilityMiddleware)
    assert isinstance(middleware[2], DeepAgentsModelRetryMiddleware)
    assert middleware[2].max_retries == 2
    assert isinstance(middleware[3], DeepAgentsModelTimeoutMiddleware)
    assert middleware[3].timeout_seconds == 33.0
    assert middleware[3].run_budget_seconds == 240.0
    assert middleware[3].run_started_monotonic is not None
    assert context.run_budget_seconds == 240.0
    assert context.run_started_monotonic is not None
    assert context.run_deadline_monotonic is not None


def test_deepagents_build_chat_agent_preserves_custom_execute_tool(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents.model_timeout_middleware import (
        DeepAgentsModelRetryMiddleware,
        DeepAgentsModelTimeoutMiddleware,
        DeepAgentsToolAvailabilityMiddleware,
        DeepAgentsToolMessageSanitizerMiddleware,
    )

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag.settings, "deepagents_run_timeout_seconds", 33.0)
    monkeypatch.setattr(dag.settings, "deepagents_run_budget_seconds", 240.0)
    monkeypatch.setattr(dag.settings, "deepagents_model_transient_error_retries", 1)
    monkeypatch.setattr(dag.settings, "desktop_plugin_execute_enabled", True)

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=True),
        memory_text="",
        skills_root=None,
    )

    middleware = list(captured.get("middleware") or [])
    assert len(middleware) == 4
    assert isinstance(middleware[0], DeepAgentsToolMessageSanitizerMiddleware)
    assert isinstance(middleware[1], DeepAgentsToolAvailabilityMiddleware)
    assert isinstance(middleware[2], DeepAgentsModelRetryMiddleware)
    assert isinstance(middleware[3], DeepAgentsModelTimeoutMiddleware)


def test_deepagents_tool_timeout_policy_uses_category_budgets(monkeypatch):
    from app.services.deepagents.timeout_policy import select_tool_timeout_seconds
    from app.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "deepagents_tool_timeout_seconds_fast", 30.0)
    monkeypatch.setattr(app_settings, "deepagents_tool_timeout_seconds_io", 90.0)
    monkeypatch.setattr(app_settings, "deepagents_tool_timeout_seconds_execute", 180.0)

    assert select_tool_timeout_seconds(name="memory_search") == 30.0
    assert select_tool_timeout_seconds(name="web_search") == 90.0
    assert select_tool_timeout_seconds(name="execute", args={"timeout_ms": 120000}) == 180.0


def test_deepagents_tool_timeout_policy_respects_remaining_run_budget(monkeypatch):
    from app.services.deepagents.timeout_policy import select_tool_timeout_seconds
    from app.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "deepagents_tool_timeout_seconds_io", 90.0)

    assert select_tool_timeout_seconds(
        name="web_search",
        remaining_budget_seconds=18.0,
    ) == 18.0


def test_deepagents_skills_use_backend_routes_instead_of_preinjected_files(monkeypatch, tmp_path):
    from app.services.deepagents import deepagents_graph as dag

    skill_root = Path(tmp_path) / "skills"
    chrome_skill = skill_root / "chrome-cdp"
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
    monkeypatch.setattr(dag.settings, "deepagents_extra_skills_dir", "")

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
    assert "/skills/aelin/chrome-cdp/SKILL.md" not in files
    assert "/skills/aelin/chrome-cdp/scripts/cdp.mjs" not in files
    assert "/skills/aelin/chrome-cdp/references/guide.md" not in files
    assert "/runtime/capabilities.json" in files
    capabilities_text = _file_data_text(files["/runtime/capabilities.json"])
    assert '"mounted_skills"' in capabilities_text
    assert "/skills/aelin/chrome-cdp/" in capabilities_text

    backend_factory = captured.get("backend")
    assert callable(backend_factory)
    backend = backend_factory(SimpleNamespace(state={}))

    listed = backend.ls_info("/skills/aelin/")
    assert any(item["path"] == "/skills/aelin/chrome-cdp/" and item["is_dir"] for item in listed)

    responses = backend.download_files(
        [
            "/skills/aelin/chrome-cdp/SKILL.md",
            "/skills/aelin/chrome-cdp/scripts/cdp.mjs",
            "/skills/aelin/chrome-cdp/references/guide.md",
        ]
    )
    decoded = [
        response.content.decode("utf-8") if response.content is not None else ""
        for response in responses
    ]
    assert "Browser automation skill" in decoded[0]
    assert "console.log('ok')" in decoded[1]
    assert "# Guide" in decoded[2]


def test_deepagents_backend_maps_workspace_and_outputs_to_real_disk(monkeypatch, tmp_path):
    from app.services.deepagents import deepagents_graph as dag
    from app.services.deepagents import delivery_paths as delivery

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    fake_delivery_root = tmp_path / "deepagents-root"

    def _fake_get_delivery_paths(*, workspace: str, user_id: int | None = None, create: bool = True):
        root = fake_delivery_root / f"user-{int(user_id or 0)}" / workspace
        workspace_dir = root / "workspace"
        outputs_dir = root / "outputs"
        if create:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            outputs_dir.mkdir(parents=True, exist_ok=True)
        return delivery.DeepAgentsDeliveryPaths(
            root_dir=root,
            workspace_dir=workspace_dir,
            outputs_dir=outputs_dir,
        )

    monkeypatch.setattr(dag, "get_delivery_paths", _fake_get_delivery_paths)

    backend_factory = dag._build_agent_backend_factory(
        user_id=1,
        workspace="default",
        skills_root=tmp_path / "skills",
        extra_dir="",
        seed_files=None,
    )
    backend = backend_factory(SimpleNamespace(state={}))

    write_result = backend.write("/workspace/demo.txt", "hello workspace")
    assert not write_result.error
    assert (fake_delivery_root / "user-1" / "default" / "workspace" / "demo.txt").read_text(encoding="utf-8") == "hello workspace"

    output_result = backend.write("/outputs/report.md", "# Report")
    assert not output_result.error
    assert (fake_delivery_root / "user-1" / "default" / "outputs" / "report.md").read_text(encoding="utf-8") == "# Report"


def test_deepagents_backend_exposes_async_file_listing_and_download(tmp_path):
    from app.services.deepagents import deepagents_graph as dag

    skill_root = tmp_path / "skills"
    chrome_skill = skill_root / "chrome-cdp"
    chrome_skill.mkdir(parents=True)
    (chrome_skill / "SKILL.md").write_text("# chrome-cdp\n", encoding="utf-8")

    backend_factory = dag._build_agent_backend_factory(
        user_id=1,
        workspace="default",
        skills_root=skill_root,
        extra_dir="",
        seed_files=None,
    )
    backend = backend_factory(SimpleNamespace(state={}))

    async def _exercise_async_file_ops():
        listing = await backend.als_info("/skills/aelin/")
        downloads = await backend.adownload_files(["/skills/aelin/chrome-cdp/SKILL.md"])
        return listing, downloads

    listed, downloads = asyncio.run(_exercise_async_file_ops())

    assert any(item["path"] == "/skills/aelin/chrome-cdp/" and item["is_dir"] for item in listed)
    assert len(downloads) == 1
    assert downloads[0].content.replace(b"\r\n", b"\n") == b"# chrome-cdp\n"


def test_deepagents_model_timeout_middleware_stops_long_async_model_call(caplog):
    from app.services.deepagents.model_timeout_middleware import DeepAgentsModelTimeoutMiddleware

    middleware = DeepAgentsModelTimeoutMiddleware(timeout_seconds=0.01)
    request = SimpleNamespace(
        model=SimpleNamespace(model_name="gpt-test"),
        runtime=SimpleNamespace(context=SimpleNamespace(user_id=7, workspace="demo")),
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"name": "write_file"}],
    )

    async def _slow_handler(_request):  # noqa: ANN001
        await asyncio.sleep(0.05)
        return SimpleNamespace(result=[])

    with caplog.at_level("WARNING"):
        result = asyncio.run(middleware.awrap_model_call(request, _slow_handler))

    assert isinstance(result, AIMessage)
    assert "模型生成超时" in str(result.content)
    assert any("deepagents_model_timeout" in record.message for record in caplog.records)


def test_deepagents_model_retry_middleware_retries_transient_connection_errors(caplog):
    import httpx
    import openai
    from app.services.deepagents.model_timeout_middleware import DeepAgentsModelRetryMiddleware

    middleware = DeepAgentsModelRetryMiddleware(max_retries=2, backoff_seconds=0.0)
    request = SimpleNamespace(
        model=SimpleNamespace(model_name="gpt-test"),
        runtime=SimpleNamespace(context=SimpleNamespace(user_id=7, workspace="demo")),
        messages=[HumanMessage(content="hello")],
        tools=[SimpleNamespace(name="execute")],
    )
    attempts = {"count": 0}

    async def _flaky_handler(_request):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://example.com/v1/chat/completions"))
        return SimpleNamespace(result=["ok"])

    with caplog.at_level("WARNING"):
        result = asyncio.run(middleware.awrap_model_call(request, _flaky_handler))

    assert attempts["count"] == 2
    assert getattr(result, "result", None) == ["ok"]
    assert any("deepagents_model_transient_error" in record.message for record in caplog.records)


def test_deepagents_model_retry_middleware_returns_visible_error_after_exhaustion(caplog):
    import httpx
    import openai
    from app.services.deepagents.model_timeout_middleware import DeepAgentsModelRetryMiddleware

    middleware = DeepAgentsModelRetryMiddleware(max_retries=1, backoff_seconds=0.0)
    request = SimpleNamespace(
        model=SimpleNamespace(model_name="gpt-test"),
        runtime=SimpleNamespace(context=SimpleNamespace(user_id=7, workspace="demo")),
        messages=[HumanMessage(content="hello")],
        tools=[SimpleNamespace(name="execute")],
    )

    async def _always_fail(_request):  # noqa: ANN001
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://example.com/v1/chat/completions"))

    with caplog.at_level("WARNING"):
        result = asyncio.run(middleware.awrap_model_call(request, _always_fail))

    assert isinstance(result, AIMessage)
    assert "模型连接异常" in str(result.content)
    assert any("deepagents_model_transient_error" in record.message for record in caplog.records)


def test_deepagents_tool_message_sanitizer_patches_orphan_tool_messages(caplog):
    from app.services.deepagents.model_timeout_middleware import sanitize_orphan_tool_messages

    messages = [
        ToolMessage(content="file body", tool_call_id="read_file:0", name="read_file"),
    ]

    with caplog.at_level("WARNING"):
        sanitized = sanitize_orphan_tool_messages(messages)

    assert len(sanitized) == 2
    assert isinstance(sanitized[0], AIMessage)
    assert sanitized[0].tool_calls == [
        {
            "id": "read_file:0",
            "name": "read_file",
            "args": {},
            "type": "tool_call",
        }
    ]
    assert isinstance(sanitized[1], ToolMessage)
    assert any("deepagents_orphan_tool_message_patched" in record.message for record in caplog.records)


def test_deepagents_tool_message_sanitizer_keeps_valid_tool_sequences():
    from app.services.deepagents.model_timeout_middleware import sanitize_orphan_tool_messages

    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "write_file:0",
                    "name": "write_file",
                    "args": {"file_path": "/a.txt"},
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="Updated file /a.txt", tool_call_id="write_file:0"),
    ]

    sanitized = sanitize_orphan_tool_messages(messages)

    assert sanitized == messages


def test_deepagents_write_file_guard_rejects_oversized_content(monkeypatch, caplog):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag, "create_deep_agent", lambda **kwargs: object())
    monkeypatch.setattr(dag.settings, "deepagents_extra_skills_dir", "")
    monkeypatch.setattr(dag.settings, "deepagents_write_file_max_chars", 10)

    _agent, _usage, _tool_runs, _files = dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(
            max_tool_calls=8,
            max_write_calls=2,
            allow_write_tools=True,
        ),
        memory_text="",
        skills_root=None,
    )

    backend_factory = dag._build_agent_backend_factory(
        user_id=context.user_id,
        workspace=context.workspace,
        skills_root=dag._backend_root() / "deepagents_skills",
        extra_dir="",
    )
    backend = backend_factory(SimpleNamespace(state={}))

    with caplog.at_level("WARNING"):
        rejected = backend.write("/poster.html", "01234567890")

    assert rejected.error is not None
    assert "write_file_too_large" in rejected.error
    assert "configured limit of 10 chars" in rejected.error
    assert any("decision=rejected" in record.message for record in caplog.records)

    allowed = backend.write("/small.txt", "ok")
    assert allowed.error is None
    assert allowed.path == "/small.txt"


def test_deepagents_write_file_guard_is_disabled_by_default(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag, "create_deep_agent", lambda **kwargs: object())
    monkeypatch.setattr(dag.settings, "deepagents_extra_skills_dir", "")
    monkeypatch.setattr(dag.settings, "deepagents_write_file_max_chars", 0)

    backend_factory = dag._build_agent_backend_factory(
        user_id=context.user_id,
        workspace=context.workspace,
        skills_root=dag._backend_root() / "deepagents_skills",
        extra_dir="",
    )
    backend = backend_factory(SimpleNamespace(state={}))

    large_content = "A" * 60000
    result = backend.write("/poster.svg", large_content)

    assert result.error is None
    assert result.path == "/poster.svg"


def test_deepagents_system_prompt_guides_large_artifacts_to_execute_when_available(monkeypatch):
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)
    monkeypatch.setattr(dag, "_build_chat_model", lambda service, provider: object())
    monkeypatch.setattr(dag.settings, "desktop_plugin_execute_enabled", True)

    captured: dict[str, object] = {}

    def _fake_create_deep_agent(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dag, "create_deep_agent", _fake_create_deep_agent)

    dag.build_chat_agent(  # type: ignore[misc]
        service=SimpleNamespace(config=SimpleNamespace(model="fake-model", temperature=0.0)),
        provider="openai",
        context=context,
        limiter=ToolCallLimiter(max_tool_calls=8, max_write_calls=2, allow_write_tools=False),
        memory_text="",
        skills_root=None,
    )

    system_prompt = str(captured.get("system_prompt") or "")
    assert "do not stuff one enormous blob into a single write_file call" in system_prompt.lower()
    assert "/workspace" in system_prompt
    assert "/outputs" in system_prompt
    assert "present_files" in system_prompt


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
    assert "attachment_ids may be omitted and the runtime will apply the scoped ids automatically" in system_prompt
    assert "memory_search" in system_prompt
    assert "compact runtime memory projection" in system_prompt
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


def test_deepagents_attachment_tool_preserves_runnable_config_across_thread_pool():
    from app.services.deepagents import deepagents_graph as dag

    fake_web = _FakeWebSearch()
    fake_attachment = _FakeAttachmentService()
    context = _tool_context(
        fake_web,
        attachment_service=fake_attachment,
        available_attachment_ids=[],
    )
    limiter = ToolCallLimiter(max_tool_calls=4, max_write_calls=1, allow_write_tools=False)
    tools, _tool_runs, _usage = dag.build_chat_tools(context=context, limiter=limiter)
    attachment_tool = next(t for t in tools if t.name == "attachment_search")

    with set_config_context({"configurable": {"attachment_ids": [31, "32"]}}) as ctx:
        result = ctx.run(attachment_tool.invoke, {"query": "项目代号"})

    assert result["ok"] is True
    assert result["attachment_ids"] == [31, 32]
    assert fake_attachment.calls[0]["attachment_ids"] == [31, 32]


def test_render_poster_artifact_tool_returns_compact_local_artifacts():
    fake_web = _FakeWebSearch()
    context = _tool_context(fake_web)

    result = tool_render_poster_artifact(
        context,
        {
            "brief": "同济大学樱花季赏花活动海报，纯净精致，无元素重叠，构图完美",
            "preferred_format": "png",
            "filename_stem": "tool-compact-poster",
        },
    )

    assert result["ok"] is True
    assert result["artifact_count"] == 2
    assert len(result["file_paths"]) == 2
    assert "read_file step" in result["summary"]

    for artifact in result["artifacts"]:
        assert artifact["content"] == ""
        assert artifact["preview_kind"] in {"image-data-url", "pdf-data-url"}
        assert Path(str(artifact["path"])).is_file()
        assert str(artifact["relative_path"]).startswith("output/generated-posters/")
