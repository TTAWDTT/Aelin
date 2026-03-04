from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
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

    settings.aelin_agent_loop_enabled = False
    settings.aelin_agent_loop_shadow_enabled = False
    app = create_app()
    return TestClient(app)


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


def test_media_ingest_douyin_auto_login_guide_retry_success(monkeypatch, tmp_path: Path):
    client = _create_test_client()
    headers = _auth_headers(client)

    state = {"calls": 0}

    def _ingest_mock(**kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise MediaIngestError("auth_required", "目标平台要求新鲜 cookies")
        return MediaIngestOutput(
            platform="douyin",
            url="https://www.douyin.com/video/7110472242345069824",
            canonical_url="https://www.douyin.com/video/7110472242345069824",
            title="Douyin Demo",
            source_type="subtitle_auto",
            source_language="zh",
            summary="自动引导后抓取成功。",
            insight_title="Douyin Demo 摘要",
            insight_markdown="## 概要\n\n自动引导后抓取成功。",
            confidence=0.73,
            reason="auto_guide_retry",
            limitations=["摘要主要基于字幕/文本，不覆盖纯视觉镜头语义。"],
            summary_overview="自动引导后抓取成功。",
            information_note="记录了可复用信息。",
        )

    monkeypatch.setattr(aelin_router._media_ingest, "ingest", _ingest_mock)
    monkeypatch.setattr(
        aelin_router._media_ingest,
        "run_douyin_login_guide",
        lambda **kwargs: {
            "ok": True,
            "platform": "douyin",
            "login_url": "https://www.douyin.com/",
            "profile_dir": str(tmp_path / "douyin_media"),
            "wait_seconds": 60,
            "cookie_count": 5,
            "message": "已检测到抖音登录态",
        },
    )
    monkeypatch.setattr(
        aelin_router._tracking_file_memory,
        "append_insight",
        lambda **kwargs: tmp_path / "douyin-insight.md",
    )

    resp = client.post(
        "/api/v1/aelin/media/ingest",
        json={
            "url": "https://www.douyin.com/video/7110472242345069824",
            "workspace": "default",
            "auto_login_guide": True,
            "login_wait_seconds": 60,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("platform") == "douyin"
    assert "自动完成抖音登录引导并重试" in str(data.get("message") or "")
    assert state["calls"] == 2


def test_media_ingest_douyin_auth_error_contains_guide(monkeypatch):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._media_ingest,
        "ingest",
        lambda **kwargs: (_ for _ in ()).throw(MediaIngestError("auth_required", "需要 cookies")),
    )
    monkeypatch.setattr(
        aelin_router._media_ingest,
        "build_douyin_auth_guidance",
        lambda **kwargs: {"platform": "douyin", "next_step": "POST /api/v1/aelin/media/auth/douyin/guide"},
    )

    resp = client.post(
        "/api/v1/aelin/media/ingest",
        json={
            "url": "https://www.douyin.com/video/7110472242345069824",
            "workspace": "default",
            "auto_login_guide": False,
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail") or {}
    assert detail.get("code") == "auth_required"
    guide = detail.get("guide") or {}
    assert guide.get("platform") == "douyin"


def test_media_auth_douyin_guide_endpoint(monkeypatch, tmp_path: Path):
    client = _create_test_client()
    headers = _auth_headers(client)

    monkeypatch.setattr(
        aelin_router._media_ingest,
        "run_douyin_login_guide",
        lambda **kwargs: {
            "ok": True,
            "platform": "douyin",
            "login_url": "https://www.douyin.com/",
            "profile_dir": str(tmp_path / "douyin_media"),
            "wait_seconds": 90,
            "cookie_count": 4,
            "message": "已检测到抖音登录态",
        },
    )

    resp = client.post(
        "/api/v1/aelin/media/auth/douyin/guide",
        json={"wait_seconds": 90},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "ready"
    assert data.get("platform") == "douyin"
    assert int(data.get("cookie_count") or 0) >= 1


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

    def _legacy_try(payload, db, current_user, event_cb=None, **kwargs):
        _ = kwargs
        return aelin_router._aelin_chat_impl(payload, db, current_user, event_cb=event_cb)

    monkeypatch.setattr(aelin_router, "_try_agent_loop_chat", _legacy_try)

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
    monkeypatch.setattr(aelin_router._memory, "update_after_turn", lambda *args, **kwargs: None)
    monkeypatch.setattr(aelin_router, "_pick_expression", lambda *_args, **_kwargs: "exp-03")
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
    trace = data.get("tool_trace") or []
    has_media_ingest = any((it.get("stage") == "media_ingest" and it.get("status") == "completed") for it in trace)
    assert has_media_ingest, f"Expected media_ingest stage in tool_trace, got: {trace!r}"
    assert "Aelinの日记" in str(data.get("answer") or "")
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


def test_media_ingest_fetch_metadata_uses_douyin_playwright_fallback(monkeypatch):
    svc = MediaIngestService()
    monkeypatch.setattr(
        svc,
        "_run_ytdlp",
        lambda **kwargs: SimpleNamespace(
            returncode=1,
            stderr="ERROR: [Douyin] 7110472242345069824: Fresh cookies (not necessarily logged in) are needed",
            stdout="null\n",
        ),
    )
    monkeypatch.setattr(
        svc,
        "_fetch_douyin_metadata_with_playwright",
        lambda **kwargs: {"title": "Douyin fallback", "description": "x" * 160},
    )

    meta = svc._fetch_metadata(
        ytdlp_cmd=["yt-dlp"],
        url="https://www.douyin.com/video/7110472242345069824",
        platform="douyin",
    )
    assert meta.get("title") == "Douyin fallback"


def test_media_ingest_fetch_metadata_douyin_fallback_failure_keeps_auth_error(monkeypatch):
    svc = MediaIngestService()
    monkeypatch.setattr(
        svc,
        "_run_ytdlp",
        lambda **kwargs: SimpleNamespace(
            returncode=1,
            stderr="ERROR: [Douyin] 7110472242345069824: Fresh cookies (not necessarily logged in) are needed",
            stdout="null\n",
        ),
    )
    monkeypatch.setattr(svc, "_fetch_douyin_metadata_with_playwright", lambda **kwargs: {})

    with pytest.raises(MediaIngestError) as exc:
        svc._fetch_metadata(
            ytdlp_cmd=["yt-dlp"],
            url="https://www.douyin.com/video/7110472242345069824",
            platform="douyin",
        )
    assert exc.value.code == "auth_required"


def test_media_ingest_extract_best_text_prefers_douyin_api(monkeypatch):
    svc = MediaIngestService()
    monkeypatch.setattr(
        svc,
        "_extract_subtitles",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call subtitles")),
    )
    text, source_type, language = svc._extract_best_text(
        ytdlp_cmd=["yt-dlp"],
        url="https://www.douyin.com/video/7110472242345069824",
        description=(
            "内容描述：Aelin 正在测试抖音抓取链路，验证 Playwright 拦截返回的 aweme 信息。"
            "页面摘要：这里包含可复用信息、作者信息、互动数据与评论摘录，可作为后续日记素材。"
        ),
        language_preferences=["zh"],
        platform="douyin",
        prefer_platform_text=True,
    )
    assert source_type == "douyin_api"
    assert language == "zh"
    assert "抖音抓取链路" in text


def test_media_ingest_quality_gate_rejects_short_douyin_api_text():
    svc = MediaIngestService()
    quality = svc._assess_summary_quality(
        source_type="douyin_api",
        extracted_text="短文本",
        overview="短",
        information_note="短",
        key_points=[],
        evidence=[],
        actions=[],
        confidence=0.2,
    )
    assert quality["usable"] is False
    assert quality["needs_review"] is True


def test_media_ingest_extract_douyin_video_url():
    svc = MediaIngestService()
    url = svc._extract_douyin_video_url(
        {
            "video": {
                "play_addr": {
                    "url_list": ["https://v3-dy.example.com/video.mp4"],
                }
            }
        }
    )
    assert url == "https://v3-dy.example.com/video.mp4"


def test_media_ingest_sanitize_douyin_body_preview_removes_noise():
    svc = MediaIngestService()
    text = (
        "开启读屏标签 读屏标签已关闭 推荐 关注 朋友 下载抖音 "
        "这条视频讲了清蒸鲈鱼的做法，先处理鱼再蒸八分钟。 "
        "京ICP备16016397号-3"
    )
    cleaned = svc._sanitize_douyin_body_preview(text)
    assert "开启读屏标签" not in cleaned
    assert "京ICP备" not in cleaned
    assert "清蒸鲈鱼" in cleaned


def test_media_ingest_transcribe_douyin_audio_skips_without_config():
    svc = MediaIngestService()
    svc._douyin_asr_backend = "openai"
    text = svc._transcribe_douyin_audio(
        video_url="https://v3-dy.example.com/video.mp4",
        service=None,
        provider="rule_based",
    )
    assert text == ""


def test_media_ingest_transcribe_douyin_audio_uses_resolved_ffmpeg(monkeypatch):
    svc = MediaIngestService()
    svc._douyin_asr_backend = "openai"
    svc._ffmpeg_command = ""
    monkeypatch.setattr(svc, "_resolve_ffmpeg_command", lambda: "ffmpeg-fallback")

    class _FakeTranscriptions:
        @staticmethod
        def create(**kwargs):
            _ = kwargs
            return SimpleNamespace(
                text=(
                    "这条视频在讲内容创作的方法。作者先给出背景，再拆解案例。"
                    "第一部分讨论选题，强调关注真实场景。第二部分讲剪辑，建议先保留关键证据。"
                    "第三部分讲发布节奏，推荐固定时间更新。最后提醒要复盘数据并持续优化表达。"
                    "同时补充了封面文案的写法、标题避坑方式、评论区互动策略，以及常见的转化误区。"
                    "作者建议先做小样本测试，再根据完播率和互动率逐步调整选题方向。"
                )
            )

    class _FakeService:
        def __init__(self):
            self.client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_FakeTranscriptions()))

        @staticmethod
        def is_configured() -> bool:
            return True

    captured: dict[str, object] = {}

    def _fake_run(cmd, **kwargs):
        _ = kwargs
        captured["cmd"] = cmd
        out_path = Path(str(cmd[-1]))
        out_path.write_bytes(b"x" * 6000)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.media_ingest.subprocess.run", _fake_run)

    text = svc._transcribe_douyin_audio(
        video_url="https://v3-dy.example.com/video.mp4",
        service=_FakeService(),
        provider="openai",
    )
    assert text
    cmd = captured.get("cmd")
    assert isinstance(cmd, list) and cmd
    assert str(cmd[0]) == "ffmpeg-fallback"


def test_media_ingest_transcribe_douyin_audio_disables_asr_on_404(monkeypatch):
    svc = MediaIngestService()
    svc._douyin_asr_backend = "openai"
    svc._ffmpeg_command = "ffmpeg-fallback"
    svc._douyin_asr_enabled = True

    class _FailingTranscriptions:
        @staticmethod
        def create(**kwargs):
            _ = kwargs
            raise RuntimeError("Error code: 404")

    class _FakeService:
        def __init__(self):
            self.client = SimpleNamespace(audio=SimpleNamespace(transcriptions=_FailingTranscriptions()))

        @staticmethod
        def is_configured() -> bool:
            return True

    def _fake_run(cmd, **kwargs):
        _ = kwargs
        out_path = Path(str(cmd[-1]))
        out_path.write_bytes(b"x" * 6000)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.media_ingest.subprocess.run", _fake_run)

    text = svc._transcribe_douyin_audio(
        video_url="https://v3-dy.example.com/video.mp4",
        service=_FakeService(),
        provider="openai",
    )
    assert text == ""
    assert svc._douyin_asr_enabled is True
    assert svc._douyin_asr_openai_available is False


def test_media_ingest_transcribe_douyin_audio_auto_prefers_local_then_stops(monkeypatch):
    svc = MediaIngestService()
    svc._douyin_asr_backend = "auto"
    svc._ffmpeg_command = "ffmpeg-fallback"
    calls: list[str] = []

    monkeypatch.setattr(svc, "_extract_audio_for_asr", lambda **kwargs: True)
    monkeypatch.setattr(
        svc,
        "_transcribe_douyin_audio_with_faster_whisper",
        lambda **kwargs: calls.append("local") or "本地转写结果",
    )
    monkeypatch.setattr(
        svc,
        "_transcribe_douyin_audio_with_openai",
        lambda **kwargs: calls.append("openai") or "远端转写结果",
    )

    text = svc._transcribe_douyin_audio(
        video_url="https://v3-dy.example.com/video.mp4",
        service=None,
        provider="rule_based",
    )
    assert text == "本地转写结果"
    assert calls == ["local"]


def test_media_ingest_transcribe_douyin_audio_auto_falls_back_to_openai(monkeypatch):
    svc = MediaIngestService()
    svc._douyin_asr_backend = "auto"
    svc._ffmpeg_command = "ffmpeg-fallback"
    calls: list[str] = []

    monkeypatch.setattr(svc, "_extract_audio_for_asr", lambda **kwargs: True)
    monkeypatch.setattr(
        svc,
        "_transcribe_douyin_audio_with_faster_whisper",
        lambda **kwargs: calls.append("local") or "",
    )
    monkeypatch.setattr(
        svc,
        "_transcribe_douyin_audio_with_openai",
        lambda **kwargs: calls.append("openai") or "远端转写结果",
    )

    text = svc._transcribe_douyin_audio(
        video_url="https://v3-dy.example.com/video.mp4",
        service=SimpleNamespace(),
        provider="openai",
    )
    assert text == "远端转写结果"
    assert calls == ["local", "openai"]


def test_media_ingest_download_douyin_video_for_asr_selects_video_file(monkeypatch, tmp_path: Path):
    svc = MediaIngestService()
    monkeypatch.setattr(svc, "_build_network_args", lambda **kwargs: [])

    def _fake_run_ytdlp(**kwargs):
        workdir = kwargs["cwd"]
        (workdir / "aelin_douyin_asr.mp4").write_bytes(b"x" * (30 * 1024))
        (workdir / "aelin_douyin_asr.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(svc, "_run_ytdlp", _fake_run_ytdlp)

    path = svc._download_douyin_video_for_asr(
        ytdlp_cmd=["yt-dlp"],
        page_url="https://www.douyin.com/video/7110472242345069824",
        workdir=tmp_path,
    )
    assert path is not None
    assert path.suffix.lower() == ".mp4"


def test_media_ingest_transcribe_douyin_audio_uses_ytdlp_download_fallback(monkeypatch, tmp_path: Path):
    svc = MediaIngestService()
    svc._douyin_asr_backend = "faster_whisper"
    svc._ffmpeg_command = "ffmpeg-fallback"

    downloaded = tmp_path / "fallback_video.mp4"
    downloaded.write_bytes(b"x" * (30 * 1024))
    monkeypatch.setattr(
        svc,
        "_download_douyin_video_for_asr",
        lambda **kwargs: downloaded,
    )

    calls: list[dict[str, object]] = []

    def _fake_extract(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(svc, "_extract_audio_for_asr", _fake_extract)
    monkeypatch.setattr(
        svc,
        "_transcribe_douyin_audio_with_faster_whisper",
        lambda **kwargs: "本地转写结果",
    )

    text = svc._transcribe_douyin_audio(
        video_url="",
        page_url="https://www.douyin.com/video/7110472242345069824",
        ytdlp_cmd=["yt-dlp"],
        service=None,
        provider="rule_based",
    )
    assert text == "本地转写结果"
    assert calls
    assert calls[0]["add_headers"] is False
    assert str(calls[0]["source_url"]).endswith("fallback_video.mp4")


def test_media_ingest_sanitize_asr_text_reduces_repetition():
    svc = MediaIngestService()
    raw = (
        "我恋我恋我恋我恋我恋。"
        "抖音热榜今天更新。"
        "抖音热榜今天更新。"
        "第十名点赞一百三十八万。"
        "第十名点赞一百三十八万。"
    )
    text = svc._sanitize_asr_text(raw)
    assert "我恋我恋我恋我恋我恋" not in text
    assert text.count("抖音热榜今天更新") <= 1
    assert text.count("第十名点赞一百三十八万") <= 1


def test_media_ingest_asr_noise_score_distinguishes_clean_text():
    svc = MediaIngestService()
    noisy = "我恋我恋我恋我恋我恋 我恋我恋我恋我恋我恋 抖音抖音抖音抖音"
    clean = (
        "这条视频分析了抖音热榜内容策略，提到第十名视频点赞超过一百万。"
        "作者给出了选题、剪辑和发布节奏三个可执行建议，并提醒复盘数据。"
    )
    assert svc._asr_noise_score(noisy) > svc._asr_noise_score(clean)


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
