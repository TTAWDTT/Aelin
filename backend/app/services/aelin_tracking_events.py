from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.connectors.douyin import _extract_sec_uid as extract_douyin_uid
from app.connectors.xiaohongshu import _extract_user_id as extract_xhs_uid
from app.connectors.weibo import _extract_uid as extract_weibo_uid
from app.models import Contact, Message

TRACKABLE_SOURCES = {
    "auto",
    "web",
    "rss",
    "x",
    "douyin",
    "xiaohongshu",
    "weibo",
    "bilibili",
    "email",
}


def normalize_track_source(raw: str) -> str:
    src = (raw or "").strip().lower()
    alias = {
        "mail": "email",
        "imap": "email",
        "twitter": "x",
        "xhs": "xiaohongshu",
        "b站": "bilibili",
    }
    src = alias.get(src, src)
    if src in TRACKABLE_SOURCES:
        return src
    return "auto"


def infer_tracking_source(target: str) -> str:
    text = (target or "").strip().lower()
    if any(token in text for token in ["抖音", "douyin"]):
        return "douyin"
    if any(token in text for token in ["小红书", "xiaohongshu", "xhs"]):
        return "xiaohongshu"
    if any(token in text for token in ["微博", "weibo"]):
        return "weibo"
    if any(token in text for token in ["bilibili", "b站", "up主"]):
        return "bilibili"
    if any(token in text for token in ["twitter", "x.com", "推特", "x "]):
        return "x"
    if any(token in text for token in ["邮件", "邮箱", "email"]):
        return "email"
    if any(token in text for token in ["rss", "订阅"]):
        return "rss"
    return "web"


def extract_x_username(target: str) -> str:
    text = (target or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:x\.com/|twitter\.com/)?@?([A-Za-z0-9_]{1,15})", text, flags=re.I)
    if not match:
        return ""
    return match.group(1).lstrip("@").strip()


def _extract_bilibili_uid(target: str) -> str:
    text = (target or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:space\.bilibili\.com/)?([1-9]\d{3,19})", text)
    return match.group(1).strip() if match else ""


def build_tracking_account_seed(source: str, target: str, query: str) -> dict[str, str] | None:
    text = (target or query or "").strip()
    if not text:
        return None

    if source == "x":
        username = extract_x_username(text)
        if not username:
            return None
        return {
            "provider": "x",
            "identifier": f"x:{username}",
            "feed_url": "",
            "feed_homepage_url": f"https://x.com/{username}",
            "feed_display_name": f"X @{username}",
        }
    if source == "douyin":
        sec_uid = extract_douyin_uid(text)
        if not sec_uid:
            return None
        return {
            "provider": "douyin",
            "identifier": sec_uid,
            "feed_url": "",
            "feed_homepage_url": f"https://www.douyin.com/user/{sec_uid}",
            "feed_display_name": "抖音用户",
        }
    if source == "xiaohongshu":
        user_id = extract_xhs_uid(text)
        if not user_id:
            return None
        return {
            "provider": "xiaohongshu",
            "identifier": user_id,
            "feed_url": "",
            "feed_homepage_url": f"https://www.xiaohongshu.com/user/profile/{user_id}",
            "feed_display_name": "小红书用户",
        }
    if source == "weibo":
        uid = extract_weibo_uid(text)
        if not uid:
            return None
        return {
            "provider": "weibo",
            "identifier": uid,
            "feed_url": "",
            "feed_homepage_url": f"https://weibo.com/u/{uid}",
            "feed_display_name": "微博用户",
        }
    if source == "bilibili":
        uid = _extract_bilibili_uid(text)
        if not uid:
            return None
        return {
            "provider": "bilibili",
            "identifier": f"bilibili:{uid}",
            "feed_url": "",
            "feed_homepage_url": f"https://space.bilibili.com/{uid}",
            "feed_display_name": f"B站 UP {uid}",
        }
    return None


def ensure_tracking_account(
    db: Session,
    *,
    user_id: int,
    source: str,
    target: str,
    query: str,
) -> Any | None:
    seed = build_tracking_account_seed(source, target, query)
    if not seed:
        return None

    existing = crud.get_account_by_provider_identifier(
        db,
        user_id=user_id,
        provider=seed["provider"],
        identifier=seed["identifier"],
    )
    if existing is not None:
        return existing

    try:
        return crud.create_connected_account(
            db,
            user_id=user_id,
            provider=seed["provider"],
            identifier=seed["identifier"],
            access_token=None,
            refresh_token=None,
            feed_url=seed.get("feed_url"),
            feed_homepage_url=seed.get("feed_homepage_url"),
            feed_display_name=seed.get("feed_display_name"),
        )
    except IntegrityError:
        db.rollback()
        return crud.get_account_by_provider_identifier(
            db,
            user_id=user_id,
            provider=seed["provider"],
            identifier=seed["identifier"],
        )
    except Exception:
        db.rollback()
        return None


def _extract_tracking_field(text: str, label: str) -> str:
    if not text:
        return ""
    match = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", text, flags=re.I)
    if not match:
        return ""
    return (match.group(1) or "").strip().splitlines()[0].strip()


def _parse_tracking_payload(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    return {
        "target": _extract_tracking_field(text, "跟踪目标"),
        "source": normalize_track_source(_extract_tracking_field(text, "来源") or "auto"),
        "status": _extract_tracking_field(text, "状态"),
        "query": _extract_tracking_field(text, "触发问题"),
        "time": _extract_tracking_field(text, "时间"),
    }


def _tracking_key(source: str, target: str) -> str:
    return f"{(source or 'auto').strip().lower()}::{(target or '').strip().lower()}"


def load_tracking_events(db: Session, *, user_id: int, limit: int) -> dict[str, dict[str, Any]]:
    contact = db.scalar(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.handle == "aelin:tracking",
        )
    )
    if contact is None:
        return {}

    rows = crud.list_messages(
        db,
        user_id=user_id,
        contact_id=int(contact.id),
        limit=max(20, min(500, int(limit) * 4)),
    )
    out: dict[str, dict[str, Any]] = {}
    for msg in rows:
        parsed = _parse_tracking_payload(msg.body or "")
        target = (parsed.get("target") or "").strip()
        if not target:
            continue
        source = normalize_track_source(parsed.get("source") or "auto")
        key = _tracking_key(source, target)
        if key in out:
            continue
        received = msg.received_at.isoformat() if msg.received_at else ""
        out[key] = {
            "message_id": int(msg.id),
            "target": target,
            "source": source,
            "query": (parsed.get("query") or "").strip(),
            "status": (parsed.get("status") or "").strip() or "active",
            "updated_at": received,
        }
    return out
