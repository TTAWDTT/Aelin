from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import create_session, init_engine
from app.main import create_app
from app.models import Base, Contact, Message, MessageTopicTag
from app.settings import settings
from app.services import content_tagging


def _make_media_dir() -> str:
    root = Path(__file__).resolve().parents[1] / "_pytest_runtime" / "media"
    root.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = root / f"aelin-test-media-{uuid4().hex[:10]}"
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return str(candidate)
        except FileExistsError:
            continue


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

    settings.media_dir = _make_media_dir()
    app = create_app()
    return TestClient(app)


def _auth_headers(client: TestClient) -> tuple[dict[str, str], int]:
    reg = client.post("/api/v1/auth/register", json={"email": "desk@example.com", "password": "password123"})
    assert reg.status_code == 200, reg.text

    login = client.post(
        "/api/v1/auth/token",
        data={"username": "desk@example.com", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    user_id = int(me.json()["id"])
    return headers, user_id


def _seed_content_messages(*, user_id: int) -> list[int]:
    db = create_session()
    try:
        c1 = Contact(user_id=user_id, handle="x:@openai", display_name="@openai")
        c2 = Contact(user_id=user_id, handle="bilibili:2233", display_name="B站 UP")
        c3 = Contact(user_id=user_id, handle="weibo:123", display_name="微博用户")
        db.add_all([c1, c2, c3])
        db.flush()

        now = datetime.now(timezone.utc)
        rows = [
            Message(
                user_id=user_id,
                contact_id=c1.id,
                source="x",
                external_id="x:1",
                sender="@openai",
                subject="AI 模型发布",
                body_preview="OpenAI 发布了新模型并更新 API 文档 https://example.com/a",
                body="OpenAI 发布了新模型并更新 API 文档",
                received_at=now - timedelta(minutes=5),
                is_read=False,
            ),
            Message(
                user_id=user_id,
                contact_id=c2.id,
                source="bilibili",
                external_id="bili:1",
                sender="UP 主",
                subject="欧冠比赛分析",
                body_preview="本期聊英超和欧冠比赛，附图 https://example.com/img.jpg",
                body="本期聊英超和欧冠比赛",
                received_at=now - timedelta(minutes=12),
                is_read=False,
            ),
            Message(
                user_id=user_id,
                contact_id=c3.id,
                source="weibo",
                external_id="weibo:1",
                sender="科技博主",
                subject="芯片行业观察",
                body_preview="半导体和手机芯片最新动向",
                body="半导体和手机芯片最新动向",
                received_at=now - timedelta(minutes=30),
                is_read=True,
            ),
            Message(
                user_id=user_id,
                contact_id=c1.id,
                source="x",
                external_id="x:2",
                sender="@openai",
                subject="创业公司融资消息",
                body_preview="某创业公司完成新一轮融资",
                body="某创业公司完成新一轮融资",
                received_at=now - timedelta(minutes=60),
                is_read=True,
            ),
            Message(
                user_id=user_id,
                contact_id=c1.id,
                source="email",
                external_id="email:ignored",
                sender="mail@example.com",
                subject="邮箱消息",
                body_preview="这条不应出现在 Desk feed",
                body="这条不应出现在 Desk feed",
                received_at=now - timedelta(minutes=2),
                is_read=False,
            ),
        ]
        db.add_all(rows)
        c1.last_message_at = now
        c2.last_message_at = now - timedelta(minutes=12)
        c3.last_message_at = now - timedelta(minutes=30)
        db.commit()
        return [int(row.id) for row in rows]
    finally:
        db.close()


def test_desk_feed_tags_end_to_end():
    client = _create_test_client()
    headers, user_id = _auth_headers(client)
    _seed_content_messages(user_id=user_id)

    feed = client.get("/api/v1/desk/feed?limit=3", headers=headers)
    assert feed.status_code == 200, feed.text
    payload = feed.json()
    items = payload.get("items", [])
    assert len(items) == 3
    assert all(item["source"] in {"x", "weibo", "xiaohongshu", "douyin", "bilibili", "rss", "web"} for item in items)

    ts = [datetime.fromisoformat(item["received_at"].replace("Z", "+00:00")) for item in items]
    assert ts == sorted(ts, reverse=True)
    assert all(isinstance(item.get("tags"), list) and item["tags"] for item in items)

    next_before_at = payload.get("next_before_received_at")
    next_before_id = payload.get("next_before_id")
    assert next_before_at is not None
    assert isinstance(next_before_id, int)

    page2 = client.get(
        f"/api/v1/desk/feed?limit=3&before_received_at={next_before_at}&before_id={next_before_id}",
        headers=headers,
    )
    assert page2.status_code == 200, page2.text
    ids1 = {int(item["message_id"]) for item in items}
    ids2 = {int(item["message_id"]) for item in page2.json().get("items", [])}
    assert ids1.isdisjoint(ids2)

    filter_tag = items[0]["primary_tag"]
    by_tag = client.get(f"/api/v1/desk/feed?tag={filter_tag}&limit=20", headers=headers)
    assert by_tag.status_code == 200, by_tag.text
    filtered_items = by_tag.json().get("items", [])
    assert filtered_items
    assert all(filter_tag in row.get("tags", []) for row in filtered_items)

    by_source = client.get("/api/v1/desk/feed?source=weibo&limit=20", headers=headers)
    assert by_source.status_code == 200, by_source.text
    source_items = by_source.json().get("items", [])
    assert source_items
    assert all((row.get("source") or "").lower() == "weibo" for row in source_items)

    follow = client.post("/api/v1/desk/tags/follow", json={"tag": filter_tag}, headers=headers)
    assert follow.status_code == 200, follow.text
    assert follow.json()["tag"] == filter_tag

    tags_after_follow = client.get("/api/v1/desk/tags", headers=headers)
    assert tags_after_follow.status_code == 200, tags_after_follow.text
    followed = tags_after_follow.json().get("followed", [])
    assert any(row.get("tag") == filter_tag for row in followed)
    recommended = tags_after_follow.json().get("recommended", [])
    assert all(row.get("tag") != filter_tag for row in recommended)

    unfollow = client.delete(f"/api/v1/desk/tags/follow/{filter_tag}", headers=headers)
    assert unfollow.status_code == 200, unfollow.text
    assert unfollow.json()["deleted"] is True


def test_tagging_fallback_when_llm_fails():
    client = _create_test_client()
    headers, user_id = _auth_headers(client)
    message_ids = _seed_content_messages(user_id=user_id)
    target_id = int(message_ids[0])

    db = create_session()
    try:
        with patch("app.services.content_tagging._classify_with_llm", side_effect=RuntimeError("llm down")):
            ok = content_tagging.tag_message_by_id(db, user_id=user_id, message_id=target_id, allow_llm=True)
            assert ok is True
            db.commit()

        tag_rows = list(
            db.scalars(
                select(MessageTopicTag).where(
                    MessageTopicTag.user_id == user_id,
                    MessageTopicTag.message_id == target_id,
                )
            )
        )
        assert tag_rows
        assert any((row.method or "") in {"rule", "hybrid", "llm"} for row in tag_rows)
    finally:
        db.close()
