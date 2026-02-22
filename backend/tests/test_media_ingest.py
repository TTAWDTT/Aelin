from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.routers.aelin as aelin_router
from app.db import init_engine
from app.main import create_app
from app.models import Base
from app.services.media_ingest import MediaIngestError, MediaIngestOutput, MediaIngestService
from app.settings import settings


def _create_test_client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    init_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    import app.db as db_module

    db_module._engine = engine  # type: ignore[attr-defined]
    db_module._SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)  # type: ignore[attr-defined]

    tmp_media = tempfile.TemporaryDirectory()
    settings.media_dir = tmp_media.name
    app = create_app()
    client = TestClient(app)
    client._tmp_media = tmp_media  # type: ignore[attr-defined]
    return client


def _auth_headers(client: TestClient) -> dict[str, str]:
    reg = client.post("/api/v1/register", json={"email": "media@example.com", "password": "password123"})
    assert reg.status_code == 200, reg.text
    login = client.post(
        "/api/v1/token",
        data={"username": "media@example.com", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_media_ingest_endpoint_saves_diary(monkeypatch, tmp_path: Path):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._media_ingest,
        "ingest",
        lambda **kwargs: MediaIngestOutput(
            platform="youtube",
            url="https://www.youtube.com/watch?v=demo",
            canonical_url="https://www.youtube.com/watch?v=demo",
            title="Demo Video",
            source_type="subtitle_manual",
            source_language="zh",
            summary="总结：这是一个测试摘要。\n\n提炼信息：这里记录可复用信息。",
            insight_title="Demo Video 摘要",
            insight_markdown="## 概要\n\n测试内容",
            confidence=0.84,
            reason="test",
            limitations=["摘要主要基于字幕/文本，不覆盖纯视觉镜头语义。"],
            summary_overview="这是一个测试摘要。",
            information_note="这里记录可复用信息。",
        ),
    )
    diary_path = tmp_path / "users" / "1" / "insight.md"
    monkeypatch.setattr(
        aelin_router._tracking_file_memory,
        "append_insight",
        lambda **kwargs: diary_path,
    )

    resp = client.post(
        "/api/v1/aelin/media/ingest",
        json={"url": "https://www.youtube.com/watch?v=demo", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "saved"
    assert data.get("written") is True
    assert data.get("platform") == "youtube"
    assert data.get("summary_overview") == "这是一个测试摘要。"
    assert data.get("information_note") == "这里记录可复用信息。"
    assert "Aelinの日记" in str(data.get("message") or "")

    mem = client.get("/api/v1/agent/memory", headers=headers)
    assert mem.status_code == 200, mem.text
    notes = mem.json().get("notes") or []
    assert any("Aelinの日记" in str(item.get("content") or "") for item in notes)


def test_media_ingest_endpoint_returns_error_contract(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    def _raise_ingest(**kwargs):
        raise MediaIngestError("unsupported_platform", "platform not supported")

    monkeypatch.setattr(aelin_router._media_ingest, "ingest", _raise_ingest)
    resp = client.post(
        "/api/v1/aelin/media/ingest",
        json={"url": "https://example.com/video/1"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail") or {}
    assert detail.get("code") == "unsupported_platform"


def test_media_ingest_endpoint_quality_gate_skips_diary_write(monkeypatch, tmp_path: Path):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._media_ingest,
        "ingest",
        lambda **kwargs: MediaIngestOutput(
            platform="instagram",
            url="https://www.instagram.com/reel/demo/",
            canonical_url="https://www.instagram.com/reel/demo/",
            title="Demo Reel",
            source_type="description",
            source_language="unknown",
            summary="摘要已生成，但信息密度不足。",
            summary_overview="摘要已生成。",
            information_note="信息密度不足，暂不建议入库。",
            insight_title="Demo Reel 摘要",
            insight_markdown="## 概要\n\n低质量示例",
            confidence=0.21,
            reason="quality_gate_test",
            limitations=["当前未提取到字幕，改用描述文本生成，置信度较低。"],
            quality_score=0.34,
            quality_reason="描述文本过短，信息密度不足",
            quality_usable=False,
            needs_review=True,
            quality_flags=["description_too_short"],
        ),
    )

    state = {"append_called": False}

    def _append_insight_mock(**kwargs):
        state["append_called"] = True
        return tmp_path / "should-not-write.md"

    monkeypatch.setattr(aelin_router._tracking_file_memory, "append_insight", _append_insight_mock)

    resp = client.post(
        "/api/v1/aelin/media/ingest",
        json={"url": "https://www.instagram.com/reel/demo/", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("written") is False
    assert data.get("quality_usable") is False
    assert data.get("needs_review") is True
    assert "质量门禁未通过" in str(data.get("message") or "")
    assert state["append_called"] is False


def test_aelin_chat_auto_ingest_media_url(monkeypatch, tmp_path: Path):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._media_ingest,
        "ingest",
        lambda **kwargs: MediaIngestOutput(
            platform="youtube",
            url="https://www.youtube.com/watch?v=demo",
            canonical_url="https://www.youtube.com/watch?v=demo",
            title="Auto Demo Video",
            source_type="subtitle_manual",
            source_language="zh",
            summary="这是自动触发测试摘要。",
            summary_overview="自动触发测试摘要。",
            information_note="自动触发时沉淀了可复用信息。",
            insight_title="Auto Demo Video 摘要",
            insight_markdown="## 概要\n\n自动测试内容",
            confidence=0.83,
            reason="chat_auto_test",
            limitations=["摘要主要基于字幕/文本，不覆盖纯视觉镜头语义。"],
        ),
    )
    diary_path = tmp_path / "users" / "1" / "insight-chat.md"
    monkeypatch.setattr(
        aelin_router._tracking_file_memory,
        "append_insight",
        lambda **kwargs: diary_path,
    )

    resp = client.post(
        "/api/v1/aelin/chat",
        json={"query": "https://www.youtube.com/watch?v=demo", "workspace": "default"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Aelinの日记" in str(data.get("answer") or "")
    assert any((it.get("stage") == "media_ingest") for it in (data.get("tool_trace") or []))
    assert any((it.get("kind") == "open_tracking") for it in (data.get("actions") or []))


def test_tracking_file_memory_tree_endpoint(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    child = SimpleNamespace(
        name="2026-02-22.md",
        path="体育/NBA/2026-02-22.md",
        kind="file",
        title="Stephen Curry 纪要",
        preview="本周状态回升",
        updated_at="2026-02-22T00:00:00+00:00",
        source="web",
        topic_path="体育 > NBA",
        entry_kind="tracking_insight",
        children=[],
    )
    root = SimpleNamespace(
        name="体育",
        path="体育",
        kind="folder",
        title="",
        preview="",
        updated_at="2026-02-22T00:00:00+00:00",
        source="",
        topic_path="",
        entry_kind="",
        children=[child],
    )
    monkeypatch.setattr(
        aelin_router._tracking_file_memory,
        "list_diary_tree",
        lambda **kwargs: [root],
    )

    resp = client.get("/api/v1/aelin/tracking/file-memory/tree?workspace=default", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("total") == 1
    items = data.get("items") or []
    assert items and items[0].get("name") == "体育"
    assert (items[0].get("children") or [{}])[0].get("entry_kind") == "tracking_insight"


def test_media_ingest_detect_platforms():
    svc = MediaIngestService()
    assert svc.detect_platform("https://www.youtube.com/watch?v=1") == "youtube"
    assert svc.detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert svc.detect_platform("https://x.com/demo/status/123") == "x"
    assert svc.detect_platform("https://example.com/demo") == "unsupported"


def test_media_ingest_subtitle_parser_strips_timestamps(tmp_path: Path):
    svc = MediaIngestService()
    subtitle = tmp_path / "demo.zh.vtt"
    subtitle.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n你好，Aelin。\n\n"
        "00:00:02.000 --> 00:00:04.000\n这是测试字幕。\n",
        encoding="utf-8",
    )
    text = svc._subtitle_file_to_text(subtitle)
    assert "00:00" not in text
    assert "你好，Aelin。" in text
    assert "这是测试字幕。" in text


def test_media_ingest_classifies_cookie_required_error():
    svc = MediaIngestService()
    code, message = svc._classify_ytdlp_error(
        stderr="ERROR: [Douyin] 7110472242345069824: Fresh cookies (not necessarily logged in) are needed",
        stdout="null\n",
    )
    assert code == "auth_required"
    assert "cookies" in message.lower()


def test_media_ingest_detects_cookie_bootstrap_error():
    svc = MediaIngestService()
    assert svc._is_cookie_bootstrap_error(
        "ERROR: Could not copy Chrome cookie database.",
        "",
    )


def test_media_ingest_quality_gate_rejects_description_link_spam():
    svc = MediaIngestService()
    raw = "Benefits of walking #Walk #Fitness https://example.com/a https://example.com/b"
    cleaned = svc._sanitize_description_text(raw)
    quality = svc._assess_summary_quality(
        source_type="description",
        extracted_text=cleaned,
        overview="步行有益健康",
        information_note="仅有一句口号，缺乏具体证据与条件。",
        key_points=["步行有益健康"],
        evidence=[],
        actions=[],
        confidence=0.22,
    )
    assert quality["usable"] is False
    assert quality["needs_review"] is True
    assert (
        "质量评分" in str(quality["reason"])
        or "描述文本" in str(quality["reason"])
        or "提炼信息" in str(quality["reason"])
    )
