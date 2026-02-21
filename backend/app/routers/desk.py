from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Contact, Message, MessageTopicTag, User, UserFollowedTag
from app.routers.auth import get_current_user
from app.schemas import DeskFeedItem, DeskFeedResponse, DeskTagFollowRequest, DeskTagItem, DeskTagResponse
from app.services import content_tagging

router = APIRouter(prefix="/desk", tags=["desk"])

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_IMAGE_EXT_RE = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:$|[?#])", re.IGNORECASE)

_SOURCE_LABELS = {
    "x": "X",
    "weibo": "微博",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "Bilibili",
    "rss": "RSS",
    "web": "Web",
}


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    no_html = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", no_html).strip()


def _extract_urls(text: str | None) -> list[str]:
    raw = text or ""
    matches = _URL_RE.findall(raw)
    urls: list[str] = []
    for item in matches:
        value = item.strip().rstrip(".,);]")
        if value and value not in urls:
            urls.append(value)
    return urls


def _pick_external_url(*chunks: str | None) -> tuple[str | None, str | None]:
    all_urls: list[str] = []
    for chunk in chunks:
        all_urls.extend(_extract_urls(chunk))
    if not all_urls:
        return None, None

    image_url = next((url for url in all_urls if _IMAGE_EXT_RE.search(url)), None)
    external_url = next((url for url in all_urls if url != image_url), None) or all_urls[0]
    return image_url, external_url


def _format_received(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_cursor(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    # Query strings decode "+" as space; accept timestamps like "...T12:34:56 00:00".
    if re.search(r"T\d{2}:\d{2}:\d{2}(?:\.\d+)? \d{2}:\d{2}$", text):
        text = f"{text[:-6]}+{text[-5:]}"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fetch_tags_map(db: Session, *, user_id: int, message_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not message_ids:
        return {}
    rows = db.execute(
        select(
            MessageTopicTag.message_id,
            MessageTopicTag.tag,
            MessageTopicTag.confidence,
            MessageTopicTag.is_primary,
        )
        .where(
            MessageTopicTag.user_id == user_id,
            MessageTopicTag.message_id.in_(message_ids),
        )
        .order_by(
            MessageTopicTag.message_id.asc(),
            MessageTopicTag.is_primary.desc(),
            MessageTopicTag.confidence.desc(),
            MessageTopicTag.id.asc(),
        )
    ).all()

    tags_map: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        bucket = tags_map.setdefault(int(row.message_id), [])
        bucket.append(
            {
                "tag": str(row.tag or ""),
                "confidence": float(row.confidence or 0.0),
                "is_primary": bool(row.is_primary),
            }
        )
    return tags_map


def _query_feed_chunk(
    db: Session,
    *,
    user_id: int,
    sources: tuple[str, ...],
    q: str,
    before_received_at: datetime | None,
    before_id: int | None,
    limit: int,
) -> list[tuple[Message, Contact]]:
    stmt = (
        select(Message, Contact)
        .join(Contact, Contact.id == Message.contact_id)
        .where(
            Message.user_id == user_id,
            Message.source.in_(sources),
        )
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Message.sender).like(like)
            | func.lower(Message.subject).like(like)
            | func.lower(Message.body_preview).like(like)
        )

    if before_received_at is not None:
        if before_id and before_id > 0:
            stmt = stmt.where(
                (Message.received_at < before_received_at)
                | ((Message.received_at == before_received_at) & (Message.id < before_id))
            )
        else:
            stmt = stmt.where(Message.received_at < before_received_at)

    stmt = stmt.order_by(desc(Message.received_at), desc(Message.id)).limit(limit)
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


@router.get("/feed", response_model=DeskFeedResponse)
def get_desk_feed(
    tag: str = Query(default="all", max_length=64),
    source: str = Query(default="", max_length=200),
    q: str = Query(default="", max_length=220),
    limit: int = Query(default=20, ge=1, le=40),
    before_received_at: str | None = Query(default=None),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    tag_norm = content_tagging.normalize_follow_tag(tag)
    tag_filter = "" if tag_norm.lower() == "all" else tag_norm
    q_norm = (q or "").strip()
    source_parts = [part.strip().lower() for part in (source or "").split(",") if part.strip()]
    source_set = {part for part in source_parts if part in content_tagging.CONTENT_SOURCES}
    source_filter = tuple(sorted(source_set)) if source_set else tuple(sorted(content_tagging.CONTENT_SOURCES))

    cursor_at = _parse_cursor(before_received_at)
    cursor_id = int(before_id or 0) if before_id else None

    matched: list[tuple[Message, Contact]] = []
    attempts = 0
    while len(matched) < (limit + 1) and attempts < 8:
        attempts += 1
        chunk = _query_feed_chunk(
            db,
            user_id=current_user.id,
            sources=source_filter,
            q=q_norm,
            before_received_at=cursor_at,
            before_id=cursor_id,
            limit=max(40, limit * 3),
        )
        if not chunk:
            break

        message_ids = [int(item[0].id) for item in chunk]
        tags_map = _fetch_tags_map(db, user_id=current_user.id, message_ids=message_ids)
        missing_ids = [mid for mid in message_ids if mid not in tags_map]
        if missing_ids:
            content_tagging.ensure_rule_tags_for_messages(db, user_id=current_user.id, message_ids=missing_ids)
            content_tagging.enqueue_tagging_job(user_id=current_user.id, message_ids=missing_ids, allow_llm=True)
            tags_map = _fetch_tags_map(db, user_id=current_user.id, message_ids=message_ids)

        for item in chunk:
            message = item[0]
            rows = tags_map.get(int(message.id), [])
            tag_values = [str(row["tag"]) for row in rows if str(row.get("tag") or "")]
            if not tag_values:
                tag_values = ["其他"]
            primary_row = next((row for row in rows if bool(row.get("is_primary"))), None)
            primary_tag = str(primary_row["tag"]) if primary_row and primary_row.get("tag") else tag_values[0]
            if tag_filter and tag_filter not in tag_values:
                continue
            matched.append(item)
            if len(matched) >= (limit + 1):
                break

        last_message = chunk[-1][0]
        cursor_at = last_message.received_at
        if cursor_at is not None and cursor_at.tzinfo is None:
            cursor_at = cursor_at.replace(tzinfo=timezone.utc)
        cursor_id = int(last_message.id)

    selected = matched[:limit]
    selected_ids = [int(item[0].id) for item in selected]
    selected_tags_map = _fetch_tags_map(db, user_id=current_user.id, message_ids=selected_ids)

    items: list[DeskFeedItem] = []
    for message, contact in selected:
        tag_rows = selected_tags_map.get(int(message.id), [])
        tags = [str(row["tag"]) for row in tag_rows if str(row.get("tag") or "")]
        if not tags:
            tags = ["其他"]
        primary_row = next((row for row in tag_rows if bool(row.get("is_primary"))), None)
        primary_tag = str(primary_row["tag"]) if primary_row and primary_row.get("tag") else tags[0]

        clean_preview = _clean_text(message.body_preview or message.body or "")
        title = _clean_text(message.subject) or clean_preview[:96] or "未命名内容"
        preview = clean_preview[:320]
        image_url, external_url = _pick_external_url(message.body_preview, message.subject, message.body)

        items.append(
            DeskFeedItem(
                message_id=int(message.id),
                contact_id=int(message.contact_id),
                source=str(message.source or ""),
                source_label=_SOURCE_LABELS.get(str(message.source or "").lower(), str(message.source or "")),
                sender=str(message.sender or contact.display_name or ""),
                sender_avatar_url=contact.avatar_url,
                title=title,
                preview=preview,
                image_url=image_url,
                external_url=external_url,
                received_at=_format_received(message.received_at),
                is_read=bool(message.is_read),
                tags=tags[:5],
                primary_tag=primary_tag,
            )
        )

    next_before_received_at = None
    next_before_id = None
    if len(matched) > limit:
        extra_message = matched[limit][0]
        next_before_received_at = _format_received(extra_message.received_at) or None
        next_before_id = int(extra_message.id)

    return DeskFeedResponse(
        items=items,
        next_before_received_at=next_before_received_at,
        next_before_id=next_before_id,
    )


def _build_tag_stats(db: Session, *, user_id: int) -> dict[str, dict[str, Any]]:
    now = datetime.now(timezone.utc)
    since_14d = now - timedelta(days=14)
    since_7d = now - timedelta(days=7)

    rows = db.execute(
        select(
            MessageTopicTag.tag.label("tag"),
            func.count(MessageTopicTag.id).label("count_14d"),
            func.sum(case((Message.received_at >= since_7d, 1), else_=0)).label("count_7d"),
            func.count(func.distinct(Message.source)).label("source_count"),
            func.max(Message.received_at).label("last_seen_at"),
        )
        .join(
            Message,
            (Message.id == MessageTopicTag.message_id) & (Message.user_id == MessageTopicTag.user_id),
        )
        .where(
            MessageTopicTag.user_id == user_id,
            Message.source.in_(tuple(sorted(content_tagging.CONTENT_SOURCES))),
            Message.received_at >= since_14d,
        )
        .group_by(MessageTopicTag.tag)
    ).all()

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        tag = str(row.tag or "").strip()
        if not tag:
            continue
        last_seen = row.last_seen_at
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age_hours = 999.0
        if last_seen is not None:
            age_hours = max(0.0, (now - last_seen).total_seconds() / 3600.0)
        recency_boost = max(0.0, 2.0 - age_hours / 48.0)
        count_14d = int(row.count_14d or 0)
        count_7d = int(row.count_7d or 0)
        source_count = int(row.source_count or 0)
        score = float(count_14d) + float(source_count) * 1.5 + recency_boost
        stats[tag] = {
            "count_14d": count_14d,
            "count_7d": count_7d,
            "source_count": source_count,
            "last_seen_at": last_seen,
            "score": round(score, 4),
        }
    return stats


@router.get("/tags", response_model=DeskTagResponse)
def get_desk_tags(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stats = _build_tag_stats(db, user_id=current_user.id)
    followed_rows = list(
        db.scalars(
            select(UserFollowedTag)
            .where(UserFollowedTag.user_id == current_user.id)
            .order_by(UserFollowedTag.updated_at.desc(), UserFollowedTag.id.desc())
        )
    )
    followed_tags = [str(row.tag or "").strip() for row in followed_rows if str(row.tag or "").strip()]
    followed_set = set(followed_tags)

    def to_item(tag: str) -> DeskTagItem:
        row = stats.get(tag, {})
        return DeskTagItem(
            tag=tag,
            count_7d=int(row.get("count_7d") or 0),
            last_seen_at=content_tagging.utc_iso_or_none(row.get("last_seen_at")),
            score=float(row.get("score") or 0.0),
        )

    followed = [to_item(tag) for tag in followed_tags]
    followed.sort(key=lambda item: (item.count_7d, item.score, item.tag), reverse=True)

    non_followed_stats = [(tag, row) for tag, row in stats.items() if tag not in followed_set]
    non_followed_stats.sort(
        key=lambda item: (
            int(item[1].get("count_14d") or 0),
            float(item[1].get("score") or 0.0),
            item[0],
        ),
        reverse=True,
    )

    recommended = [to_item(tag) for tag, _ in non_followed_stats[:6]]
    discover = [to_item(tag) for tag, _ in non_followed_stats[:20]]
    return DeskTagResponse(
        followed=followed,
        recommended=recommended,
        discover=discover,
    )


@router.post("/tags/follow", response_model=DeskTagItem)
def follow_tag(
    payload: DeskTagFollowRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    tag = content_tagging.normalize_follow_tag(payload.tag)
    existing = db.scalar(
        select(UserFollowedTag).where(
            UserFollowedTag.user_id == current_user.id,
            UserFollowedTag.tag == tag,
        )
    )
    if existing is None:
        db.add(UserFollowedTag(user_id=current_user.id, tag=tag))
        db.commit()
    stats = _build_tag_stats(db, user_id=current_user.id).get(tag, {})
    return DeskTagItem(
        tag=tag,
        count_7d=int(stats.get("count_7d") or 0),
        last_seen_at=content_tagging.utc_iso_or_none(stats.get("last_seen_at")),
        score=float(stats.get("score") or 0.0),
    )


@router.delete("/tags/follow/{tag}")
def unfollow_tag(
    tag: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    tag_norm = content_tagging.normalize_follow_tag(tag)
    row = db.scalar(
        select(UserFollowedTag).where(
            UserFollowedTag.user_id == current_user.id,
            UserFollowedTag.tag == tag_norm,
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()
        return {"deleted": True, "tag": tag_norm}
    return {"deleted": False, "tag": tag_norm}
