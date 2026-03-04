from __future__ import annotations

import json
import hashlib
import logging
import os
import platform
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crud
from app.db import create_session
from app.db import get_session
from app.models import Contact, Message, TrackingTarget, User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinAction,
    AelinChatRequest,
    AelinChatResponse,
    AelinCitation,
    AelinDailyBrief,
    AelinDailyBriefAction,
    AelinLayoutCard,
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinNotificationItem,
    AelinPinRecommendationItem,
    AelinToolStep,
    AelinTodoItem,
    AgentFocusItemOut,
    AgentMemoryNoteOut,
)
from app.services.agent_memory import AgentMemoryService
from app.services import content_tagging
from app.services.aelin_tools import (
    AelinToolHub,
    run_aelin_structured_tools,
    should_attempt_aelin_tools,
    summarize_tool_results_for_prompt,
)
from app.services.aelin_agent_loop import AelinAgentLoop
from app.services.aelin_tool_policy import AelinToolPolicy
from app.services.aelin_chat_dispatch import (
    dispatch_aelin_chat as _dispatch_aelin_chat_service,
)
from app.services.aelin_media_pipeline import (
    build_media_ingest_answer as _build_media_ingest_answer,
    media_ingest_service as _media_ingest,
    save_media_ingest_diary as _save_media_ingest_diary,
)
from app.services.aelin_limits import MAX_IMAGE_DATA_URL_LENGTH
from app.services.aelin_runtime import (
    json_from_text as _json_from_text,
    normalize_workspace as _normalize_workspace,
    resolve_llm_service as _resolve_llm_service,
)
from app.services.aelin_tracking_events import (
    infer_tracking_source as _infer_tracking_source,
    load_tracking_events as _load_tracking_events,
    normalize_track_source as _normalize_track_source,
)
from app.services.memory_draft import ParallelMemoryDraftResult, build_parallel_memory_draft
from app.services.media_ingest import MediaIngestError
from app.services.openviking_bridge import tracking_file_memory_bridge
from app.services.summarizer import RuleBasedSummarizer
from app.services.sync_jobs import enqueue_sync_job
from app.services.web_search import WebSearchResult, WebSearchService
from app.services.tracking_autonomy import tracking_autonomy_service
from app.settings import settings
from app.routers.aelin_text_helpers import (
    _AELIN_EXPRESSION_IDS,
    _apply_answer_emoji,
    _build_chat_diary_entry,
    _build_source_indices_from_citations,
    _dedupe_citations,
    _expression_mapping_prompt,
    _extract_emoji_tag,
    _extract_expression_tag,
    _extract_first_json_object,
    _now_ms,
    _pick_expression,
    _sanitize_diary_answer,
)
router = APIRouter(prefix="/aelin", tags=["aelin"])
_log = logging.getLogger(__name__)

_memory = AgentMemoryService()
_summarizer = RuleBasedSummarizer()
_web_search = WebSearchService()
_tracking = tracking_autonomy_service
_tracking_file_memory = tracking_file_memory_bridge
_memory_draft_executor = ThreadPoolExecutor(
    max_workers=max(1, min(8, int(getattr(settings, "aelin_parallel_memory_draft_workers", 4) or 4))),
    thread_name_prefix="aelin-memory-draft",
)

_TRACKABLE_SOURCES = {
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

_MAX_WEB_SUBAGENTS = 5
_MAX_LOCAL_SUBAGENTS = 5
_MAX_CONTEXT_BOUNDARIES = 10
_WEB_SEARCH_MAX_RESULTS = 15
_WEB_SEARCH_FETCH_TOP_K = 5
_PROACTIVE_STATE_SOURCE_PREFIX = "proactive_state"
_PROACTIVE_SEEN_LIMIT = 180
_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(settings, "aelin_base_context_cache_ttl_seconds", 4.0) or 4.0),
)
_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES = max(
    0,
    int(getattr(settings, "aelin_base_context_cache_max_entries", 128) or 128),
)
_AELIN_TRACKING_SNAPSHOT_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(settings, "aelin_tracking_snapshot_cache_ttl_seconds", 10.0) or 10.0),
)
_AELIN_TRACKING_SNAPSHOT_CACHE_MAX_ENTRIES = max(
    0,
    int(getattr(settings, "aelin_tracking_snapshot_cache_max_entries", 256) or 256),
)

_MEDIA_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_MEDIA_SUMMARY_HINTS_ZH = (
    "总结",
    "摘要",
    "读",
    "读取",
    "理解",
    "解析",
    "梳理",
    "提炼",
    "看懂",
    "记住",
    "存入日记",
    "日记",
)
_MEDIA_SUMMARY_HINTS_EN = (
    "summary",
    "summarize",
    "recap",
    "digest",
    "analyze",
    "ingest",
    "diary",
)

_base_context_cache_lock = threading.Lock()
_base_context_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}

_tracking_snapshot_cache_lock = threading.Lock()
_tracking_snapshot_cache: dict[tuple[int, str, str, int], tuple[float, dict[str, Any]]] = {}


def _scoped_web_search_service(proxy_url: str = "") -> WebSearchService:
    return WebSearchService(
        timeout_seconds=float(getattr(_web_search, "timeout_seconds", 10.0) or 10.0),
        max_parallel_providers=int(getattr(_web_search, "max_parallel_providers", 4) or 4),
        max_parallel_fetch=int(getattr(_web_search, "max_parallel_fetch", 4) or 4),
        enable_reader_fallback=bool(getattr(_web_search, "enable_reader_fallback", True)),
        enable_browser_fallback=bool(getattr(_web_search, "enable_browser_fallback", True)),
        proxy_url=str(proxy_url or "").strip(),
    )


def _to_layout_cards(raw_cards: list[dict]) -> list[AelinLayoutCard]:
    out: list[AelinLayoutCard] = []
    for row in raw_cards[:120]:
        try:
            card = AelinLayoutCard(
                contact_id=int(row.get("contact_id") or 0),
                display_name=str(row.get("display_name") or f"contact-{row.get('contact_id') or 'unknown'}"),
                pinned=bool(row.get("pinned")),
                order=max(0, int(row.get("order") or 0)),
                x=max(0.0, float(row.get("x") or 0.0)),
                y=max(0.0, float(row.get("y") or 0.0)),
                width=float(row.get("width") or 312.0),
                height=float(row.get("height") or 316.0),
            )
        except Exception:
            continue
        if card.contact_id <= 0:
            continue
        out.append(card)
    out.sort(key=lambda x: (x.y, x.x, x.order, x.display_name))
    return out[:80]


def _build_fixed_profile_injection(bundle: dict[str, Any], *, max_items: int = 12) -> list[str]:
    if not isinstance(bundle, dict):
        return []

    safe_limit = max(1, min(24, int(max_items or 12)))
    out: list[str] = []
    seen: set[str] = set()

    def _read(item: Any, key: str) -> str:
        if isinstance(item, dict):
            return str(item.get(key) or "").strip()
        return str(getattr(item, key, "") or "").strip()

    def _push(text: str, *, label: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return
        normalized = cleaned.lower()
        if normalized in seen:
            return
        seen.add(normalized)
        out.append(f"- [{label}] {cleaned[:220]}")

    memory_layers = bundle.get("memory_layers")
    preference_rows = list(getattr(memory_layers, "preferences", []) or [])
    fact_rows = list(getattr(memory_layers, "facts", []) or [])

    for row in preference_rows[:10]:
        title = _read(row, "title")
        detail = _read(row, "detail")
        merged = f"{title}: {detail}" if detail else title
        _push(merged, label="preference")
        if len(out) >= safe_limit:
            return out[:safe_limit]

    for row in fact_rows[:10]:
        title = _read(row, "title")
        detail = _read(row, "detail")
        merged = f"{title}: {detail}" if detail else title
        _push(merged, label="fact")
        if len(out) >= safe_limit:
            return out[:safe_limit]

    profile_kinds = {
        "profile",
        "identity",
        "preference",
        "user_profile",
        "user_note",
        "manual_note",
    }
    notes = bundle.get("notes") if isinstance(bundle.get("notes"), list) else []
    for row in notes:
        kind = _read(row, "kind").lower()
        source = _read(row, "source").lower()
        if (kind not in profile_kinds) and (not source.startswith("profile")):
            continue
        content = _read(row, "content")
        _push(content, label="note")
        if len(out) >= safe_limit:
            break
    return out[:safe_limit]


def _build_context_bundle(db: Session, user_id: int, *, workspace: str, query: str) -> dict:
    workspace_norm = _normalize_workspace(workspace)
    snap = _memory.snapshot(db, user_id, query=query)
    note_rows = _memory.list_notes(db, user_id, limit=24)
    notes: list[AgentMemoryNoteOut] = []
    for row in note_rows:
        src = (row.source or "").strip().lower()
        if src == "todo" or src.startswith("card_layout"):
            continue
        notes.append(
            AgentMemoryNoteOut(
                id=row.id,
                kind=row.kind,
                content=row.content,
                source=row.source,
                updated_at=row.updated_at.isoformat() if row.updated_at else "",
            )
        )
        if len(notes) >= 12:
            break

    todos_raw = _memory.list_todos(db, user_id, include_done=False, limit=10)
    todos: list[AelinTodoItem] = []
    for row in todos_raw:
        try:
            todos.append(AelinTodoItem(**row))
        except Exception:
            continue

    pins_raw = _memory.recommend_pins(db, user_id, limit=6)
    pin_recommendations: list[AelinPinRecommendationItem] = []
    for row in pins_raw:
        try:
            pin_recommendations.append(AelinPinRecommendationItem(**row))
        except Exception:
            continue

    brief_raw = _memory.build_daily_brief(db, user_id)
    daily_brief = AelinDailyBrief(
        generated_at=brief_raw["generated_at"],
        summary=str(brief_raw.get("summary") or ""),
        top_updates=[AgentFocusItemOut(**item) for item in brief_raw.get("top_updates", [])],
        actions=[AelinDailyBriefAction(**item) for item in brief_raw.get("actions", [])],
    )

    layout_cards = _to_layout_cards(_memory.get_latest_layout_cards(db, user_id, workspace=workspace_norm))
    memory_layers_raw = _memory.build_memory_layers(db, user_id, workspace=workspace_norm, query=query)
    memory_layers = AelinMemoryLayers(
        facts=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("facts") or [])],
        preferences=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("preferences") or [])],
        in_progress=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("in_progress") or [])],
        generated_at=datetime.now(timezone.utc),
    )
    notifications = [
        AelinNotificationItem(**item)
        for item in _memory.build_notifications(db, user_id, limit=24)
    ]

    return {
        "workspace": workspace_norm,
        "summary": str(snap.get("summary") or ""),
        "focus_items": [AgentFocusItemOut(**item) for item in snap.get("focus_items", [])],
        "focus_items_raw": list(snap.get("focus_items", [])),
        "notes": notes,
        "notes_count": len(notes),
        "todos": todos,
        "pin_recommendations": pin_recommendations,
        "daily_brief": daily_brief,
        "layout_cards": layout_cards,
        "memory_layers": memory_layers,
        "notifications": notifications,
    }


def _prune_ttl_cache(
    cache: dict[Any, tuple[float, Any]],
    *,
    max_entries: int,
) -> None:
    if max_entries <= 0:
        cache.clear()
        return
    overflow = len(cache) - max_entries
    if overflow <= 0:
        return
    for key, _ in sorted(cache.items(), key=lambda item: float(item[1][0]))[:overflow]:
        cache.pop(key, None)


def _build_cached_base_context_bundle(db: Session, user_id: int, *, workspace: str) -> dict[str, Any]:
    workspace_norm = _normalize_workspace(workspace)
    if _AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS <= 0 or _AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES <= 0:
        return _build_context_bundle(db, user_id, workspace=workspace_norm, query="")

    cache_key = (int(user_id), workspace_norm)
    now = time.monotonic()
    with _base_context_cache_lock:
        hit = _base_context_cache.get(cache_key)
        if hit is not None:
            ts, cached_bundle = hit
            if (now - float(ts)) <= _AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS and isinstance(cached_bundle, dict):
                return cached_bundle
            _base_context_cache.pop(cache_key, None)

    bundle = _build_context_bundle(db, user_id, workspace=workspace_norm, query="")
    with _base_context_cache_lock:
        _base_context_cache[cache_key] = (now, bundle)
        _prune_ttl_cache(_base_context_cache, max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES)
    return bundle


def _empty_tracking_snapshot() -> dict[str, Any]:
    return {
        "active_items": [],
        "matched_items": [],
        "active_count": 0,
        "matched_count": 0,
        "matched_file_items": [],
    }


def _build_cached_tracking_snapshot(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    include_file_memory: bool,
    include_diary_memory: bool = False,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    if not query_text:
        return _empty_tracking_snapshot()

    workspace_norm = _normalize_workspace(workspace)
    query_key = _normalize_match_text(query_text)[:220]
    include_file_flag = 1 if include_file_memory else 0
    include_diary_flag = 1 if include_diary_memory else 0
    if _AELIN_TRACKING_SNAPSHOT_CACHE_TTL_SECONDS <= 0 or _AELIN_TRACKING_SNAPSHOT_CACHE_MAX_ENTRIES <= 0:
        return _build_planner_tracking_snapshot(
            db,
            user_id=user_id,
            workspace=workspace_norm,
            query=query_text,
            include_file_memory=include_file_memory,
            include_diary_memory=include_diary_memory,
        )

    cache_key = (int(user_id), workspace_norm, query_key, include_file_flag, include_diary_flag)
    now = time.monotonic()
    with _tracking_snapshot_cache_lock:
        hit = _tracking_snapshot_cache.get(cache_key)
        if hit is not None:
            ts, cached_snapshot = hit
            if (now - float(ts)) <= _AELIN_TRACKING_SNAPSHOT_CACHE_TTL_SECONDS and isinstance(cached_snapshot, dict):
                return cached_snapshot
            _tracking_snapshot_cache.pop(cache_key, None)

    snapshot = _build_planner_tracking_snapshot(
        db,
        user_id=user_id,
        workspace=workspace_norm,
        query=query_text,
        include_file_memory=include_file_memory,
        include_diary_memory=include_diary_memory,
    )
    with _tracking_snapshot_cache_lock:
        _tracking_snapshot_cache[cache_key] = (now, snapshot)
        _prune_ttl_cache(_tracking_snapshot_cache, max_entries=_AELIN_TRACKING_SNAPSHOT_CACHE_MAX_ENTRIES)
    return snapshot


def _to_citations(raw_focus_items: list[dict], max_items: int) -> list[AelinCitation]:
    items: list[AelinCitation] = []
    for row in raw_focus_items[: max(1, min(20, max_items))]:
        try:
            items.append(
                AelinCitation(
                    message_id=int(row.get("message_id") or 0),
                    source=str(row.get("source") or "unknown"),
                    source_label=str(row.get("source_label") or row.get("source") or "unknown"),
                    sender=str(row.get("sender") or ""),
                    sender_avatar_url=(
                        str(row.get("sender_avatar_url") or "").strip() or None
                    ),
                    title=str(row.get("title") or ""),
                    received_at=str(row.get("received_at") or ""),
                    score=float(row.get("score") or 0.0),
                )
            )
        except Exception:
            continue
    return items


def _fetch_local_focus_citations(
    *,
    user_id: int,
    query: str,
    max_citations: int,
) -> tuple[list[AelinCitation], str]:
    local_db = create_session()
    try:
        n = max(4, min(20, int(max_citations or 6) * 2))
        focus_items = _memory.build_focus_items(local_db, user_id, query=query, limit=n)
        rows = [
            {
                "message_id": int(item.message_id or 0),
                "source": str(item.source or "unknown"),
                "source_label": str(item.source or "unknown"),
                "sender": str(item.sender or ""),
                "sender_avatar_url": str(item.sender_avatar_url or "").strip() or None,
                "title": str(item.title or ""),
                "received_at": str(item.received_at or ""),
                "score": float(item.score or 0.0),
            }
            for item in focus_items
        ]
        return _to_citations(rows, max_citations), ""
    except Exception as exc:
        return [], str(exc)[:140]
    finally:
        try:
            local_db.close()
        except Exception:
            pass


def _hydrate_citation_avatars(
    db: Session,
    user_id: int,
    citations: list[AelinCitation],
) -> list[AelinCitation]:
    missing_ids = [int(it.message_id) for it in citations if not it.sender_avatar_url and int(it.message_id or 0) > 0]
    if not missing_ids:
        return citations

    rows = db.execute(
        select(Message.id, Contact.avatar_url)
        .join(Contact, Contact.id == Message.contact_id)
        .where(
            Message.user_id == user_id,
            Contact.user_id == user_id,
            Message.id.in_(missing_ids),
        )
    ).all()
    avatar_by_message_id: dict[int, str] = {}
    for message_id, avatar_url in rows:
        if avatar_url:
            avatar_by_message_id[int(message_id)] = str(avatar_url)

    if not avatar_by_message_id:
        return citations

    out: list[AelinCitation] = []
    for it in citations:
        if it.sender_avatar_url:
            out.append(it)
            continue
        avatar = avatar_by_message_id.get(int(it.message_id or 0))
        if avatar:
            out.append(it.model_copy(update={"sender_avatar_url": avatar}))
        else:
            out.append(it)
    return out


def _rule_based_answer(
    query: str,
    summary: str,
    citations: list[AelinCitation],
    *,
    brief_summary: str = "",
    todo_titles: list[str] | None = None,
    image_count: int = 0,
) -> str:
    image_tip = (
        f"\n\n你上传了 {image_count} 张图片。当前规则模式不具备图片理解能力，若需图像分析请配置支持视觉的模型。"
        if image_count > 0
        else ""
    )
    if not citations:
        todo_line = ""
        if todo_titles:
            todo_line = "\n\n你当前待跟进事项：\n" + "\n".join(f"- {title}" for title in todo_titles[:4])
        if summary:
            return (
                "我已在你的长期记忆中检索相关内容，但当前缺少足够的新证据。"
                f"\n\n当前记忆摘要：{_summarizer.summarize(summary)}"
                + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
                + todo_line
                + "\n\n建议：扩大追踪边界或先触发一次同步。"
                + image_tip
            )
        return (
            "当前还没有足够的信号证据。先连接数据源并同步后，我就能给出可追溯结论。"
            + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
            + todo_line
            + image_tip
        )

    top = citations[0]
    bullets = [
        f"- [{it.source_label}] {it.title}（{it.sender}，{it.received_at}）"
        for it in citations[:4]
    ]
    return (
        f"基于你最近的信号证据，和“{query.strip()}”最相关的线索是：\n"
        + "\n".join(bullets)
        + f"\n\n当前优先关注：{top.title}"
        + ("\n\n我也参考了你的长期记忆摘要。" if summary else "")
        + (f"\n\n今日简报：{brief_summary}" if brief_summary else "")
        + (
            "\n\n建议先处理待跟进事项：\n" + "\n".join(f"- {title}" for title in (todo_titles or [])[:3])
            if todo_titles
            else ""
        )
        + image_tip
    )


def _build_actions(
    query: str,
    citations: list[AelinCitation],
    *,
    has_todos: bool,
    track_suggestion: dict[str, str] | None = None,
) -> list[AelinAction]:
    actions: list[AelinAction] = [
        AelinAction(
            kind="open_desk",
            title="在 Desk 查看可视化证据",
            detail="打开 /desk，在卡片与时间线里核验上下文",
            payload={"path": "/desk", "query": query.strip()[:180]},
        ),
    ]
    if citations:
        actions.insert(
            0,
            AelinAction(
                kind="open_message",
                title="打开最高相关消息",
                detail=f"查看：{citations[0].title}",
                payload={"message_id": str(citations[0].message_id), "query": query.strip()[:180]},
            ),
        )
    if track_suggestion:
        target = str(track_suggestion.get("target") or "").strip()
        source = str(track_suggestion.get("source") or "auto").strip().lower()
        reason = str(track_suggestion.get("reason") or "").strip()
        if target:
            actions.append(
                AelinAction(
                    kind="confirm_track",
                    title=f"跟踪 {target} 的后续动态？",
                    detail=reason or "Aelin 判断这可能值得持续跟踪。",
                    payload={
                        "target": target[:240],
                        "source": source[:32] or "auto",
                        "query": query.strip()[:500],
                    },
                ),
            )
    if "追踪" not in query and "follow" not in query.lower():
        actions.append(
            AelinAction(
                kind="track_topic",
                title="持续追踪该主题",
                detail="将当前问题加入长期追踪边界",
                payload={"query": query.strip()},
            )
        )
    if has_todos:
        actions.append(
            AelinAction(
                kind="open_todos",
                title="查看待办跟进",
                detail="在 Desk 的 Agent 面板里处理待办",
                payload={"path": "/desk", "query": query.strip()[:180]},
            )
        )
    return actions[:4]


def _normalize_images(raw_images: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw_images[:4]:
        data_url = str(getattr(item, "data_url", "") or "").strip()
        name = str(getattr(item, "name", "") or "").strip()[:120]
        if not data_url.startswith("data:image/"):
            continue
        if ";base64," not in data_url:
            continue
        if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
            continue
        out.append({"data_url": data_url, "name": name})
    return out


def _normalize_history(raw_turns: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw_turns[-12:]:
        role = str(getattr(item, "role", "") or "").strip().lower()
        content = str(getattr(item, "content", "") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        out.append({"role": role, "content": content[:3000]})
    return out


def _extract_first_supported_media_url(query: str) -> tuple[str, str] | None:
    text = str(query or "")
    if not text:
        return None
    for match in _MEDIA_URL_RE.finditer(text):
        raw_url = str(match.group(0) or "").strip().rstrip(".,;:!?)")
        if not raw_url:
            continue
        try:
            platform = _media_ingest.detect_platform(raw_url)
        except Exception:
            platform = "unsupported"
        if platform != "unsupported":
            return raw_url, platform
    return None


def _is_media_summary_intent(query: str, media_url: str) -> bool:
    text = str(query or "")
    stripped = text.replace(media_url, " ")
    stripped = _MEDIA_URL_RE.sub(" ", stripped)
    stripped = re.sub(r"[\s`~!@#$%^&*()_\-+=\[\]{};:'\",.<>/?，。！？、（）【】《》\|]+", " ", stripped).strip()
    if not stripped:
        return True

    lowered = stripped.lower()
    if any(token in lowered for token in _MEDIA_SUMMARY_HINTS_EN):
        return True
    if any(token in stripped for token in _MEDIA_SUMMARY_HINTS_ZH):
        return True
    return len(stripped) <= 6


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # Accept common fenced format: ```json { ... } ```
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _parse_json_payload(raw: str) -> Any | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Accept fenced JSON payloads and both object/array roots.
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except Exception:
            continue
    return None


def _normalize_track_source(raw: str) -> str:
    src = (raw or "").strip().lower()
    alias = {
        "mail": "email",
        "imap": "email",
        "twitter": "x",
        "xhs": "xiaohongshu",
        "b站": "bilibili",
    }
    src = alias.get(src, src)
    if src in _TRACKABLE_SOURCES:
        return src
    return "auto"


def _normalize_web_queries(query: str, items: Any, *, limit: int = _MAX_WEB_SUBAGENTS) -> list[str]:
    safe_limit = max(1, min(_MAX_WEB_SUBAGENTS, int(limit or _MAX_WEB_SUBAGENTS)))
    out: list[str] = []
    seen: set[str] = set()
    seen_sig: set[str] = set()

    def _query_sig(text: str) -> str:
        base = str(text or "").strip().lower()
        if not base:
            return ""
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", base)
        for phrase in (
            "latest",
            "recent",
            "today",
            "yesterday",
            "now",
            "current",
            "\u6700\u65b0",  # 最新
            "\u6700\u8fd1",  # 最近
            "\u4eca\u5929",  # 今天
            "\u6628\u5929",  # 昨天
            "\u524d\u5929",  # 前天
            "\u521a\u521a",  # 刚刚
            "\u5b9e\u65f6",  # 实时
            "\u76ee\u524d",  # 目前
            "\u6709\u4ec0\u4e48",  # 有什么
            "\u6709\u54ea\u4e9b",  # 有哪些
            "\u6709\u5565",  # 有啥
            "\u6709\u6ca1\u6709",  # 有没有
            "\u8bf7\u95ee",  # 请问
            "\u5e2e\u6211",  # 帮我
            "\u544a\u8bc9\u6211",  # 告诉我
        ):
            normalized = normalized.replace(phrase, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", normalized).strip()
        return normalized or base

    if isinstance(items, list):
        for it in items:
            text = str(it or "").strip()[:180]
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            sig = _query_sig(text)
            if sig and sig in seen_sig:
                continue
            seen.add(key)
            if sig:
                seen_sig.add(sig)
            out.append(text)
            if len(out) >= safe_limit:
                break
    if not out and query.strip():
        out.append(query.strip()[:180])
    return out[:safe_limit]


def _is_cjk_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _extract_search_subject_dynamic(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""

    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text)
    lowered = cleaned.lower()
    stop_phrases_cjk = [
        "\u6700\u8fd1",
        "\u6700\u65b0",
        "\u4eca\u5929",
        "\u6628\u5929",
        "\u524d\u5929",
        "\u521a\u521a",
        "\u5b9e\u65f6",
        "\u6253\u4e86",
        "\u6253\u4ec0\u4e48",
        "\u8fdb\u884c\u4e86",
        "\u6709\u4ec0\u4e48",
        "\u6709\u54ea\u4e9b",
        "\u6709\u5565",
        "\u6709\u6ca1\u6709",
        "\u6709\u5426",
        "\u4ec0\u4e48",
        "\u54ea\u4e9b",
        "\u51e0\u573a",
        "\u6bd4\u8d5b",
        "\u8d5b\u679c",
        "\u6bd4\u5206",
        "\u7ed3\u679c",
        "\u60c5\u51b5",
        "\u662f\u591a\u5c11",
        "\u591a\u5c11",
        "\u544a\u8bc9\u6211",
        "\u5e2e\u6211",
        "\u4e00\u4e0b",
        "\u8bf7\u95ee",
        "\u600e\u4e48",
        "\u5982\u4f55",
    ]
    stop_phrases_en = [
        "who won",
        "what",
        "latest",
        "recent",
        "today",
        "yesterday",
        "result",
        "results",
        "score",
        "scores",
        "game",
        "games",
        "match",
        "matches",
    ]
    subject = lowered
    for phrase in stop_phrases_cjk:
        subject = subject.replace(phrase, " ")
    for phrase in stop_phrases_en:
        subject = re.sub(rf"\b{re.escape(phrase)}\b", " ", subject)
    subject = re.sub(r"\s+", " ", subject).strip()
    # Drop dangling one-letter latin leftovers such as the trailing "s" from "games".
    subject = " ".join(token for token in subject.split(" ") if (len(token) > 1 or bool(re.search(r"[\u4e00-\u9fff]", token))))
    subject = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", subject).strip()
    if len(subject) >= 2:
        return subject[:90]

    leagues = re.findall(r"\b(?:nba|wnba|cba|nfl|nhl|mlb|epl)\b", lowered, flags=re.I)
    if leagues:
        uniq: list[str] = []
        seen: set[str] = set()
        for row in leagues:
            key = row.lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(row.upper())
        return " ".join(uniq)[:90]

    tokens = re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    if tokens:
        return " ".join(tokens[:4])[:90]
    return text[:90]


def _build_web_query_pack_dynamic(
    *,
    query: str,
    base_queries: list[str] | None,
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None = None,
    limit: int = _MAX_WEB_SUBAGENTS,
) -> list[str]:
    query_text = (query or "").strip()
    if not query_text:
        return []

    is_cjk = _is_cjk_text(query_text)
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}

    time_scope = str(contract.get("time_scope") or "").strip().lower()
    sports_intent = bool(contract.get("sports_result_intent")) or _is_sports_result_query(query_text)
    requires_citations = bool(contract.get("requires_citations"))
    freshness_hours = max(1, min(720, _safe_int(contract.get("freshness_hours"), 72)))
    time_sensitive = time_scope in {"today", "recent", "realtime"} or _is_time_sensitive_query(query_text)

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    subject = _extract_search_subject_dynamic(query_text) or query_text
    focused = subject if len(subject) >= 2 else query_text

    seeds: list[str] = []
    if focused and focused != query_text:
        seeds.append(focused[:180])

    # Put one recency-aware facet early so it survives top-k truncation.
    if time_sensitive:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u4eca\u5929",
                    f"{focused} {today}",
                ]
            )
        else:
            seeds.extend(
                [
                    f"{focused} today",
                    f"{focused} {today}",
                    f"{focused} latest",
                ]
            )

    if sports_intent:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u6bd4\u8d5b\u7ed3\u679c",
                    f"{focused} \u8d5b\u7a0b",
                    f"{focused} \u6218\u62a5",
                    f"{focused} \u5b98\u65b9 \u8d5b\u7a0b",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} \u6bd4\u8d5b\u7ed3\u679c",
                ]
            )
        else:
            seeds.extend(
                [
                    f"{focused} match result",
                    f"{focused} fixtures",
                    f"{focused} recap",
                    f"{focused} official schedule",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} result",
                ]
            )

    if time_sensitive:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u6700\u65b0",
                    f"{focused} \u4eca\u5929",
                    f"{focused} {today}",
                    f"{focused} {yesterday}",
                ]
            )
            if freshness_hours <= 48:
                seeds.append(f"{focused} \u6700\u8fd124\u5c0f\u65f6")
        else:
            seeds.extend(
                [
                    f"{focused} latest",
                    f"{focused} today",
                    f"{focused} {today}",
                    f"{focused} {yesterday}",
                ]
            )
            if freshness_hours <= 48:
                seeds.append(f"{focused} last 24 hours")

    if requires_citations:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u5b98\u65b9",
                    f"{focused} \u6570\u636e",
                    f"{focused} \u6765\u6e90",
                ]
            )
        else:
            seeds.extend([f"{focused} official", f"{focused} data", f"{focused} source"])

    matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []
    for row in matched_items[:2]:
        target = str(row.get("target") or row.get("query") or "").strip()[:140]
        if not target:
            continue
        if is_cjk:
            seeds.append(f"{target} \u6700\u65b0")
        else:
            seeds.append(f"{target} latest")

    if isinstance(base_queries, list):
        seeds.extend(str(it or "").strip()[:180] for it in base_queries if str(it or "").strip())
    seeds.append(query_text[:180])

    return _normalize_web_queries(query_text, seeds, limit=limit)


def _decompose_web_context_boundaries_dynamic(
    *,
    query: str,
    web_boundaries: list[dict[str, str]],
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    base_queries = [str(it.get("query") or "").strip() for it in web_boundaries if str(it.get("query") or "").strip()]

    fallback_queries = _build_web_query_pack_dynamic(
        query=query_text,
        base_queries=base_queries or [query_text],
        intent_contract=contract,
        tracking_snapshot=tracking,
        limit=_MAX_WEB_SUBAGENTS,
    )
    scope_map = {
        str(it.get("query") or "").strip().lower(): str(it.get("scope") or "").strip()
        for it in web_boundaries
        if str(it.get("query") or "").strip()
    }
    fallback_boundaries = [
        {"kind": "web", "query": q, "scope": (scope_map.get(q.lower()) or q)[:120]}
        for q in fallback_queries
    ]

    if provider == "rule_based" or not service.is_configured():
        return {
            "source": "fallback",
            "reason": "decomposer_unavailable",
            "boundaries": fallback_boundaries,
        }

    now_utc = datetime.now(timezone.utc).isoformat()
    prompt = (
        "You are Aelin Query Decomposer Agent.\n"
        "Dynamically create temporary web-search subagents (facets) for this request.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"facets\": [{\"scope\": string, \"query\": string, \"priority\": number, \"why\": string}],"
        "\"reason\": string"
        "}\n"
        "Rules:\n"
        "- Create 3 to 5 facets when possible.\n"
        "- Queries must be short search-ready strings.\n"
        "- Avoid near-duplicate paraphrases.\n"
        "- Cover direct answer + verification + authoritative source.\n"
        "- If time-sensitive, include explicit date/recency facets.\n"
    )
    user_msg = (
        f"user_query: {query_text}\n"
        f"intent_contract: {json.dumps(contract, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
        f"existing_web_queries: {json.dumps(base_queries, ensure_ascii=False, separators=(',', ':'))[:600]}\n"
        f"matched_tracking_count: {_safe_int(tracking.get('matched_count'), 0)}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )

    parsed_payload: Any | None = None
    retry_used = False
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed_payload = _parse_json_payload(str(raw or ""))
    except Exception:
        parsed_payload = None

    if parsed_payload is None:
        retry_used = True
        retry_prompt = (
            "Return JSON only. Root can be {\"facets\": [...], \"reason\": \"...\"} "
            "or a JSON array of facets."
        )
        retry_msg = (
            f"user_query: {query_text}\n"
            f"intent_contract: {json.dumps(contract, ensure_ascii=False, separators=(',', ':'))[:800]}\n"
            f"fallback_candidates: {json.dumps(fallback_queries, ensure_ascii=False, separators=(',', ':'))[:600]}\n"
            "Generate 3-5 orthogonal facets and return JSON only."
        )
        try:
            raw_retry = service._chat(
                messages=[
                    {"role": "system", "content": retry_prompt},
                    {"role": "user", "content": retry_msg},
                ],
                max_tokens=320,
                stream=False,
            )
            parsed_payload = _parse_json_payload(str(raw_retry or ""))
        except Exception:
            parsed_payload = None

    if parsed_payload is None:
        return {
            "source": "fallback",
            "reason": "decomposer_invalid_json_retry_failed",
            "boundaries": fallback_boundaries,
        }

    parsed_reason = "decomposer_llm"
    if isinstance(parsed_payload, dict):
        parsed_reason = str(parsed_payload.get("reason") or "").strip()[:180] or parsed_reason

    raw_facets: Any = None
    if isinstance(parsed_payload, dict):
        raw_facets = (
            parsed_payload.get("facets")
            or parsed_payload.get("queries")
            or parsed_payload.get("boundaries")
            or parsed_payload.get("tasks")
        )
    elif isinstance(parsed_payload, list):
        raw_facets = parsed_payload

    if not isinstance(raw_facets, list):
        return {
            "source": "fallback",
            "reason": "decomposer_no_facets",
            "boundaries": fallback_boundaries,
        }

    normalized: list[tuple[int, dict[str, str]]] = []
    seen: set[str] = set()
    seen_sig: set[str] = set()

    def _facet_sig(text: str) -> str:
        base = str(text or "").strip().lower()
        if not base:
            return ""
        normalized_text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", base)
        for phrase in (
            "latest",
            "recent",
            "today",
            "yesterday",
            "now",
            "current",
            "\u6700\u65b0",
            "\u6700\u8fd1",
            "\u4eca\u5929",
            "\u6628\u5929",
            "\u524d\u5929",
            "\u5b9e\u65f6",
            "\u521a\u521a",
            "\u6709\u4ec0\u4e48",
            "\u6709\u54ea\u4e9b",
            "\u6709\u5565",
            "\u6709\u6ca1\u6709",
            "\u8bf7\u95ee",
            "\u5e2e\u6211",
        ):
            normalized_text = normalized_text.replace(phrase, " ")
        normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
        normalized_text = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", normalized_text).strip()
        return normalized_text or base

    for idx, row in enumerate(raw_facets):
        if isinstance(row, str):
            q = str(row or "").strip()[:180]
            scope = q[:120]
            priority = idx + 1
        elif isinstance(row, dict):
            q = str(
                row.get("query")
                or row.get("search_query")
                or row.get("q")
                or row.get("task")
                or ""
            ).strip()[:180]
            scope = str(
                row.get("scope")
                or row.get("facet")
                or row.get("goal")
                or row.get("why")
                or q
            ).strip()[:120]
            priority = max(1, min(9, _safe_int(row.get("priority"), idx + 1)))
        else:
            continue
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        sig = _facet_sig(q)
        if sig and sig in seen_sig:
            continue
        seen.add(key)
        if sig:
            seen_sig.add(sig)
        normalized.append((priority, {"kind": "web", "query": q, "scope": scope or q[:120]}))
        if len(normalized) >= _MAX_WEB_SUBAGENTS:
            break

    if not normalized:
        return {
            "source": "fallback",
            "reason": "decomposer_empty",
            "boundaries": fallback_boundaries,
        }

    normalized.sort(key=lambda it: it[0])
    boundaries = [row for _, row in normalized][:_MAX_WEB_SUBAGENTS]
    reason = parsed_reason
    if retry_used:
        reason = f"{reason};retry=1"
    return {
        "source": "llm",
        "reason": reason,
        "boundaries": boundaries,
    }


def _extract_search_subject(query: str) -> str:
    return _extract_search_subject_dynamic(query)


def _extract_search_subject_legacy(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""
    cleaned = re.sub(r"[?？!！,，。;；:：()（）【】\\[\\]\"'`]+", " ", text)
    lowered = cleaned.lower()
    stop_phrases = [
        "最近",
        "最新",
        "今天",
        "昨日",
        "昨天",
        "前天",
        "刚刚",
        "实时",
        "打了",
        "进行了",
        "什么",
        "哪些",
        "几场",
        "比赛",
        "赛果",
        "比分",
        "结果",
        "情况",
        "是多少",
        "多少",
        "告诉我",
        "帮我",
        "一下",
        "请问",
        "有没有",
        "怎么",
        "如何",
        "who won",
        "what",
        "latest",
        "recent",
        "today",
        "yesterday",
        "result",
        "results",
        "score",
        "scores",
        "game",
        "games",
        "match",
        "matches",
    ]
    subject = lowered
    for phrase in stop_phrases:
        subject = subject.replace(phrase, " ")
    subject = re.sub(r"\s+", " ", subject).strip()
    if len(subject) >= 2:
        return subject[:90]

    leagues = re.findall(r"\b(?:nba|wnba|cba|nfl|nhl|mlb|epl)\b", lowered, flags=re.I)
    if leagues:
        uniq: list[str] = []
        seen: set[str] = set()
        for row in leagues:
            key = row.lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(row.upper())
        return " ".join(uniq)[:90]

    tokens = re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}", cleaned)
    if tokens:
        return " ".join(tokens[:4])[:90]
    return text[:90]


def _build_web_query_pack(
    *,
    query: str,
    base_queries: list[str] | None,
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None = None,
    limit: int = _MAX_WEB_SUBAGENTS,
) -> list[str]:
    return _build_web_query_pack_dynamic(
        query=query,
        base_queries=base_queries,
        intent_contract=intent_contract,
        tracking_snapshot=tracking_snapshot,
        limit=limit,
    )


def _build_web_query_pack_legacy(
    *,
    query: str,
    base_queries: list[str] | None,
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None = None,
    limit: int = _MAX_WEB_SUBAGENTS,
) -> list[str]:
    query_text = (query or "").strip()
    if not query_text:
        return []

    is_cjk = _is_cjk_text(query_text)
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}

    time_scope = str(contract.get("time_scope") or "").strip().lower()
    sports_intent = bool(contract.get("sports_result_intent")) or _is_sports_result_query(query_text)
    requires_citations = bool(contract.get("requires_citations"))
    freshness_hours = max(1, min(720, _safe_int(contract.get("freshness_hours"), 72)))
    time_sensitive = time_scope in {"today", "recent", "realtime"} or _is_time_sensitive_query(query_text)

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    subject = _extract_search_subject(query_text) or query_text
    focused = subject if len(subject) >= 2 else query_text

    seeds: list[str] = []
    if focused and focused != query_text:
        seeds.append(focused[:180])

    if sports_intent:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} 最新 比分",
                    f"{focused} 比分",
                    f"{focused} 赛果",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} 比分",
                ]
            )
        else:
            seeds.extend(
                [
                    f"{focused} latest score",
                    f"{focused} score",
                    f"{focused} result",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} score",
                ]
            )

    if time_sensitive:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} 最新",
                    f"{focused} 今天",
                    f"{focused} {today}",
                    f"{focused} {yesterday}",
                ]
            )
            if freshness_hours <= 48:
                seeds.append(f"{focused} 最近24小时")
        else:
            seeds.extend(
                [
                    f"{focused} latest",
                    f"{focused} today",
                    f"{focused} {today}",
                    f"{focused} {yesterday}",
                ]
            )
            if freshness_hours <= 48:
                seeds.append(f"{focused} last 24 hours")

    if requires_citations:
        if is_cjk:
            seeds.extend([f"{focused} 官方", f"{focused} 数据", f"{focused} 来源"])
        else:
            seeds.extend([f"{focused} official", f"{focused} data", f"{focused} source"])

    matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []
    for row in matched_items[:2]:
        target = str(row.get("target") or row.get("query") or "").strip()[:140]
        if not target:
            continue
        if is_cjk:
            seeds.append(f"{target} 最新")
        else:
            seeds.append(f"{target} latest")

    if isinstance(base_queries, list):
        seeds.extend(str(it or "").strip()[:180] for it in base_queries if str(it or "").strip())
    seeds.append(query_text[:180])

    return _normalize_web_queries(query_text, seeds, limit=limit)


def _decompose_web_context_boundaries(
    *,
    query: str,
    web_boundaries: list[dict[str, str]],
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    return _decompose_web_context_boundaries_dynamic(
        query=query,
        web_boundaries=web_boundaries,
        intent_contract=intent_contract,
        tracking_snapshot=tracking_snapshot,
        service=service,
        provider=provider,
    )


def _decompose_web_context_boundaries_legacy(
    *,
    query: str,
    web_boundaries: list[dict[str, str]],
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    base_queries = [str(it.get("query") or "").strip() for it in web_boundaries if str(it.get("query") or "").strip()]

    fallback_queries = _build_web_query_pack(
        query=query_text,
        base_queries=base_queries or [query_text],
        intent_contract=contract,
        tracking_snapshot=tracking,
        limit=_MAX_WEB_SUBAGENTS,
    )
    scope_map = {
        str(it.get("query") or "").strip().lower(): str(it.get("scope") or "").strip()
        for it in web_boundaries
        if str(it.get("query") or "").strip()
    }
    fallback_boundaries = [
        {"kind": "web", "query": q, "scope": (scope_map.get(q.lower()) or q)[:120]}
        for q in fallback_queries
    ]

    if provider == "rule_based" or not service.is_configured():
        return {
            "source": "fallback",
            "reason": "decomposer_unavailable",
            "boundaries": fallback_boundaries,
        }

    now_utc = datetime.now(timezone.utc).isoformat()
    prompt = (
        "You are Aelin Query Decomposer.\n"
        "Decompose one user retrieval request into multiple orthogonal web-search facets.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"facets\": [{\"scope\": string, \"query\": string, \"priority\": number, \"why\": string}],"
        "\"reason\": string"
        "}\n"
        "Rules:\n"
        "- Create 3 to 5 facets when possible.\n"
        "- Queries must be short search-ready strings, not one long user sentence.\n"
        "- Avoid near-duplicate paraphrases.\n"
        "- Cover direct answer facet + verification facet + authoritative source facet.\n"
        "- If time-sensitive, include explicit date/recency angle.\n"
    )
    user_msg = (
        f"user_query: {query_text}\n"
        f"intent_contract: {json.dumps(contract, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
        f"existing_web_queries: {json.dumps(base_queries, ensure_ascii=False, separators=(',', ':'))[:600]}\n"
        f"matched_tracking_count: {_safe_int(tracking.get('matched_count'), 0)}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )

    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return {
            "source": "fallback",
            "reason": "decomposer_invalid_json",
            "boundaries": fallback_boundaries,
        }

    raw_facets = parsed.get("facets")
    if not isinstance(raw_facets, list):
        return {
            "source": "fallback",
            "reason": "decomposer_no_facets",
            "boundaries": fallback_boundaries,
        }

    normalized: list[tuple[int, dict[str, str]]] = []
    seen: set[str] = set()
    for idx, row in enumerate(raw_facets):
        if isinstance(row, str):
            q = str(row or "").strip()[:180]
            scope = q[:120]
            priority = idx + 1
        elif isinstance(row, dict):
            q = str(
                row.get("query")
                or row.get("search_query")
                or row.get("q")
                or row.get("task")
                or ""
            ).strip()[:180]
            scope = str(
                row.get("scope")
                or row.get("facet")
                or row.get("goal")
                or row.get("why")
                or q
            ).strip()[:120]
            priority = max(1, min(9, _safe_int(row.get("priority"), idx + 1)))
        else:
            continue
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append((priority, {"kind": "web", "query": q, "scope": scope or q[:120]}))
        if len(normalized) >= _MAX_WEB_SUBAGENTS:
            break

    if not normalized:
        return {
            "source": "fallback",
            "reason": "decomposer_empty",
            "boundaries": fallback_boundaries,
        }

    normalized.sort(key=lambda it: it[0])
    boundaries = [row for _, row in normalized][:_MAX_WEB_SUBAGENTS]

    if len(boundaries) > 1:
        direct_idx = next(
            (i for i, row in enumerate(boundaries) if str(row.get("query") or "").strip().lower() == query_text.lower()),
            -1,
        )
        if direct_idx > 0:
            direct = boundaries.pop(direct_idx)
            boundaries.append(direct)

    reason = str(parsed.get("reason") or "").strip()[:180] or "decomposer_llm"
    return {
        "source": "llm",
        "reason": reason,
        "boundaries": boundaries,
    }


def _normalize_context_boundaries(
    query: str,
    raw_boundaries: Any,
    *,
    need_local_search: bool,
    need_web_search: bool,
    web_queries: list[str],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def count_kind(kind: str) -> int:
        return sum(1 for it in out if it["kind"] == kind)

    def push(kind: str, q: str, scope: str = "") -> None:
        k = (kind or "").strip().lower()
        if k not in {"local", "web"}:
            return
        if k == "local" and count_kind("local") >= _MAX_LOCAL_SUBAGENTS:
            return
        if k == "web" and count_kind("web") >= _MAX_WEB_SUBAGENTS:
            return
        text = (q or "").strip()[:180]
        if not text:
            return
        key = (k, text.lower())
        if key in seen:
            return
        seen.add(key)
        out.append({"kind": k, "query": text, "scope": (scope or text).strip()[:120]})

    if isinstance(raw_boundaries, list):
        for row in raw_boundaries:
            if len(out) >= _MAX_CONTEXT_BOUNDARIES:
                break
            if isinstance(row, str):
                push("web", row, row)
                continue
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or row.get("type") or row.get("source") or "").strip().lower()
            query_text = str(
                row.get("query") or row.get("facet") or row.get("task") or row.get("goal") or ""
            ).strip()
            scope = str(row.get("scope") or row.get("label") or "").strip()
            if kind in {"local_search", "local"}:
                push("local", query_text or query, scope)
            elif kind in {"web_search", "web"}:
                push("web", query_text or query, scope)

    if need_local_search and not any(it["kind"] == "local" for it in out):
        push("local", query, "local context")
    if need_web_search and not any(it["kind"] == "web" for it in out):
        for q in (web_queries or [query]):
            if len(out) >= _MAX_CONTEXT_BOUNDARIES:
                break
            push("web", q, q)

    out.sort(key=lambda x: 0 if x["kind"] == "local" else 1)
    return out[:_MAX_CONTEXT_BOUNDARIES]


def _build_trace_context_boundaries(
    *,
    query: str,
    raw_boundaries: Any,
    need_local_search: bool,
    need_web_search: bool,
    web_queries: list[str],
    intent_contract: dict[str, Any] | None,
    tracking_snapshot: dict[str, Any] | None,
    max_local: int = 2,
    max_web: int = 3,
) -> list[dict[str, str]]:
    local_cap = max(0, min(_MAX_LOCAL_SUBAGENTS, int(max_local or 2)))
    web_cap = max(0, min(_MAX_WEB_SUBAGENTS, int(max_web or 3)))
    boundaries = _normalize_context_boundaries(
        query,
        raw_boundaries,
        need_local_search=need_local_search,
        need_web_search=need_web_search,
        web_queries=web_queries,
    )
    local = [it for it in boundaries if str(it.get("kind") or "") == "local"][:local_cap]
    web = [it for it in boundaries if str(it.get("kind") or "") == "web"][:web_cap]

    # When trace route is enabled but planner does not provide explicit boundaries,
    # synthesize lightweight web facets so Trace Agent can verify trackability.
    if need_web_search and (not web):
        seeds = _build_web_query_pack(
            query=(query or "").strip(),
            base_queries=web_queries or [(query or "").strip()],
            intent_contract=intent_contract if isinstance(intent_contract, dict) else None,
            tracking_snapshot=tracking_snapshot if isinstance(tracking_snapshot, dict) else None,
            limit=web_cap,
        )
        for q in seeds[:web_cap]:
            web.append({"kind": "web", "query": q[:180], "scope": q[:120]})

    if need_local_search and (not local) and query.strip() and local_cap > 0:
        local.append(
            {
                "kind": "local",
                "query": query.strip()[:180],
                "scope": "trace local context",
            }
        )

    return [*local[:local_cap], *web[:web_cap]][:_MAX_CONTEXT_BOUNDARIES]


def _normalize_search_mode(raw: str) -> str:
    return "auto"


def _is_smalltalk_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return True
    signals = [
        "你好",
        "hello",
        "hi ",
        "在吗",
        "聊聊",
        "你觉得",
        "你怎么看",
        "心情",
        "焦虑",
        "emo",
        "哈哈",
        "谢谢",
        "晚安",
    ]
    return any(sig in text for sig in signals)


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _build_planner_tracking_snapshot(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    include_file_memory: bool = True,
    include_diary_memory: bool = False,
) -> dict[str, Any]:
    workspace_norm = _normalize_workspace(workspace)
    active_items: list[dict[str, Any]] = []

    try:
        rows = _tracking.list_targets(
            db,
            user_id=user_id,
            workspace=workspace_norm,
            limit=120,
            include_deleted=False,
        )
    except Exception:
        rows = []

    for row in rows:
        if row is None:
            continue
        if str(getattr(row, "status", "") or "").strip().lower() == "deleted":
            continue
        if getattr(row, "deleted_at", None) is not None:
            continue
        cfg = _json_from_text(getattr(row, "config_json", "") or "{}")
        target_text = (str(getattr(row, "display_name", "") or "") or str(getattr(row, "source_key", "") or "")).strip()
        if not target_text:
            continue
        active_items.append(
            {
                "target_id": int(getattr(row, "id", 0) or 0),
                "target": target_text[:255],
                "source": (str(getattr(row, "source_type", "web") or "web").strip().lower() or "web")[:32],
                "query": str(cfg.get("query") or "").strip()[:500],
                "status": str(getattr(row, "status", "active") or "active").strip().lower() or "active",
                "workspace": workspace_norm,
                "track_type": str(getattr(row, "track_type", "term") or "term").strip().lower() or "term",
                "updated_at": (
                    getattr(row, "updated_at", None).isoformat()
                    if getattr(row, "updated_at", None) is not None
                    else ""
                ),
            }
        )

    # Keep legacy tracking contact events as supplemental context when available.
    try:
        events = _load_tracking_events(db, user_id=user_id, limit=80)
    except Exception:
        events = {}
    if events:
        seen = {
            _tracking_key(str(it.get("source") or ""), str(it.get("target") or ""))
            for it in active_items
            if str(it.get("target") or "").strip()
        }
        for it in sorted(
            [x for x in (events or {}).values() if str(x.get("target") or "").strip()],
            key=lambda row: str(row.get("updated_at") or ""),
            reverse=True,
        ):
            key = _tracking_key(str(it.get("source") or ""), str(it.get("target") or ""))
            if key in seen:
                continue
            seen.add(key)
            active_items.append(
                {
                    "target_id": 0,
                    "target": str(it.get("target") or "").strip()[:255],
                    "source": _normalize_track_source(str(it.get("source") or "auto")),
                    "query": str(it.get("query") or "").strip()[:500],
                    "status": str(it.get("status") or "active").strip().lower() or "active",
                    "workspace": workspace_norm,
                    "track_type": "term",
                    "updated_at": str(it.get("updated_at") or ""),
                }
            )
            if len(active_items) >= 160:
                break

    active_items.sort(key=lambda it: str(it.get("updated_at") or ""), reverse=True)

    q_norm = _normalize_match_text(query)
    matched_items: list[dict[str, Any]] = []
    if q_norm:
        for it in active_items:
            target_norm = _normalize_match_text(str(it.get("target") or ""))
            query_norm = _normalize_match_text(str(it.get("query") or ""))
            if not target_norm and not query_norm:
                continue
            if target_norm and (target_norm in q_norm or q_norm in target_norm):
                matched_items.append(it)
            elif query_norm and (query_norm in q_norm or q_norm in query_norm):
                matched_items.append(it)
            if len(matched_items) >= 8:
                break

    memory_hits: list[Any] = []
    should_scan_file_memory = bool(include_file_memory and (include_diary_memory or active_items or matched_items))
    if should_scan_file_memory:
        memory_hits = _tracking_file_memory.search(
            user_id=user_id,
            workspace=workspace_norm,
            query=query,
            limit=12,
            include_diary=include_diary_memory,
        )
    file_items = [
        {
            "path": item.path,
            "title": item.title,
            "preview": item.preview,
            "score": float(item.score),
            "updated_at": item.updated_at,
            "canonical_id": item.canonical_id,
            "target": item.target,
            "source": item.source,
            "kind": item.kind,
            "topic_path": item.topic_path,
            "entry_kind": item.entry_kind,
        }
        for item in memory_hits[:12]
    ]
    return {
        "active_items": active_items[:12],
        "matched_items": matched_items[:8],
        "active_count": len(active_items),
        "matched_count": len(matched_items) + len(file_items),
        "matched_file_items": file_items[:8],
        "matched_file_count": len(file_items),
    }


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _fallback_intent_contract(
    *,
    query: str,
    memory_summary: str,
    tracking_snapshot: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    smalltalk = _is_smalltalk_query(query_text)
    time_sensitive = _is_time_sensitive_query(query_text)
    sports_result_intent = _is_sports_result_query(query_text)
    tracking_intent = _is_tracking_intent_query(query_text)
    matched_count = 0
    if isinstance(tracking_snapshot, dict):
        matched_count = _safe_int(tracking_snapshot.get("matched_count"), 0)

    intent_type = "chat"
    if tracking_intent:
        intent_type = "tracking"
    elif not smalltalk:
        intent_type = "retrieval"
    time_scope = "any"
    if time_sensitive:
        time_scope = "recent"
    if "today" in query_text.lower():
        time_scope = "today"
    freshness_hours = 720
    if time_scope == "today":
        freshness_hours = 24
    elif time_scope == "recent":
        freshness_hours = 72
    if sports_result_intent:
        freshness_hours = min(freshness_hours, 24)

    requires_citations = bool((not smalltalk) and (time_sensitive or sports_result_intent))
    requires_factuality = not smalltalk

    ambiguities: list[str] = []
    if len(query_text) <= 6:
        ambiguities.append("query_too_short")
    if intent_type == "retrieval" and matched_count > 0 and not time_sensitive:
        ambiguities.append("could_use_existing_tracking_only")
    if intent_type == "retrieval" and not (memory_summary or "").strip():
        ambiguities.append("limited_personal_memory_context")

    return {
        "goal": query_text[:240] or "chat",
        "intent_type": intent_type,
        "time_scope": time_scope,
        "freshness_hours": max(1, min(720, int(freshness_hours))),
        "requires_citations": requires_citations,
        "requires_factuality": requires_factuality,
        "sports_result_intent": sports_result_intent,
        "tracking_intent": tracking_intent,
        "ambiguities": ambiguities[:4],
        "confidence": 0.62 if not smalltalk else 0.8,
        "reason": reason[:180],
        "intent_source": "fallback",
    }


def _normalize_intent_contract(
    *,
    raw: dict[str, Any] | None,
    query: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    out = dict(fallback)
    if not isinstance(raw, dict):
        return out

    goal = str(raw.get("goal") or "").strip()
    if goal:
        out["goal"] = goal[:240]

    intent_type = str(raw.get("intent_type") or "").strip().lower()
    if intent_type in {"chat", "retrieval", "tracking", "analysis"}:
        out["intent_type"] = intent_type

    time_scope = str(raw.get("time_scope") or "").strip().lower()
    if time_scope in {"any", "today", "recent", "historical", "realtime"}:
        out["time_scope"] = time_scope

    freshness_hours = _safe_int(raw.get("freshness_hours"), _safe_int(out.get("freshness_hours"), 72))
    out["freshness_hours"] = max(1, min(720, freshness_hours))

    if raw.get("requires_citations") is not None:
        out["requires_citations"] = bool(raw.get("requires_citations"))
    if raw.get("requires_factuality") is not None:
        out["requires_factuality"] = bool(raw.get("requires_factuality"))

    out["sports_result_intent"] = bool(raw.get("sports_result_intent")) or _is_sports_result_query(query)
    out["tracking_intent"] = bool(raw.get("tracking_intent")) or _is_tracking_intent_query(query)

    ambiguities = raw.get("ambiguities")
    if isinstance(ambiguities, list):
        normalized_ambiguities: list[str] = []
        for row in ambiguities:
            text = str(row or "").strip()
            if not text:
                continue
            normalized_ambiguities.append(text[:120])
            if len(normalized_ambiguities) >= 4:
                break
        out["ambiguities"] = normalized_ambiguities

    confidence = _safe_float(raw.get("confidence"), _safe_float(out.get("confidence"), 0.62))
    out["confidence"] = max(0.0, min(1.0, confidence))

    reason = str(raw.get("reason") or "").strip()
    if reason:
        out["reason"] = reason[:180]
    return out


def _build_intent_contract(
    *,
    query: str,
    service: LLMService,
    provider: str,
    memory_summary: str,
    tracking_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = _fallback_intent_contract(
        query=query,
        memory_summary=memory_summary,
        tracking_snapshot=tracking_snapshot,
        reason="intent_fallback",
    )
    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "intent_planner_unavailable"
        if provider == "rule_based":
            fallback_reason = "intent_rule_based"
        elif not service.is_configured():
            fallback_reason = "intent_not_configured"
        fallback["reason"] = fallback_reason
        return fallback

    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    active_count = _safe_int(tracking.get("active_count"), 0)
    matched_count = _safe_int(tracking.get("matched_count"), 0)
    now_utc = datetime.now(timezone.utc).isoformat()

    prompt = (
        "You are Aelin Intent Lens Agent.\n"
        "Infer user intent with explicit time understanding and factuality requirements.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"goal\": string,"
        "\"intent_type\": \"chat|retrieval|tracking|analysis\","
        "\"time_scope\": \"any|today|recent|historical|realtime\","
        "\"freshness_hours\": number,"
        "\"requires_citations\": boolean,"
        "\"requires_factuality\": boolean,"
        "\"sports_result_intent\": boolean,"
        "\"tracking_intent\": boolean,"
        "\"ambiguities\": string[],"
        "\"confidence\": number,"
        "\"reason\": string"
        "}\n"
        "If user uses relative time words like today/recent/latest, convert them into explicit time_scope and freshness."
    )
    user_msg = (
        f"user_query: {query.strip()}\n"
        f"memory_summary_available: {'yes' if bool((memory_summary or '').strip()) else 'no'}\n"
        f"active_tracking_count: {active_count}\n"
        f"matched_tracking_count: {matched_count}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=320,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        normalized = _normalize_intent_contract(raw=parsed if isinstance(parsed, dict) else None, query=query, fallback=fallback)
        normalized["intent_source"] = "llm"
        if not isinstance(parsed, dict):
            normalized["reason"] = "intent_invalid_json"
            normalized["intent_source"] = "fallback"
        return normalized
    except Exception:
        fallback["reason"] = "intent_error"
        return fallback


def _plan_tool_usage(
    *,
    query: str,
    service: LLMService,
    provider: str,
    memory_summary: str,
    tracking_snapshot: dict[str, Any] | None = None,
    intent_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _fallback_plan(reason: str) -> dict[str, Any]:
        contract = intent_contract if isinstance(intent_contract, dict) else {}
        contract_intent_type = str(contract.get("intent_type") or "").strip().lower()
        contract_time_scope = str(contract.get("time_scope") or "").strip().lower()
        contract_requires_citations = bool(contract.get("requires_citations"))
        contract_sports_intent = bool(contract.get("sports_result_intent"))
        contract_tracking_intent = bool(contract.get("tracking_intent"))

        tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
        active_items = tracking.get("active_items") if isinstance(tracking.get("active_items"), list) else []
        matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []

        query_text = (query or "").strip()
        conversational = _is_smalltalk_query(query_text)
        time_sensitive = contract_time_scope in {"today", "recent", "realtime"} or _is_time_sensitive_query(query_text)
        has_memory = bool((memory_summary or "").strip())
        has_tracking_match = bool(matched_items)

        recent_tracking_match = False
        now = datetime.now(timezone.utc)
        for it in matched_items[:5]:
            updated_raw = str(it.get("updated_at") or "").strip()
            if not updated_raw:
                continue
            try:
                updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if (now - updated_at).total_seconds() <= 36 * 3600:
                recent_tracking_match = True
                break

        retrieval_like = bool(query_text) and (not conversational)
        if contract_intent_type == "chat":
            retrieval_like = False
        elif contract_intent_type in {"retrieval", "tracking", "analysis"}:
            retrieval_like = True
        sports_result_intent = bool(contract_sports_intent or _is_sports_result_query(query_text))
        need_local = retrieval_like and (has_memory or has_tracking_match or bool(active_items))
        need_web = False
        if retrieval_like:
            if time_sensitive or sports_result_intent or contract_requires_citations:
                need_web = not recent_tracking_match
            elif (not has_memory) and (not has_tracking_match):
                need_web = True

        web_seed: list[str] = []
        if need_web:
            web_seed.append(query_text)
            if sports_result_intent:
                web_seed.extend(
                    [
                        f"{query_text} \u6700\u65b0 \u6bd4\u5206",
                        f"{query_text} \u8d5b\u679c",
                        f"{query_text} box score",
                        f"{query_text} game recap",
                    ]
                )
            for it in matched_items[:2]:
                target = str(it.get("target") or it.get("query") or "").strip()[:120]
                if target:
                    web_seed.append(f"{target} latest")
        web_queries = _normalize_web_queries(query_text, web_seed, limit=_MAX_WEB_SUBAGENTS) if need_web else []
        context_boundaries = _normalize_context_boundaries(
            query_text,
            [],
            need_local_search=need_local,
            need_web_search=need_web,
            web_queries=web_queries,
        )
        need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
        need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
        web_queries = (
            _normalize_web_queries(
                query_text,
                [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"],
            )
            if need_web
            else []
        )

        trace_agent = bool((contract_tracking_intent or _is_tracking_intent_query(query_text)) and not recent_tracking_match)
        track_suggestion = None
        if trace_agent and query_text:
            track_suggestion = {
                "target": query_text[:240],
                "source": "web" if need_web else "auto",
                "reason": "fallback planner detected potential long-running tracking intent",
            }
        trace_context_boundaries = _build_trace_context_boundaries(
            query=query_text,
            raw_boundaries=[],
            need_local_search=trace_agent and need_local,
            need_web_search=trace_agent and bool(need_web or query_text),
            web_queries=web_queries,
            intent_contract=contract,
            tracking_snapshot=tracking,
        )
        reason_bits = [reason]
        if conversational:
            reason_bits.append("smalltalk")
        if time_sensitive:
            reason_bits.append("time_sensitive")
        if sports_result_intent:
            reason_bits.append("sports_result_intent")
        if recent_tracking_match:
            reason_bits.append("tracking_match_recent")
        elif has_tracking_match:
            reason_bits.append("tracking_match_stale")
        if need_local:
            reason_bits.append("local_context")
        if need_web:
            reason_bits.append("web_context")
        return {
            "need_local_search": need_local,
            "need_web_search": need_web,
            "web_queries": web_queries,
            "context_boundaries": context_boundaries,
            "trace_context_boundaries": trace_context_boundaries,
            "track_suggestion": track_suggestion,
            "route": {
                "reply_agent": True,
                "trace_agent": trace_agent,
                "allow_web_retry": bool(need_web and time_sensitive),
            },
            "reason": ";".join(reason_bits),
            "planner_source": "fallback",
        }

    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "planner_unavailable"
        if provider == "rule_based":
            fallback_reason = "planner_rule_based"
        elif not service.is_configured():
            fallback_reason = "planner_not_configured"
        return _fallback_plan(fallback_reason)

    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    active_items = tracking.get("active_items") if isinstance(tracking.get("active_items"), list) else []
    matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []

    planning_prompt = (
        "You are Aelin Main Agent planner.\n"
        "Decide dynamic dispatch by context boundaries.\n"
        "You must obey intent contract constraints from Intent Lens Agent.\n"
        "Do not rely on rigid keyword-only rules; decide from query + memory + tracking context.\n"
        "Both local and web subagents are optional.\n"
        "You may dispatch up to 5 web subagents and up to 5 local subagents in parallel.\n"
        "If existing tracking already covers the asked topic, you may skip web retrieval.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"need_local_search\": boolean,"
        "\"need_web_search\": boolean,"
        "\"web_queries\": string[],"
        "\"context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"trace_context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"reply_agent\": boolean,"
        "\"trace_agent\": boolean,"
        "\"allow_web_retry\": boolean,"
        "\"should_suggest_tracking\": boolean,"
        "\"tracking_target\": string,"
        "\"tracking_source\": \"auto|web|rss|x|douyin|xiaohongshu|weibo|bilibili|email\","
        "\"tracking_reason\": string,"
        "\"reason\": string"
        "}\n"
        "context_boundaries is the primary dispatch plan.\n"
        "reply_agent defaults to true and can be omitted unless you want it disabled."
    )
    matched_lines = [
        f"- {str(it.get('target') or '').strip()} ({str(it.get('source') or 'auto').strip()} / {str(it.get('updated_at') or '').strip()})"
        for it in matched_items[:5]
        if str(it.get("target") or "").strip()
    ]
    active_lines = [
        f"- {str(it.get('target') or '').strip()} ({str(it.get('source') or 'auto').strip()})"
        for it in active_items[:5]
        if str(it.get("target") or "").strip()
    ]
    user_msg = (
        f"user_query: {query.strip()}\n"
        + (
            f"intent_contract: {json.dumps(intent_contract, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
            if isinstance(intent_contract, dict)
            else ""
        )
        +
        f"memory_summary_available: {'yes' if bool((memory_summary or '').strip()) else 'no'}\n"
        f"active_tracking_count: {len(active_items)}\n"
        + ("matched_tracking:\n" + "\n".join(matched_lines) + "\n" if matched_lines else "matched_tracking: none\n")
        + ("recent_tracking:\n" + "\n".join(active_lines) + "\n" if active_lines else "recent_tracking: none\n")
        + "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": planning_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return _fallback_plan("planner_invalid_json")

        need_local_hint = bool(parsed.get("need_local_search"))
        need_web_hint = bool(parsed.get("need_web_search"))
        web_queries = _normalize_web_queries(query, parsed.get("web_queries"))
        context_boundaries = _normalize_context_boundaries(
            query,
            parsed.get("context_boundaries"),
            need_local_search=need_local_hint,
            need_web_search=need_web_hint,
            web_queries=web_queries,
        )
        need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
        need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
        web_queries = _normalize_web_queries(
            query,
            [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"] or web_queries,
        )
        should_track = bool(parsed.get("should_suggest_tracking"))
        track_target = str(parsed.get("tracking_target") or "").strip()[:240]
        track_source = _normalize_track_source(str(parsed.get("tracking_source") or "auto"))
        track_reason = str(parsed.get("tracking_reason") or "").strip()[:220]
        reason = str(parsed.get("reason") or "").strip()[:200] or "llm_planner"
        reply_agent = bool(parsed.get("reply_agent", True))
        trace_agent = bool(parsed.get("trace_agent"))
        allow_web_retry_raw = parsed.get("allow_web_retry")
        allow_web_retry = bool(allow_web_retry_raw) if allow_web_retry_raw is not None else need_web

        track_suggestion = None
        if should_track and track_target:
            track_suggestion = {
                "target": track_target,
                "source": track_source,
                "reason": track_reason or "Aelin 判断该主题值得持续跟踪。",
            }
            trace_agent = True

        trace_context_boundaries = _build_trace_context_boundaries(
            query=query,
            raw_boundaries=parsed.get("trace_context_boundaries"),
            need_local_search=trace_agent and need_local,
            need_web_search=trace_agent and bool(need_web or track_suggestion),
            web_queries=web_queries,
            intent_contract=intent_contract if isinstance(intent_contract, dict) else None,
            tracking_snapshot=tracking_snapshot if isinstance(tracking_snapshot, dict) else None,
        )

        if need_web and not web_queries:
            web_queries = [query.strip()[:180]] if query.strip() else []
        return {
            "need_local_search": need_local,
            "need_web_search": need_web,
            "web_queries": web_queries,
            "context_boundaries": context_boundaries,
            "trace_context_boundaries": trace_context_boundaries,
            "track_suggestion": track_suggestion,
            "route": {
                "reply_agent": reply_agent,
                "trace_agent": trace_agent,
                "allow_web_retry": allow_web_retry,
            },
            "reason": f"llm:{reason}",
            "planner_source": "llm",
        }
    except Exception:
        return _fallback_plan("planner_error")


def _critic_tool_plan(
    *,
    query: str,
    intent_contract: dict[str, Any] | None,
    tool_plan: dict[str, Any],
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    def _fallback_critic(reason: str) -> dict[str, Any]:
        contract = intent_contract if isinstance(intent_contract, dict) else {}
        requires_citations = bool(contract.get("requires_citations"))
        intent_type = str(contract.get("intent_type") or "").strip().lower()
        sports_result_intent = bool(contract.get("sports_result_intent")) or _is_sports_result_query(query)
        tracking_intent = bool(contract.get("tracking_intent")) or _is_tracking_intent_query(query)

        need_local = bool(tool_plan.get("need_local_search"))
        need_web = bool(tool_plan.get("need_web_search"))
        web_queries = _normalize_web_queries(query, tool_plan.get("web_queries"))
        boundaries = _normalize_context_boundaries(
            query,
            tool_plan.get("context_boundaries"),
            need_local_search=need_local,
            need_web_search=need_web,
            web_queries=web_queries,
        )
        has_local = any(str(it.get("kind") or "") == "local" for it in boundaries)
        has_web = any(str(it.get("kind") or "") == "web" for it in boundaries)
        route = tool_plan.get("route") if isinstance(tool_plan.get("route"), dict) else {}
        issues: list[str] = []
        patch: dict[str, Any] = {}

        retrieval_intent = intent_type in {"retrieval", "tracking", "analysis"} or (not _is_smalltalk_query(query))
        if retrieval_intent and (not has_local) and (not has_web):
            issues.append("no_retrieval_path")
            patch["need_local_search"] = True
            patch["context_boundaries"] = [{"kind": "local", "query": query.strip()[:180], "scope": "critic_local_context"}]

        if (requires_citations or sports_result_intent) and (not has_web):
            issues.append("missing_web_path_for_factual_intent")
            patch["need_web_search"] = True
            patch["web_queries"] = _normalize_web_queries(
                query,
                [
                    query.strip()[:180],
                    f"{query.strip()[:160]} 最新",
                    f"{query.strip()[:160]} 比分" if sports_result_intent else f"{query.strip()[:160]} 官方",
                ],
                limit=_MAX_WEB_SUBAGENTS,
            )
            patch_boundaries = patch.get("context_boundaries")
            if not isinstance(patch_boundaries, list):
                patch_boundaries = list(boundaries)
            patch_boundaries.extend(
                {"kind": "web", "query": q, "scope": q}
                for q in patch.get("web_queries", [])[:2]
            )
            patch["context_boundaries"] = patch_boundaries

        if tracking_intent and (not bool(route.get("trace_agent"))):
            issues.append("missing_trace_route")
            patch["route"] = {
                "reply_agent": bool(route.get("reply_agent", True)),
                "trace_agent": True,
                "allow_web_retry": bool(route.get("allow_web_retry", False) or requires_citations or sports_result_intent),
            }
            patch["trace_context_boundaries"] = _build_trace_context_boundaries(
                query=query,
                raw_boundaries=tool_plan.get("trace_context_boundaries"),
                need_local_search=has_local,
                need_web_search=bool(has_web or patch.get("need_web_search")),
                web_queries=patch.get("web_queries") if isinstance(patch.get("web_queries"), list) else web_queries,
                intent_contract=contract,
                tracking_snapshot=None,
            )

        accepted = not issues
        return {
            "accepted": accepted,
            "issues": issues,
            "patch": patch if patch else None,
            "reason": reason if accepted else f"{reason}:{','.join(issues)}",
            "critic_source": "fallback",
        }

    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "critic_unavailable"
        if provider == "rule_based":
            fallback_reason = "critic_rule_based"
        elif not service.is_configured():
            fallback_reason = "critic_not_configured"
        return _fallback_critic(fallback_reason)

    contract_payload = intent_contract if isinstance(intent_contract, dict) else {}
    prompt = (
        "You are Aelin Plan Critic Agent.\n"
        "Evaluate whether dispatch plan fully covers intent contract.\n"
        "If weak, provide a corrective patch.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"accepted\": boolean,"
        "\"issues\": string[],"
        "\"patch\": {"
        "\"need_local_search\": boolean,"
        "\"need_web_search\": boolean,"
        "\"web_queries\": string[],"
        "\"context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"trace_context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"route\": {\"reply_agent\": boolean,\"trace_agent\": boolean,\"allow_web_retry\": boolean}"
        "},"
        "\"reason\": string"
        "}\n"
        "Rules:\n"
        "- For time-sensitive factual intents, ensure evidence path exists.\n"
        "- For sports result intents, prefer web path with score/result oriented queries.\n"
        "- Keep patch minimal and deterministic."
    )
    user_msg = (
        f"user_query: {query.strip()}\n"
        f"intent_contract: {json.dumps(contract_payload, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
        f"tool_plan: {json.dumps(tool_plan, ensure_ascii=False, separators=(',', ':'))[:1800]}\n"
        "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=320,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return _fallback_critic("critic_invalid_json")
        accepted = bool(parsed.get("accepted"))
        issues_raw = parsed.get("issues")
        issues: list[str] = []
        if isinstance(issues_raw, list):
            for row in issues_raw:
                text = str(row or "").strip()
                if not text:
                    continue
                issues.append(text[:120])
                if len(issues) >= 6:
                    break
        patch_raw = parsed.get("patch")
        patch: dict[str, Any] | None = None
        if isinstance(patch_raw, dict):
            patch = {}
            if patch_raw.get("need_local_search") is not None:
                patch["need_local_search"] = bool(patch_raw.get("need_local_search"))
            if patch_raw.get("need_web_search") is not None:
                patch["need_web_search"] = bool(patch_raw.get("need_web_search"))
            if patch_raw.get("web_queries") is not None:
                patch["web_queries"] = _normalize_web_queries(query, patch_raw.get("web_queries"), limit=_MAX_WEB_SUBAGENTS)
            if isinstance(patch_raw.get("context_boundaries"), list):
                patch["context_boundaries"] = patch_raw.get("context_boundaries")
            if isinstance(patch_raw.get("trace_context_boundaries"), list):
                patch["trace_context_boundaries"] = patch_raw.get("trace_context_boundaries")
            if isinstance(patch_raw.get("route"), dict):
                route_raw = patch_raw.get("route") or {}
                patch["route"] = {
                    "reply_agent": bool(route_raw.get("reply_agent", True)),
                    "trace_agent": bool(route_raw.get("trace_agent", False)),
                    "allow_web_retry": bool(route_raw.get("allow_web_retry", False)),
                }
        reason = str(parsed.get("reason") or "").strip()[:180] or "critic_llm"
        if (not accepted) and (not patch):
            fallback = _fallback_critic(f"critic_patch_missing:{reason}")
            fallback["critic_source"] = "fallback"
            return fallback
        return {
            "accepted": accepted,
            "issues": issues,
            "patch": patch,
            "reason": reason,
            "critic_source": "llm",
        }
    except Exception:
        return _fallback_critic("critic_error")


def _apply_plan_patch(
    *,
    query: str,
    tool_plan: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    out = dict(tool_plan or {})
    need_local = bool(patch.get("need_local_search", out.get("need_local_search")))
    need_web = bool(patch.get("need_web_search", out.get("need_web_search")))
    web_queries_seed = patch.get("web_queries") if patch.get("web_queries") is not None else out.get("web_queries")
    web_queries = _normalize_web_queries(query, web_queries_seed, limit=_MAX_WEB_SUBAGENTS)
    context_seed = patch.get("context_boundaries") if isinstance(patch.get("context_boundaries"), list) else out.get("context_boundaries")
    context_boundaries = _normalize_context_boundaries(
        query,
        context_seed,
        need_local_search=need_local,
        need_web_search=need_web,
        web_queries=web_queries,
    )
    need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
    need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
    web_queries = _normalize_web_queries(
        query,
        [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"] or web_queries,
        limit=_MAX_WEB_SUBAGENTS,
    )

    base_route = out.get("route") if isinstance(out.get("route"), dict) else {}
    patch_route = patch.get("route") if isinstance(patch.get("route"), dict) else {}
    merged_route = {
        "reply_agent": bool(patch_route.get("reply_agent", base_route.get("reply_agent", True))),
        "trace_agent": bool(patch_route.get("trace_agent", base_route.get("trace_agent", False))),
        "allow_web_retry": bool(patch_route.get("allow_web_retry", base_route.get("allow_web_retry", need_web))),
    }
    trace_seed = patch.get("trace_context_boundaries") if isinstance(patch.get("trace_context_boundaries"), list) else out.get("trace_context_boundaries")
    trace_enabled = bool(merged_route.get("trace_agent")) or bool(out.get("track_suggestion"))
    trace_context_boundaries = _build_trace_context_boundaries(
        query=query,
        raw_boundaries=trace_seed,
        need_local_search=trace_enabled and need_local,
        need_web_search=trace_enabled and bool(need_web or merged_route.get("allow_web_retry")),
        web_queries=web_queries,
        intent_contract=None,
        tracking_snapshot=None,
    )

    out["need_local_search"] = need_local
    out["need_web_search"] = need_web
    out["web_queries"] = web_queries
    out["context_boundaries"] = context_boundaries
    out["trace_context_boundaries"] = trace_context_boundaries
    out["route"] = merged_route
    out["planner_source"] = str(out.get("planner_source") or "fallback") + "+critic_patch"
    out["reason"] = str(out.get("reason") or "planner") + ";critic_patch"
    return out


def _is_tracking_intent_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    signals = [
        "\u8ffd\u8e2a",
        "\u8ddf\u8e2a",
        "\u540e\u7eed",
        "\u6301\u7eed",
        "\u8ba2\u9605",
        "\u63d0\u9192",
        "\u76d1\u63a7",
        "watch",
        "follow",
        "track",
    ]
    return any(sig in text for sig in signals)


def _is_diary_only_query(query: str) -> bool:
    text = re.sub(r"\s+", " ", (query or "").strip()).lower()
    if not text:
        return False
    diary_tokens = [
        "aelinの日记",
        "日记",
        "长期追踪记忆",
        "追踪记忆",
        "file memory",
        "memory",
        "diary",
    ]
    strict_prefix = ["仅根据", "只根据", "仅基于", "只基于", "仅按", "只按", "only based on", "only use"]
    no_web_tokens = ["不要联网", "无需联网", "不联网", "不要网络搜索", "只看日记", "仅看日记", "仅用日记", "只用日记"]
    has_diary = any(token in text for token in diary_tokens)
    if has_diary and any(token in text for token in strict_prefix):
        return True
    if has_diary and any(token in text for token in no_web_tokens):
        return True
    if re.search(r"\bonly\b.*\b(diary|memory)\b", text):
        return True
    return False


def _is_sports_result_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    signals = [
        "nba",
        "wnba",
        "cba",
        "nfl",
        "nhl",
        "mlb",
        "epl",
        "\u6bd4\u8d5b",
        "\u6bd4\u5206",
        "\u8d5b\u7a0b",
        "\u8d5b\u679c",
        "\u6218\u7ee9",
        "\u6253\u4e86\u4ec0\u4e48",
        "\u8c01\u8d62\u4e86",
        "\u5bf9\u9635",
        "\u5b63\u540e\u8d5b",
        "\u5e38\u89c4\u8d5b",
        "score",
        "box score",
        "result",
        "results",
        "fixture",
        "fixtures",
        "match",
        "matches",
        "who won",
        "standings",
        "game recap",
    ]
    return any(sig in text for sig in signals)


def _is_time_sensitive_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    signals = [
        "\u4eca\u5929",
        "\u6628\u5929",
        "\u524d\u5929",
        "\u521a\u521a",
        "\u6700\u65b0",
        "\u6700\u8fd1",
        "\u8fd1\u671f",
        "\u8fd1\u51e0\u5929",
        "\u5b9e\u65f6",
        "\u5373\u65f6",
        "\u76ee\u524d",
        "\u6bd4\u5206",
        "\u6218\u7ee9",
        "\u8d5b\u679c",
        "\u65b0\u95fb",
        "\u80a1\u4ef7",
        "\u4ef7\u683c",
        "\u6c47\u7387",
        "now",
        "today",
        "yesterday",
        "latest",
        "recent",
        "recently",
        "breaking",
        "live",
        "score",
        "result",
        "results",
        "price",
        "quote",
        "this week",
        "last week",
        "past",
    ]
    if any(sig in text for sig in signals):
        return True
    if re.search(r"\b(last|past)\s+(24|48|72)\s*(h|hour|hours|d|day|days)\b", text):
        return True
    if re.search(r"\b(last|past|recent)\s+\d+\s*(day|days|week|weeks|month|months)\b", text):
        return True
    return False


def _main_agent_route(
    *,
    need_local_search: bool,
    need_web_search: bool,
    planned_track_suggestion: dict[str, str] | None,
    planned_route: dict[str, Any] | None,
) -> dict[str, Any]:
    reply_agent = True
    trace_agent = bool(planned_track_suggestion)
    allow_web_retry = bool(need_web_search)
    if isinstance(planned_route, dict):
        reply_agent = bool(planned_route.get("reply_agent", True))
        trace_agent = bool(planned_route.get("trace_agent", trace_agent))
        allow_web_retry = bool(planned_route.get("allow_web_retry", allow_web_retry))
    multi_agent = bool((reply_agent and (need_local_search or need_web_search)) or trace_agent)
    reasons: list[str] = []
    if isinstance(planned_route, dict):
        reasons.append("planner_route")
    if need_local_search:
        reasons.append("local_context")
    if need_web_search:
        reasons.append("web_facts")
    if trace_agent:
        reasons.append("trace_intent")
    if not reasons:
        reasons.append("chat_only")
    return {
        "multi_agent": multi_agent,
        "reply_agent": reply_agent,
        "trace_agent": trace_agent,
        "allow_web_retry": allow_web_retry,
        "reason": ",".join(reasons),
    }


def _answer_has_fact_signal(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return False
    if re.search(r"\d{1,4}\s*[:：-]\s*\d{1,4}", text):
        return True
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|元|美元|万|亿|分|秒|点|年|月|日)", text):
        return True
    signals = ["截至", "目前", "官方", "数据显示", "来源", "北京时间", "更新于"]
    return any(sig in text for sig in signals)


def _verify_reply_answer(
    *,
    query: str,
    answer: str,
    need_web_search: bool,
    citations: list[AelinCitation],
    diary_only_mode: bool = False,
) -> tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"
    if diary_only_mode:
        if _looks_like_link_dump_answer(text):
            return False, "diary_only_link_dump"
        return True, "diary_only_pass"
    needs_evidence = bool(need_web_search or (_is_time_sensitive_query(query) and not _is_smalltalk_query(query)))
    if needs_evidence and not citations:
        return False, "evidence_missing"
    if needs_evidence and _looks_like_link_dump_answer(text):
        return False, "link_dump_answer"
    if needs_evidence and citations and not _answer_has_fact_signal(text):
        return False, "fact_sparse"
    return True, "pass"


def _check_evidence_coverage(
    *,
    query: str,
    intent_contract: dict[str, Any] | None,
    answer: str,
    citations: list[AelinCitation],
    web_results: list[WebSearchResult],
    diary_only_mode: bool = False,
) -> tuple[bool, str]:
    if diary_only_mode:
        return True, "diary_only_mode"
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    requires_citations = bool(contract.get("requires_citations"))
    if not requires_citations:
        requires_citations = bool(_is_time_sensitive_query(query) and not _is_smalltalk_query(query))

    if requires_citations and not citations:
        return False, "missing_evidence"

    freshness_hours = max(1, min(720, _safe_int(contract.get("freshness_hours"), 72)))
    if requires_citations and freshness_hours <= 48:
        has_web = any(str(it.source or "").strip().lower() == "web" for it in citations)
        if not has_web:
            return False, "freshness_unmet_no_web"

    sports_result_intent = bool(contract.get("sports_result_intent")) or _is_sports_result_query(query)
    if sports_result_intent:
        has_score = bool(_extract_score_clues(answer))
        if not has_score:
            for row in web_results[:10]:
                blob = f"{row.title} {row.snippet} {(getattr(row, 'fetched_excerpt', '') or '')}".strip()
                if _extract_score_clues(blob):
                    has_score = True
                    break
        if not has_score:
            for cite in citations[:10]:
                if _extract_score_clues(str(cite.title or "")):
                    has_score = True
                    break
        if not has_score:
            return False, "missing_score_evidence"

    return True, "coverage_pass"


def _judge_answer_grounding(
    *,
    query: str,
    answer: str,
    citations: list[AelinCitation],
    intent_contract: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    if bool(contract.get("diary_only")):
        if _looks_like_link_dump_answer(text):
            return False, "diary_only_link_dump"
        return True, "diary_only_mode"
    requires_factuality = bool(contract.get("requires_factuality"))
    requires_citations = bool(contract.get("requires_citations"))
    if not requires_factuality:
        requires_factuality = not _is_smalltalk_query(query)
    if requires_citations and not citations:
        return False, "missing_citations"
    if not requires_factuality:
        return True, "chat_mode"

    def _heuristic_judge() -> tuple[bool, str]:
        if _looks_like_link_dump_answer(text):
            return False, "link_dump"
        if citations and _answer_has_fact_signal(text):
            return True, "heuristic_grounded"
        if citations and (not _is_time_sensitive_query(query)):
            return True, "heuristic_non_time_sensitive"
        if citations:
            return False, "fact_signal_missing"
        return False, "no_citation_grounding"

    if provider == "rule_based" or not service.is_configured():
        return _heuristic_judge()

    evidence_lines = [
        f"- [{it.source}] {it.title} ({it.received_at})"
        for it in citations[:8]
    ]
    prompt = (
        "You are Aelin Grounding Judge.\n"
        "Decide whether answer is grounded by provided evidence.\n"
        "Return strict JSON only with schema: {\"grounded\": boolean, \"reason\": string, \"risk\": \"low|medium|high\"}.\n"
        "High risk if answer makes factual claims unsupported by evidence or asks user to search manually despite evidence."
    )
    user_msg = (
        f"user_query: {query.strip()}\n"
        f"answer: {text[:1600]}\n"
        + (f"evidence:\n{chr(10).join(evidence_lines)}\n" if evidence_lines else "evidence: none\n")
        + "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=180,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return _heuristic_judge()
        grounded = bool(parsed.get("grounded"))
        reason = str(parsed.get("reason") or "").strip()[:160] or "judge_llm"
        return grounded, reason
    except Exception:
        return _heuristic_judge()


def _build_retry_web_queries(
    query: str,
    used_queries: list[str],
    *,
    intent_contract: dict[str, Any] | None = None,
    tracking_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    base = (query or "").strip()
    if not base:
        return []
    used = {q.strip().lower() for q in used_queries if q.strip()}
    query_pack = _build_web_query_pack(
        query=base,
        base_queries=[base],
        intent_contract=intent_contract if isinstance(intent_contract, dict) else None,
        tracking_snapshot=tracking_snapshot if isinstance(tracking_snapshot, dict) else None,
        limit=min(_MAX_WEB_SUBAGENTS + 2, 7),
    )
    out: list[str] = []
    for candidate in query_pack:
        text = candidate.strip()[:180]
        if not text:
            continue
        key = text.lower()
        if key in used:
            continue
        used.add(key)
        out.append(text)
        if len(out) >= 3:
            break
    return out


def _trace_agent_suggestion(
    *,
    query: str,
    planned_track_suggestion: dict[str, str] | None,
    citations: list[AelinCitation],
    need_web_search: bool,
) -> tuple[dict[str, str] | None, str]:
    if planned_track_suggestion:
        target = str(planned_track_suggestion.get("target") or "").strip()[:240]
        source = _normalize_track_source(str(planned_track_suggestion.get("source") or "auto"))
        reason = str(planned_track_suggestion.get("reason") or "").strip()[:220]
        if target:
            return (
                {
                    "target": target,
                    "source": source,
                    "reason": reason or "Trace Agent 采纳了 Reply Agent 的跟踪建议。",
                },
                "use_planned_track_suggestion",
            )

    if _is_tracking_intent_query(query):
        source = "web" if (need_web_search or any(it.source == "web" for it in citations)) else "auto"
        return (
            {
                "target": query.strip()[:240],
                "source": source,
                "reason": "Trace Agent 识别到明确的持续追踪意图。",
            },
            "tracking_intent_matched",
        )

    return None, "no_trace_action"


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.strip().lower()
        return host or "web"
    except Exception:
        return "web"


def _extract_score_clues(text: str) -> list[str]:
    src = (text or "").strip()
    if not src:
        return []
    out: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"([A-Za-z\u4e00-\u9fff·]{1,24})?\s*(\d{2,3})\s*[-:：]\s*(\d{2,3})\s*([A-Za-z\u4e00-\u9fff·]{1,24})?"
    )
    for m in pattern.finditer(src):
        a = int(m.group(2))
        b = int(m.group(3))
        if a < 50 or b < 50 or a > 200 or b > 200:
            continue
        left = (m.group(1) or "").strip()
        right = (m.group(4) or "").strip()
        clue = re.sub(r"\s+", " ", f"{left} {a}:{b} {right}".strip())
        if not clue or clue in seen:
            continue
        seen.add(clue)
        out.append(clue)
        if len(out) >= 8:
            break
    return out


def _looks_like_link_dump_answer(answer: str) -> bool:
    text = (answer or "").strip().lower()
    if not text:
        return False
    bad_signals = [
        "可以在多个网站",
        "以下是一些可供参考的网站",
        "您可以访问这些网站",
        "你可以访问这些网站",
        "网站查询到",
        "duckduckgo",
        "yahoo",
    ]
    return any(sig in text for sig in bad_signals)


def _compose_web_first_answer(query: str, results: list[WebSearchResult]) -> str:
    if not results:
        return ""
    score_clues: list[str] = []
    highlights: list[str] = []
    seen_highlights: set[str] = set()
    for row in results[:10]:
        blob = f"{row.title} {row.snippet}".strip()
        for clue in _extract_score_clues(blob):
            if clue not in score_clues:
                score_clues.append(clue)
            if len(score_clues) >= 6:
                break
        snippet = (row.snippet or "").strip()
        if snippet:
            line = f"{row.title}：{snippet}"
            if line not in seen_highlights:
                seen_highlights.add(line)
                highlights.append(line)
        if len(highlights) >= 4 and len(score_clues) >= 6:
            break

    if score_clues:
        return (
            f"我先联网检索了“{query.strip()}”，当前抓到的比分线索如下：\n"
            + "\n".join(f"- {item}" for item in score_clues[:6])
            + "\n\n这些来自公开网页抓取，若你愿意我可以继续自动跟踪并持续更新。"
        )
    if highlights:
        return (
            f"我已经先联网检索了“{query.strip()}”。目前可确认的信息：\n"
            + "\n".join(f"- {item}" for item in highlights[:4])
            + "\n\n如果你希望，我可以继续自动跟踪这个主题。"
        )
    first = results[0]
    return (
        f"我已经先联网检索了“{query.strip()}”，但当前抓到的结果细节不足以直接下结论。"
        f"\n\n目前最相关线索：{first.title}（{_domain_from_url(first.url)}）"
        "\n\n我可以继续补抓更高质量的结果后再给你更具体的答案。"
    )


def _persist_web_search_results(
    db: Session,
    user_id: int,
    *,
    query: str,
    results: list[WebSearchResult],
) -> list[AelinCitation]:
    if not results:
        return []
    contact = crud.upsert_contact(db, user_id=user_id, handle="web:search", display_name="Web Search")
    now = datetime.now(timezone.utc)
    citations: list[AelinCitation] = []
    for idx, item in enumerate(results[:_WEB_SEARCH_MAX_RESULTS]):
        title = (item.title or "").strip()[:220]
        url = (item.url or "").strip()
        snippet = (item.snippet or "").strip()
        fetched = (getattr(item, "fetched_excerpt", "") or "").strip()
        if fetched and len(snippet) < 120:
            snippet = fetched
        snippet = snippet[:2200]
        if not title or not url:
            continue
        external_id = f"web:{hashlib.sha1(url.encode('utf-8')).hexdigest()}"
        body = f"{snippet}\n\nURL: {url}\n查询: {query.strip()[:180]}"
        msg = crud.create_message(
            db,
            user_id=user_id,
            contact_id=contact.id,
            source="web",
            external_id=external_id,
            sender=_domain_from_url(url),
            subject=title,
            body=body,
            received_at=now,
            summary=snippet or title,
        )
        if msg is not None and getattr(msg, "id", None) is None:
            db.flush()
        if msg is None:
            msg = db.scalar(
                select(Message).where(
                    Message.user_id == user_id,
                    Message.source == "web",
                    Message.external_id == external_id,
                )
            )
        if msg is None:
            continue
        crud.touch_contact_last_message(db, contact=contact, received_at=now)
        citations.append(
            AelinCitation(
                message_id=int(msg.id),
                source="web",
                source_label="Web",
                sender=_domain_from_url(url),
                sender_avatar_url=None,
                title=title,
                received_at=now.strftime("%Y-%m-%d %H:%M"),
                score=max(0.2, 6.0 - float(idx)),
            )
        )
    if citations:
        db.flush()
        content_tagging.enqueue_tagging_job(
            user_id=user_id,
            message_ids=[int(item.message_id) for item in citations],
            allow_llm=True,
        )
    return citations


def _rule_based_chat_answer(query: str, *, memory_summary: str = "", brief_summary: str = "") -> str:
    q = (query or "").strip()
    if not q:
        return "我在。你可以直接告诉我想聊什么，或让我帮你跟进某个来源的更新。"
    if any(token in q.lower() for token in ["你好", "hi", "hello"]):
        return "你好，我在这。你可以把我当作长期记忆型助手，聊想法或让我去跟进你的信息源都可以。"
    if re.search(r"[?？吗么嘛]$", q) or "是不是" in q or "有没有" in q:
        base = f"先给你直接结论：围绕“{q[:36]}”，我建议先以当前上下文做判断，再按需补证据。"
    elif any(token in q for token in ["怎么看", "看法", "觉得", "为什么", "如何", "怎么"]):
        base = f"我的直接看法是：关于“{q[:36]}”，要先抓住最近变化，再结合你长期关注点来判断。"
    else:
        base = f"直接回答：你提到的“{q[:36]}”可以先按当前已知信息处理。"
    if memory_summary:
        base += "\n\n我也会参考你已有的长期记忆来保持上下文连续。"
    if brief_summary:
        base += f"\n\n如果你需要，我也可以基于今日简报继续展开：{brief_summary}"
    base += "\n\n如果问题涉及外部事实，我会先自动检索，再直接给你结论。"
    return base


def _looks_like_non_answer(answer: str) -> bool:
    text = re.sub(r"\s+", " ", (answer or "").strip().lower())
    if not text:
        return True
    bad_starts = (
        "这是个好问题",
        "我也会参考你已有的长期记忆",
        "如果你需要",
        "可以直接说",
        "帮我检索相关更新",
    )
    if any(text.startswith(s) for s in bad_starts):
        return True
    if "帮你检索" in text and ("结论" not in text and "回答" not in text):
        return True
    if "你可以手动" in text:
        return True
    if len(text) < 24:
        return True
    return False


def _enforce_answer_first(
    *,
    query: str,
    answer: str,
    citations: list[AelinCitation],
    web_results: list[WebSearchResult],
    memory_summary: str,
    brief_summary: str,
    todo_titles: list[str] | None = None,
    image_count: int = 0,
    allow_web_fallback: bool = True,
) -> str:
    text = (answer or "").strip()
    if text and not _looks_like_non_answer(text):
        return text
    if citations:
        return _rule_based_answer(
            query,
            memory_summary,
            citations,
            brief_summary=brief_summary,
            todo_titles=todo_titles or [],
            image_count=image_count,
        )
    if allow_web_fallback and web_results:
        guarded = _compose_web_first_answer(query, web_results)
        if guarded:
            return guarded
    return _rule_based_chat_answer(query, memory_summary=memory_summary, brief_summary=brief_summary)

def _save_chat_diary_entry(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    citations: list[AelinCitation],
) -> dict[str, Any]:
    if not query.strip() or not answer.strip():
        return {"written": False, "reason": "empty_turn", "path": ""}
    now = datetime.now(timezone.utc)
    topic_path = ["与主人的聊天日记", now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")]
    title, markdown = _build_chat_diary_entry(query, answer, citations)
    target = SimpleNamespace(
        user_id=user_id,
        workspace=workspace,
        source_type="chat",
        track_type="conversation",
        source_key=f"chat:{now.strftime('%Y-%m-%d')}",
        display_name="与主人的聊天日记",
    )
    source_indices = _build_source_indices_from_citations(citations)
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=title,
        markdown=markdown,
        reason="chat_diary",
        confidence=0.82,
        source_query=query,
        topic_path=topic_path,
        source_indices=source_indices,
        entry_kind="chat_diary",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed", "path": ""}
    try:
        _memory.add_note(
            db,
            user_id,
            f"[chat-diary] {title}\npath: {str(out_path)}",
            kind="tracking_insight",
            source="chat:diary",
        )
    except Exception:
        pass
    return {"written": True, "reason": "", "path": str(out_path)}


def _save_parallel_draft_entry(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    draft_result: ParallelMemoryDraftResult | None,
    quality_passed: bool,
) -> dict[str, Any]:
    if draft_result is None:
        return {"written": False, "reason": "draft_missing", "path": ""}
    if not quality_passed:
        return {"written": False, "reason": "verifier_not_passed", "path": ""}
    min_conf = max(0.0, min(1.0, float(getattr(settings, "aelin_parallel_memory_draft_min_confidence", 0.58) or 0.58)))
    if float(draft_result.confidence or 0.0) < min_conf:
        return {"written": False, "reason": "draft_low_confidence", "path": ""}
    if int(draft_result.evidence_count or 0) <= 0:
        return {"written": False, "reason": "draft_no_evidence", "path": ""}

    now = datetime.now(timezone.utc)
    query_text = re.sub(r"\s+", " ", str(query or "").strip())[:320]
    topic_path = [
        *(draft_result.topic_path[:4] if isinstance(draft_result.topic_path, list) and draft_result.topic_path else ["并行记忆"]),
        now.strftime("%Y"),
        now.strftime("%m"),
        now.strftime("%d"),
    ]
    source_key = f"parallel:{now.strftime('%Y-%m-%d')}:{hashlib.sha1(query_text.encode('utf-8')).hexdigest()[:16]}"
    target = SimpleNamespace(
        user_id=user_id,
        workspace=workspace,
        source_type="chat",
        track_type="conversation",
        source_key=source_key,
        display_name="并行记忆草稿",
    )
    source_indices = []
    seen_refs: set[str] = set()
    for row in (draft_result.source_indices or [])[:24]:
        if not isinstance(row, dict):
            continue
        source_type = str(row.get("type") or "unknown").strip()[:32]
        label = str(row.get("label") or "").strip()[:220]
        message_id = int(row.get("message_id") or 0)
        path = str(row.get("path") or "").strip()[:500]
        url = str(row.get("url") or "").strip()[:500]
        dedupe_key = f"{source_type}:{message_id}:{path}:{url}:{label}".lower()
        if dedupe_key in seen_refs:
            continue
        seen_refs.add(dedupe_key)
        source_indices.append(
            {
                "type": source_type,
                "label": label,
                "message_id": message_id,
                "path": path,
                "url": url,
            }
        )
    source_indices.insert(
        0,
        {
            "type": "query",
            "label": query_text[:220],
            "message_id": 0,
            "path": "",
            "url": "",
        },
    )
    merged_markdown = "\n".join(
        [
            draft_result.markdown.strip(),
            "",
            "## 最终回答归档",
            "",
            _sanitize_diary_answer(answer),
        ]
    ).strip()
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=str(draft_result.title or "并行记忆草稿")[:120],
        markdown=merged_markdown,
        reason="parallel_draft_commit",
        confidence=float(draft_result.confidence or 0.0),
        source_query=query_text,
        topic_path=topic_path,
        source_indices=source_indices[:28],
        entry_kind="chat_parallel_draft",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed", "path": ""}
    try:
        _memory.add_note(
            db,
            user_id,
            f"[parallel-draft] {draft_result.title}\npath: {str(out_path)}",
            kind="tracking_insight",
            source="chat:parallel-draft",
        )
    except Exception:
        pass
    return {"written": True, "reason": "", "path": str(out_path)}


def _pick_tracking_target_for_insight(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    tracking_snapshot: dict[str, Any] | None,
) -> TrackingTarget | None:
    workspace_norm = _normalize_workspace(workspace)
    try:
        rows = _tracking.list_targets(
            db,
            user_id=user_id,
            workspace=workspace_norm,
            limit=180,
            include_deleted=False,
        )
    except Exception:
        rows = []
    if not rows:
        return None

    candidates: list[tuple[str, str, str]] = []
    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    for key in ("matched_items", "active_items"):
        items = tracking.get(key)
        if not isinstance(items, list):
            continue
        for item in items[:16]:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target") or "").strip()
            if not target:
                continue
            source = _normalize_track_source(str(item.get("source") or "auto"))
            candidate_query = str(item.get("query") or "").strip()
            candidates.append((source, target, candidate_query))

    q_norm = _normalize_match_text(query)
    best: TrackingTarget | None = None
    best_score = -1.0
    for row in rows:
        if row is None:
            continue
        if str(getattr(row, "status", "") or "").strip().lower() == "deleted":
            continue
        if getattr(row, "deleted_at", None) is not None:
            continue
        row_source = str(getattr(row, "source_type", "web") or "web").strip().lower() or "web"
        row_target = (str(getattr(row, "display_name", "") or "") or str(getattr(row, "source_key", "") or "")).strip()
        row_cfg = _json_from_text(getattr(row, "config_json", "") or "{}")
        row_query = str(row_cfg.get("query") or "").strip()
        row_target_norm = _normalize_match_text(row_target)
        row_query_norm = _normalize_match_text(row_query)

        score = 0.0
        if str(getattr(row, "status", "") or "").strip().lower() == "active":
            score += 1.2

        for source, target, cand_query in candidates:
            target_norm = _normalize_match_text(target)
            cand_query_norm = _normalize_match_text(cand_query)
            if source and source == row_source:
                score += 0.7
            if target_norm and row_target_norm and (target_norm in row_target_norm or row_target_norm in target_norm):
                score += 3.2
            if cand_query_norm and row_query_norm and (cand_query_norm in row_query_norm or row_query_norm in cand_query_norm):
                score += 1.8

        if q_norm:
            if row_target_norm and (q_norm in row_target_norm or row_target_norm in q_norm):
                score += 2.0
            if row_query_norm and (q_norm in row_query_norm or row_query_norm in q_norm):
                score += 1.4

        if score > best_score:
            best_score = score
            best = row

    if best is not None and best_score > 0:
        return best
    return rows[0] if rows else None


def _decide_tracking_insight_write(
    *,
    service: LLMService,
    provider: str,
    query: str,
    answer: str,
    tracking_snapshot: dict[str, Any] | None,
    file_memory_lines: list[str],
) -> dict[str, Any]:
    if provider == "rule_based" or not service.is_configured():
        return {"should_write": False, "reason": "llm_not_configured", "confidence": 0.0}
    question = (query or "").strip()
    reply = (answer or "").strip()
    if not question or not reply:
        return {"should_write": False, "reason": "empty_turn", "confidence": 0.0}

    tracking = tracking_snapshot if isinstance(tracking_snapshot, dict) else {}
    active_items = tracking.get("active_items") if isinstance(tracking.get("active_items"), list) else []
    matched_items = tracking.get("matched_items") if isinstance(tracking.get("matched_items"), list) else []
    active_hint = "; ".join(str(it.get("target") or "").strip() for it in active_items[:8] if isinstance(it, dict) and str(it.get("target") or "").strip())
    matched_hint = "; ".join(str(it.get("target") or "").strip() for it in matched_items[:6] if isinstance(it, dict) and str(it.get("target") or "").strip())
    file_hint = "\n".join(file_memory_lines[:6]) if file_memory_lines else ""

    system_prompt = (
        "You are Aelin planner for long-term tracking memory write.\\n"
        "Decide autonomously whether this finished answer should be persisted as a tracking insight.\\n"
        "Return strict JSON only with keys: should_write, confidence, title, markdown, reason.\\n"
        "Rules: should_write=true only when output adds stable insight helpful for future discussion; markdown should be concise, structured, and factual.\\n"
        "confidence in [0,1]."
    )
    user_prompt = (
        f"question: {question[:500]}\\n\\n"
        + f"answer: {reply[:1800]}\\n\\n"
        + f"matched_tracking: {matched_hint or 'none'}\\n"
        + f"active_tracking: {active_hint or 'none'}\\n"
        + (f"file_memory_hits:\\n{file_hint}\\n" if file_hint else "")
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=320,
            stream=False,
        )
    except Exception as exc:
        return {"should_write": False, "reason": f"planner_error:{str(exc)[:80]}", "confidence": 0.0}

    parsed = _extract_first_json_object(str(raw or ""))
    should_write = bool(parsed.get("should_write"))
    title = str(parsed.get("title") or "").strip()[:120]
    markdown = str(parsed.get("markdown") or "").strip()[:3200]
    reason = str(parsed.get("reason") or "").strip()[:200]
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    except Exception:
        confidence = 0.0

    if should_write and not markdown:
        base_title = title or "追踪洞察"
        markdown = f"### {base_title}\\n\\n{reply[:1200]}"

    if should_write and not title:
        title = "追踪洞察"

    if (not should_write) and confidence >= 0.85 and markdown:
        # High-confidence insights are kept even if model forgot the boolean flag.
        should_write = True

    return {
        "should_write": should_write,
        "confidence": confidence,
        "title": title,
        "markdown": markdown,
        "reason": reason or ("planner_declined" if not should_write else ""),
    }


def _maybe_write_tracking_insight(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    answer: str,
    service: LLMService,
    provider: str,
    tracking_snapshot: dict[str, Any] | None,
    file_memory_lines: list[str],
    citations: list[AelinCitation],
) -> dict[str, Any]:
    decision = _decide_tracking_insight_write(
        service=service,
        provider=provider,
        query=query,
        answer=answer,
        tracking_snapshot=tracking_snapshot,
        file_memory_lines=file_memory_lines,
    )
    if not bool(decision.get("should_write")):
        return {"written": False, "reason": str(decision.get("reason") or "planner_skip")}

    target = _pick_tracking_target_for_insight(
        db,
        user_id=user_id,
        workspace=workspace,
        query=query,
        tracking_snapshot=tracking_snapshot,
    )
    if target is None:
        return {"written": False, "reason": "no_tracking_target"}

    topic_path = _infer_diary_topic_path(
        query,
        answer,
        str(getattr(target, "display_name", "") or ""),
        fallback_source=str(getattr(target, "source_type", "") or "综合"),
    )
    source_indices = _build_source_indices_from_citations(citations)
    out_path = _tracking_file_memory.append_insight(
        target=target,
        title=str(decision.get("title") or "追踪洞察"),
        markdown=str(decision.get("markdown") or "").strip(),
        reason=str(decision.get("reason") or ""),
        confidence=float(decision.get("confidence") or 0.0),
        source_query=query,
        topic_path=topic_path,
        source_indices=source_indices,
        entry_kind="tracking_insight",
    )
    if out_path is None:
        return {"written": False, "reason": "file_write_failed"}

    try:
        _memory.add_note(
            db,
            user_id,
            f"[tracking-insight] {str(decision.get('title') or '追踪洞察')}\\npath: {str(out_path)}",
            kind="tracking_insight",
            source=f"tracking:insight:{int(getattr(target, 'id', 0) or 0)}",
        )
    except Exception:
        pass

    return {
        "written": True,
        "target_id": int(getattr(target, "id", 0) or 0),
        "target": str(getattr(target, "display_name", "") or ""),
        "path": str(out_path),
        "confidence": float(decision.get("confidence") or 0.0),
        "reason": str(decision.get("reason") or ""),
    }


def _aelin_chat_impl(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
) -> AelinChatResponse:
    tool_trace: list[AelinToolStep] = []
    trace_index: dict[str, int] = {}

    def emit(event: str, data: dict[str, Any]) -> None:
        if event_cb is None:
            return
        try:
            event_cb(event, data)
        except Exception:
            pass

    def add_trace(stage: str, *, status: str = "completed", detail: str = "", count: int = 0) -> None:
        safe_stage = str(stage or "stage").strip().lower()[:80] or "stage"
        safe_status = str(status or "completed").strip().lower()[:24] or "completed"
        safe_detail = str(detail or "").strip()[:240]
        safe_count = max(0, int(count or 0))
        ts = _now_ms()
        step = AelinToolStep(
            stage=safe_stage,
            status=safe_status,
            detail=safe_detail,
            count=safe_count,
            ts=ts,
        )
        idx = trace_index.get(safe_stage)
        if idx is None:
            trace_index[safe_stage] = len(tool_trace)
            tool_trace.append(step)
        else:
            prev = tool_trace[idx]
            step = step.model_copy(update={"ts": int(prev.ts or 0) if int(prev.ts or 0) > 0 else ts})
            tool_trace[idx] = step
        emit("trace", {"step": step.model_dump()})

    service, provider = _resolve_llm_service(db, current_user)
    search_mode = _normalize_search_mode(getattr(payload, "search_mode", "auto"))
    llm_generation_failed = False
    media_result: MediaIngestOutput | None = None
    media_save_state: dict[str, Any] = {"written": False, "diary_path": "", "note_added": False}
    media_summary_intent = False
    parallel_draft_future: Any | None = None
    parallel_draft_result: ParallelMemoryDraftResult | None = None
    parallel_draft_commit: dict[str, Any] = {"written": False, "reason": "not_evaluated", "path": ""}

    media_hit = _extract_first_supported_media_url(payload.query)
    if media_hit is not None:
        media_url, media_platform = media_hit
        media_summary_intent = _is_media_summary_intent(payload.query, media_url)
        add_trace("media_ingest", status="running", detail=f"{media_platform}:{media_url[:90]}")
        try:
            media_result = _media_ingest.ingest(
                user_id=current_user.id,
                workspace=payload.workspace,
                url=media_url,
                service=service,
                provider=provider,
                languages=None,
            )
            media_save_state = _save_media_ingest_diary(
                db,
                user_id=current_user.id,
                workspace=_normalize_workspace(payload.workspace),
                result=media_result,
            )
            add_trace(
                "media_ingest",
                status="completed",
                detail=(
                    f"{media_result.platform}; source={media_result.source_type}; "
                    f"written={1 if media_save_state.get('written') else 0}; conf={media_result.confidence:.2f}"
                ),
                count=1,
            )
        except MediaIngestError as exc:
            add_trace("media_ingest", status="failed", detail=f"{exc.code}:{exc.message[:140]}", count=0)
        except Exception as exc:
            add_trace("media_ingest", status="failed", detail=str(exc)[:160], count=0)

    if media_result is not None and media_summary_intent:
        answer = _build_media_ingest_answer(
            media_result,
            written=bool(media_save_state.get("written")),
        )
        expression = _pick_expression(payload.query, answer)
        actions: list[AelinAction] = []
        if media_save_state.get("written"):
            actions.append(
                AelinAction(
                    kind="open_tracking",
                    title="打开 Aelinの日记",
                    detail=str(media_save_state.get("diary_path") or "")[:220],
                    payload={"workspace": _normalize_workspace(payload.workspace)},
                )
            )
        actions.append(
            AelinAction(
                kind="open_desk",
                title="在 Desk 查看日记上下文",
                detail="打开 /desk 检索刚刚沉淀的摘要",
                payload={"path": "/desk", "query": media_result.title[:120]},
            )
        )
        chat_diary_media = _save_chat_diary_entry(
            db,
            user_id=current_user.id,
            workspace=_normalize_workspace(payload.workspace),
            query=payload.query,
            answer=answer,
            citations=[],
        )
        if bool(chat_diary_media.get("written")):
            actions.append(
                AelinAction(
                    kind="open_tracking",
                    title="打开聊天日记",
                    detail=str(chat_diary_media.get("path") or "")[:220],
                    payload={"workspace": _normalize_workspace(payload.workspace)},
                )
            )
        try:
            _memory.update_after_turn(
                db,
                current_user.id,
                [{"role": "user", "content": payload.query}],
                answer,
            )
            db.commit()
        except Exception:
            db.rollback()
        return AelinChatResponse(
            answer=answer,
            expression=expression,
            citations=[],
            actions=actions[:4],
            tool_trace=tool_trace[:64],
            memory_summary="已更新 Aelinの日记",
            generated_at=datetime.now(timezone.utc),
        )

    base_bundle = _build_cached_base_context_bundle(
        db,
        current_user.id,
        workspace=payload.workspace,
    )
    active_bundle = base_bundle
    memory_summary = str(base_bundle.get("summary") or "")
    brief_summary = base_bundle["daily_brief"].summary if base_bundle.get("daily_brief") else ""
    todo_titles = [item.title for item in base_bundle.get("todos", [])]
    profile_injection_lines = _build_fixed_profile_injection(base_bundle, max_items=12)
    images = _normalize_images(payload.images)
    history_turns = _normalize_history(payload.history)
    diary_only_mode = _is_diary_only_query(payload.query)
    include_file_memory_for_plan = bool((not _is_smalltalk_query(payload.query)) or diary_only_mode)
    tracking_snapshot = _build_cached_tracking_snapshot(
        db,
        user_id=current_user.id,
        workspace=payload.workspace,
        query=payload.query,
        include_file_memory=include_file_memory_for_plan,
        include_diary_memory=diary_only_mode,
    )
    intent_contract = _build_intent_contract(
        query=payload.query,
        service=service,
        provider=provider,
        memory_summary=memory_summary,
        tracking_snapshot=tracking_snapshot,
    )
    if diary_only_mode:
        intent_contract = dict(intent_contract)
        intent_contract["diary_only"] = True
        intent_contract["requires_citations"] = False
        intent_contract["requires_factuality"] = False
    intent_source = str(intent_contract.get("intent_source") or "fallback")
    intent_type = str(intent_contract.get("intent_type") or "retrieval")
    time_scope = str(intent_contract.get("time_scope") or "any")
    freshness_hours = max(1, min(720, _safe_int(intent_contract.get("freshness_hours"), 72)))
    intent_conf = max(0.0, min(1.0, _safe_float(intent_contract.get("confidence"), 0.62)))
    add_trace(
        "intent_lens",
        status="completed",
        detail=(
            f"type={intent_type}; scope={time_scope}; freshness_h={freshness_hours}; conf={intent_conf:.2f}; "
            f"src={intent_source}; diary_only={1 if diary_only_mode else 0}"
        ),
    )

    tool_plan = _plan_tool_usage(
        query=payload.query,
        service=service,
        provider=provider,
        memory_summary=memory_summary,
        tracking_snapshot=tracking_snapshot,
        intent_contract=intent_contract,
    )
    critic = _critic_tool_plan(
        query=payload.query,
        intent_contract=intent_contract,
        tool_plan=tool_plan,
        service=service,
        provider=provider,
    )
    critic_source = str(critic.get("critic_source") or "fallback")
    critic_reason = str(critic.get("reason") or "").strip()[:180]
    if bool(critic.get("accepted", True)):
        add_trace("plan_critic", status="completed", detail=f"{critic_source}:{critic_reason or 'accepted'}")
    else:
        add_trace("plan_critic", status="failed", detail=f"{critic_source}:{critic_reason or 'rejected'}")
        patch = critic.get("patch") if isinstance(critic.get("patch"), dict) else None
        if isinstance(patch, dict):
            tool_plan = _apply_plan_patch(
                query=payload.query,
                tool_plan=tool_plan,
                patch=patch,
            )
            add_trace("plan_critic", status="completed", detail=f"{critic_source}:patched")
    if diary_only_mode:
        tool_plan = dict(tool_plan)
        tool_plan["need_local_search"] = False
        tool_plan["need_web_search"] = False
        tool_plan["web_queries"] = []
        tool_plan["context_boundaries"] = []
        tool_plan["trace_context_boundaries"] = []
        tool_plan["track_suggestion"] = None
        route_patch = dict(tool_plan.get("route") or {})
        route_patch.update({"reply_agent": True, "trace_agent": False, "allow_web_retry": False})
        tool_plan["route"] = route_patch
        tool_plan["reason"] = f"{str(tool_plan.get('reason') or 'planner')};diary_only_enforced"
        add_trace("plan_critic", status="completed", detail="system:diary_only_enforced")

    planner_source = str(tool_plan.get("planner_source") or "fallback").strip().lower()
    planning_reason = str(tool_plan.get("reason") or "planner:none")
    if planner_source:
        planning_reason = f"{planning_reason}; planner={planner_source}"
    if critic_reason:
        planning_reason = f"{planning_reason}; critic={critic_reason}"
    need_local_search = bool(tool_plan.get("need_local_search"))
    need_web_search = bool(tool_plan.get("need_web_search"))
    web_queries = _normalize_web_queries(payload.query, tool_plan.get("web_queries"))
    context_boundaries = _normalize_context_boundaries(
        payload.query,
        tool_plan.get("context_boundaries"),
        need_local_search=need_local_search,
        need_web_search=need_web_search,
        web_queries=web_queries,
    )

    local_boundaries = [it for it in context_boundaries if str(it.get("kind") or "") == "local"][:_MAX_LOCAL_SUBAGENTS]
    web_boundaries = [it for it in context_boundaries if str(it.get("kind") or "") == "web"][:_MAX_WEB_SUBAGENTS]
    if web_boundaries:
        decomposed = _decompose_web_context_boundaries(
            query=payload.query,
            web_boundaries=web_boundaries,
            intent_contract=intent_contract,
            tracking_snapshot=tracking_snapshot,
            service=service,
            provider=provider,
        )
        decompose_source = str(decomposed.get("source") or "fallback")
        decompose_reason = str(decomposed.get("reason") or "").strip()[:180]
        decomposed_boundaries = (
            decomposed.get("boundaries")
            if isinstance(decomposed.get("boundaries"), list)
            else []
        )
        normalized_decomposed = _normalize_context_boundaries(
            payload.query,
            decomposed_boundaries,
            need_local_search=False,
            need_web_search=True,
            web_queries=[str(it.get("query") or "") for it in decomposed_boundaries if isinstance(it, dict)],
        )
        web_boundaries = [
            it
            for it in normalized_decomposed
            if str(it.get("kind") or "") == "web"
        ][:_MAX_WEB_SUBAGENTS] or web_boundaries
        planning_reason = f"{planning_reason};web_decomposer={decompose_source}:{len(web_boundaries)}"
        add_trace(
            "query_decomposer",
            status="completed" if decompose_source == "llm" else "completed",
            detail=f"{decompose_source}:{decompose_reason or 'ok'}; web={len(web_boundaries)}",
            count=len(web_boundaries),
        )
    else:
        add_trace("query_decomposer", status="skipped", detail="no web boundary")
    context_boundaries = [*local_boundaries, *web_boundaries]
    need_local_search = bool(local_boundaries)
    need_web_search = bool(web_boundaries)
    web_queries = [str(it.get("query") or "") for it in web_boundaries if str(it.get("query") or "").strip()]
    planned_track_suggestion = tool_plan.get("track_suggestion") if isinstance(tool_plan.get("track_suggestion"), dict) else None
    route = _main_agent_route(
        need_local_search=need_local_search,
        need_web_search=need_web_search,
        planned_track_suggestion=planned_track_suggestion if isinstance(planned_track_suggestion, dict) else None,
        planned_route=tool_plan.get("route") if isinstance(tool_plan.get("route"), dict) else None,
    )
    trace_route_enabled = bool(route.get("trace_agent")) or bool(planned_track_suggestion)
    trace_context_boundaries = _build_trace_context_boundaries(
        query=payload.query,
        raw_boundaries=tool_plan.get("trace_context_boundaries"),
        need_local_search=trace_route_enabled and need_local_search,
        need_web_search=trace_route_enabled and bool(need_web_search or route.get("allow_web_retry")),
        web_queries=web_queries,
        intent_contract=intent_contract,
        tracking_snapshot=tracking_snapshot,
    )
    trace_local_boundaries = [
        it for it in trace_context_boundaries if str(it.get("kind") or "") == "local"
    ][:2]
    trace_web_boundaries = [
        it for it in trace_context_boundaries if str(it.get("kind") or "") == "web"
    ][:3]

    add_trace(
        "main_agent",
        status="completed",
        detail=(
            f"{planning_reason}; mode={search_mode}; local={len(local_boundaries)}; web={len(web_boundaries)}; "
            f"trace_local={len(trace_local_boundaries)}; trace_web={len(trace_web_boundaries)}; "
            f"matched_tracking={int(tracking_snapshot.get('matched_count') or 0)}"
        ),
    )
    add_trace(
        "reply_agent",
        status="completed",
        detail=(
            f"route reply={1 if route.get('reply_agent') else 0}, "
            f"trace={1 if route.get('trace_agent') else 0}, "
            f"retry={1 if route.get('allow_web_retry') else 0}"
        ),
    )
    add_trace(
        "reply_dispatch",
        status="completed",
        detail=f"context_boundaries={len(context_boundaries)}; trace_boundaries={len(trace_context_boundaries)}",
    )

    local_citations: list[AelinCitation] = []
    web_citations: list[AelinCitation] = []
    web_results_for_answer: list[WebSearchResult] = []
    web_evidence_lines: list[str] = []
    used_web_queries: list[str] = []
    web_provider_totals: Counter[str] = Counter()
    web_fetch_mode_totals: Counter[str] = Counter()

    local_enabled = bool(need_local_search and route.get("reply_agent", True))
    web_enabled = bool(need_web_search and route.get("reply_agent", True))

    local_jobs: list[tuple[int, dict[str, str], str, str]] = []
    if local_enabled:
        add_trace(
            "local_search",
            status="running",
            detail=f"dispatching {len(local_boundaries)} local subagents",
        )
        for idx, boundary in enumerate(local_boundaries, start=1):
            sub_query = str(boundary.get("query") or payload.query).strip()[:180]
            sub_scope = str(boundary.get("scope") or sub_query).strip()[:120]
            add_trace(f"local_search_subagent_{idx}", status="running", detail=sub_scope or sub_query)
            local_jobs.append((idx, boundary, sub_query, sub_scope))
    else:
        add_trace("local_search", status="skipped", detail="local search skipped by route")

    web_jobs: list[tuple[int, dict[str, str], str]] = []
    if web_enabled:
        add_trace(
            "web_search",
            status="running",
            detail=f"dispatching {len(web_boundaries)} web subagents",
        )
        for idx, boundary in enumerate(web_boundaries, start=1):
            q = str(boundary.get("query") or payload.query).strip()[:180]
            used_web_queries.append(q)
            add_trace(f"web_search_subagent_{idx}", status="running", detail=str(boundary.get("scope") or boundary.get("query") or ""))
            web_jobs.append((idx, boundary, q))
    else:
        add_trace("web_search", status="skipped", detail="web search skipped by route")

    def _run_local_worker(jobs: list[tuple[int, dict[str, str], str, str]]) -> dict[str, Any]:
        if not jobs:
            return {"sub_results": [], "citations": []}

        merged_citations: list[AelinCitation] = []
        sub_results: list[dict[str, Any]] = []

        def _fetch_local_bundle(raw_query: str) -> tuple[list[AelinCitation], str]:
            return _fetch_local_focus_citations(
                user_id=current_user.id,
                query=raw_query,
                max_citations=payload.max_citations,
            )

        futures: dict[Any, tuple[int, dict[str, str], str, str]] = {}
        max_workers = max(1, min(len(jobs), _MAX_LOCAL_SUBAGENTS))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, boundary, sub_query, sub_scope in jobs:
                futures[pool.submit(_fetch_local_bundle, sub_query)] = (idx, boundary, sub_query, sub_scope)

            for fut in as_completed(futures):
                idx, _, sub_query, sub_scope = futures[fut]
                scope_text = sub_scope or sub_query
                try:
                    cites, local_error = fut.result()
                except Exception as exc:
                    sub_results.append(
                        {"idx": idx, "status": "failed", "detail": f"{scope_text}: {str(exc)[:140]}", "count": 0}
                    )
                    continue
                if local_error:
                    sub_results.append(
                        {"idx": idx, "status": "failed", "detail": f"{scope_text}: {local_error or 'local error'}", "count": 0}
                    )
                    continue
                merged_citations.extend(cites)
                sub_results.append({"idx": idx, "status": "completed", "detail": scope_text, "count": len(cites)})

        sub_results.sort(key=lambda item: int(item.get("idx") or 0))
        return {
            "sub_results": sub_results,
            "citations": merged_citations,
        }

    def _run_web_worker(jobs: list[tuple[int, dict[str, str], str]]) -> dict[str, Any]:
        if not jobs:
            return {"sub_results": []}

        def _fetch_web_rows(raw_query: str) -> list[WebSearchResult]:
            return _web_search.search_and_fetch(
                raw_query,
                max_results=_WEB_SEARCH_MAX_RESULTS,
                fetch_top_k=_WEB_SEARCH_FETCH_TOP_K,
            )

        sub_results: list[dict[str, Any]] = []
        futures: dict[Any, tuple[int, dict[str, str], str]] = {}
        max_workers = max(1, min(len(jobs), _MAX_WEB_SUBAGENTS))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, boundary, q in jobs:
                futures[pool.submit(_fetch_web_rows, q)] = (idx, boundary, q)

            for fut in as_completed(futures):
                idx, boundary, q = futures[fut]
                scope_text = str(boundary.get("scope") or q)
                try:
                    rows = fut.result() or []
                except Exception as exc:
                    sub_results.append(
                        {"idx": idx, "query": q, "scope": scope_text, "status": "failed", "error": str(exc)[:140], "rows": []}
                    )
                    continue
                provider_counts = Counter(str(getattr(it, "provider", "") or "unknown") for it in rows[:8])
                fetch_counts = Counter(str(getattr(it, "fetch_mode", "") or "none") for it in rows[:8])
                sub_results.append(
                    {
                        "idx": idx,
                        "query": q,
                        "scope": scope_text,
                        "status": ("completed" if rows else "failed"),
                        "error": ("" if rows else "no result"),
                        "rows": rows,
                        "provider_counts": dict(provider_counts),
                        "fetch_counts": dict(fetch_counts),
                    }
                )

        sub_results.sort(key=lambda item: int(item.get("idx") or 0))
        return {"sub_results": sub_results}

    local_state: dict[str, Any] = {"sub_results": [], "citations": []}
    web_state: dict[str, Any] = {"sub_results": []}
    if local_jobs or web_jobs:
        futures: dict[Any, str] = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            if local_jobs:
                futures[pool.submit(_run_local_worker, local_jobs)] = "local"
            if web_jobs:
                futures[pool.submit(_run_web_worker, web_jobs)] = "web"
            for fut in as_completed(futures):
                kind = futures[fut]
                try:
                    payload_out = fut.result() or {}
                except Exception as exc:
                    payload_out = {"worker_error": str(exc)[:160]}
                if kind == "local":
                    local_state = payload_out
                else:
                    web_state = payload_out

    if local_jobs:
        worker_error = str(local_state.get("worker_error") or "").strip()
        if worker_error:
            add_trace("local_search", status="failed", detail=f"worker_error: {worker_error}", count=0)
        else:
            for item in local_state.get("sub_results") or []:
                idx = int(item.get("idx") or 0)
                add_trace(
                    f"local_search_subagent_{idx}",
                    status=str(item.get("status") or "failed"),
                    detail=str(item.get("detail") or "")[:200],
                    count=max(0, int(item.get("count") or 0)),
                )
            local_citations = list(local_state.get("citations") or [])
            if local_citations:
                local_citations = _hydrate_citation_avatars(db, current_user.id, local_citations)
            add_trace(
                "local_search",
                status="completed",
                detail="local search finished",
                count=len(local_citations),
            )

    if web_jobs:
        worker_error = str(web_state.get("worker_error") or "").strip()
        if worker_error:
            add_trace("web_search", status="failed", detail=f"worker_error: {worker_error}", count=0)
        else:
            total = len(web_jobs)
            completed = 0
            evidence_count = 0
            for item in web_state.get("sub_results") or []:
                idx = int(item.get("idx") or 0)
                q = str(item.get("query") or "").strip()
                sub_stage = f"web_search_subagent_{idx}"
                completed += 1
                rows = item.get("rows") if isinstance(item.get("rows"), list) else []
                if (str(item.get("status") or "") != "completed") or (not rows):
                    failure_detail = str(item.get("error") or "no result").strip()
                    detail = f"{q}: {failure_detail}" if q else failure_detail
                    add_trace(sub_stage, status="failed", detail=detail[:200])
                    continue

                web_results_for_answer.extend(rows[:_WEB_SEARCH_MAX_RESULTS])
                provider_counts = Counter({str(k): int(v) for k, v in (item.get("provider_counts") or {}).items()})
                fetch_counts = Counter({str(k): int(v) for k, v in (item.get("fetch_counts") or {}).items()})
                web_provider_totals.update(provider_counts)
                web_fetch_mode_totals.update(fetch_counts)
                provider_note = ",".join(f"{name}:{count}" for name, count in provider_counts.most_common(3))
                fetch_note = ",".join(f"{name}:{count}" for name, count in fetch_counts.most_common(3))
                try:
                    persisted = _persist_web_search_results(
                        db,
                        current_user.id,
                        query=q,
                        results=rows,
                    )
                except Exception:
                    persisted = []
                web_citations.extend(persisted)
                for row in rows[:_WEB_SEARCH_MAX_RESULTS]:
                    host = _domain_from_url(row.url)
                    snippet = ((getattr(row, "fetched_excerpt", "") or "").strip() or (row.snippet or "").strip())
                    provider_name = str(getattr(row, "provider", "") or "unknown")
                    fetch_mode = str(getattr(row, "fetch_mode", "") or "none")
                    line = f"- [Web/{provider_name}/{fetch_mode}] {row.title} ({host})"
                    if snippet:
                        line += f" | {snippet}"
                    web_evidence_lines.append(line)
                for ridx, cite in enumerate(persisted, start=1):
                    evidence_count += 1
                    snippet = ""
                    provider_name = "unknown"
                    fetch_mode = "none"
                    if ridx - 1 < len(rows):
                        row = rows[ridx - 1]
                        snippet = (
                            (getattr(row, "fetched_excerpt", "") or "").strip()
                            or (row.snippet or "").strip()
                        )[:280]
                        provider_name = str(getattr(row, "provider", "") or "unknown")
                        fetch_mode = str(getattr(row, "fetch_mode", "") or "none")
                    emit(
                        "evidence",
                        {
                            "citation": cite.model_dump(),
                            "snippet": snippet,
                            "query": q,
                            "provider": provider_name,
                            "fetch_mode": fetch_mode,
                            "progress": {
                                "query_index": completed,
                                "query_total": total,
                                "evidence_count": evidence_count,
                            },
                        },
                    )
                add_trace(
                    sub_stage,
                    status="completed",
                    detail=f"{str(item.get('scope') or q)}; p={provider_note or 'unknown'}; f={fetch_note or 'none'}",
                    count=len(persisted),
                )

            provider_total_note = ",".join(f"{name}:{count}" for name, count in web_provider_totals.most_common(4))
            fetch_total_note = ",".join(f"{name}:{count}" for name, count in web_fetch_mode_totals.most_common(4))
            add_trace(
                "web_search",
                status="completed" if web_citations else "failed",
                detail=(
                    f"web search finished; p={provider_total_note or 'none'}; f={fetch_total_note or 'none'}"
                    if web_citations
                    else "web search empty"
                ),
                count=len(web_citations),
            )

    max_citations = max(1, min(20, int(payload.max_citations or 6)))
    citations = _dedupe_citations([*local_citations, *web_citations], limit=max_citations)
    if diary_only_mode:
        citations = []
        web_results_for_answer = []
        web_evidence_lines = []

    file_memory_items_raw = (
        tracking_snapshot.get("matched_file_items")
        if isinstance(tracking_snapshot, dict) and isinstance(tracking_snapshot.get("matched_file_items"), list)
        else []
    )
    file_memory_items: list[dict[str, Any]] = []
    for row in file_memory_items_raw[:12]:
        if not isinstance(row, dict):
            continue
        file_memory_items.append(
            {
                "path": str(row.get("path") or "").strip()[:400],
                "title": str(row.get("title") or "").strip()[:220],
                "preview": str(row.get("preview") or "").strip()[:520],
                "score": float(row.get("score") or 0.0),
                "updated_at": str(row.get("updated_at") or "").strip()[:80],
                "source": str(row.get("source") or "").strip()[:32],
                "kind": str(row.get("kind") or "").strip()[:24],
                "target": str(row.get("target") or "").strip()[:255],
                "topic_path": str(row.get("topic_path") or "").strip()[:260],
                "entry_kind": str(row.get("entry_kind") or "").strip()[:48],
            }
        )

    if (not file_memory_items) and (not local_jobs) and (need_local_search or diary_only_mode) and payload.query.strip():
        try:
            fallback_hits = _tracking_file_memory.search(
                user_id=current_user.id,
                workspace=payload.workspace,
                query=payload.query,
                limit=8,
                include_diary=diary_only_mode,
            )
            file_memory_items = [
                {
                    "path": str(item.path),
                    "title": str(item.title),
                    "preview": str(item.preview),
                    "score": float(item.score),
                    "updated_at": str(item.updated_at),
                    "source": str(item.source),
                    "kind": str(item.kind),
                    "target": str(item.target),
                    "topic_path": str(item.topic_path),
                    "entry_kind": str(item.entry_kind),
                }
                for item in fallback_hits[:8]
            ]
        except Exception:
            file_memory_items = []

    file_memory_lines: list[str] = []
    for item in file_memory_items[:6]:
        title = str(item.get("title") or item.get("target") or "memory").strip()
        preview = re.sub(r"\s+", " ", str(item.get("preview") or "")).strip()[:160]
        source = str(item.get("source") or "tracking").strip() or "tracking"
        kind = str(item.get("kind") or "memory").strip() or "memory"
        topic_path = str(item.get("topic_path") or "").strip()
        path = str(item.get("path") or "").strip()[:220]
        line = f"- [{source}/{kind}] {title}"
        if topic_path:
            line += f" | topic={topic_path}"
        if preview:
            line += f" | {preview}"
        if path:
            line += f" | path={path}"
        file_memory_lines.append(line)

    add_trace(
        "message_hub",
        status="completed",
        detail=f"merged local={len(local_citations)} web={len(web_citations)} file={len(file_memory_items)}",
        count=len(citations),
    )
    add_trace(
        "file_memory_search",
        status="completed" if file_memory_items else "skipped",
        detail="file memory hits merged" if file_memory_items else "no file memory hits",
        count=len(file_memory_items),
    )
    if bool(getattr(settings, "aelin_parallel_memory_draft_enabled", True)):
        draft_citation_rows = [
            {
                "message_id": int(it.message_id or 0),
                "source": str(it.source or ""),
                "source_label": str(it.source_label or ""),
                "sender": str(it.sender or ""),
                "title": str(it.title or ""),
            }
            for it in citations[:12]
        ]
        draft_web_rows = [
            {
                "title": str(getattr(row, "title", "") or ""),
                "url": str(getattr(row, "url", "") or ""),
                "host": _domain_from_url(str(getattr(row, "url", "") or "")),
                "snippet": (
                    (str(getattr(row, "fetched_excerpt", "") or "").strip() or str(getattr(row, "snippet", "") or "").strip())
                )[:260],
            }
            for row in web_results_for_answer[:10]
        ]
        if draft_citation_rows or file_memory_items or draft_web_rows:
            add_trace(
                "parallel_draft",
                status="running",
                detail=f"parallel draft start local={len(draft_citation_rows)} web={len(draft_web_rows)} file={len(file_memory_items)}",
                count=len(draft_citation_rows) + len(draft_web_rows) + len(file_memory_items),
            )
            parallel_draft_future = _memory_draft_executor.submit(
                build_parallel_memory_draft,
                query=payload.query,
                citations=draft_citation_rows,
                file_memory_items=file_memory_items[:8],
                web_results=draft_web_rows,
                memory_summary=memory_summary,
                brief_summary=brief_summary,
            )
        else:
            add_trace("parallel_draft", status="skipped", detail="no retrieval evidence", count=0)
    else:
        add_trace("parallel_draft", status="skipped", detail="disabled by settings", count=0)

    pin_lines = [
        f"{item.display_name}(score {item.score:.1f}, unread {item.unread_count})"
        for item in active_bundle.get("pin_recommendations", [])[:4]
    ]
    memory_prompt = _memory.build_system_memory_prompt(
        db,
        current_user.id,
        query=payload.query if need_local_search else "",
    )
    structured_tool_runs: list[dict[str, Any]] = []
    structured_tool_lines: list[str] = []
    structured_tool_actions: list[AelinAction] = []
    if should_attempt_aelin_tools(payload.query):
        add_trace("structured_tools", status="running", detail="planning structured tools")
        tool_hub = AelinToolHub(
            db=db,
            user_id=current_user.id,
            workspace=payload.workspace,
            memory_service=_memory,
            tracking_service=_tracking,
            file_memory_bridge=_tracking_file_memory,
            web_search_service=_scoped_web_search_service(getattr(service.config, "web_search_proxy_url", "")),
        )
        runs, tool_err = run_aelin_structured_tools(
            service=service,
            provider=provider,
            query=payload.query,
            memory_summary=memory_summary,
            tool_hub=tool_hub,
            max_calls=2,
        )
        structured_tool_runs = list(runs or [])
        structured_tool_lines = summarize_tool_results_for_prompt(structured_tool_runs, max_lines=8)
        if structured_tool_runs:
            add_trace("structured_tools", status="completed", detail="structured tools executed", count=len(structured_tool_runs))
        else:
            add_trace(
                "structured_tools",
                status=("failed" if tool_err and not tool_err.startswith("no_tool_call") else "skipped"),
                detail=(tool_err[:180] if tool_err else "no structured tools needed"),
                count=0,
            )
        for run in structured_tool_runs:
            if str(run.get("name") or "").strip().lower() != "tracking":
                continue
            result = run.get("result") if isinstance(run.get("result"), dict) else {}
            target_id = int(result.get("target_id") or 0) if str(result.get("target_id") or "").isdigit() else 0
            target = str(result.get("target") or "").strip()
            if target_id <= 0:
                continue
            structured_tool_actions.append(
                AelinAction(
                    kind="open_tracking",
                    title="已通过工具创建追踪",
                    detail=(target[:120] if target else f"target_id={target_id}"),
                    payload={"target_id": str(target_id), "workspace": payload.workspace},
                )
            )
        if structured_tool_runs:
            first_diary = next(
                (
                    run
                    for run in structured_tool_runs
                    if str(run.get("name") or "").strip().lower() == "diary"
                    and isinstance(run.get("result"), dict)
                ),
                None,
            )
            if isinstance(first_diary, dict):
                diary_result = first_diary.get("result") if isinstance(first_diary.get("result"), dict) else {}
                first_item = (diary_result.get("items") or [None])[0] if isinstance(diary_result.get("items"), list) else None
                if isinstance(first_item, dict):
                    detail_path = str(first_item.get("path") or "").strip()[:220]
                    if detail_path:
                        structured_tool_actions.append(
                            AelinAction(
                                kind="open_tracking",
                                title="查看工具命中的日记",
                                detail=detail_path,
                                payload={"workspace": payload.workspace, "path": detail_path},
                            )
                        )
    else:
        add_trace("structured_tools", status="skipped", detail="query not tool-oriented", count=0)

    add_trace("generation", status="running", detail="composing answer")
    generation_detail = "generation completed"

    if provider == "rule_based":
        if local_citations:
            answer = _rule_based_answer(
                payload.query,
                memory_summary,
                citations,
                brief_summary=brief_summary,
                todo_titles=todo_titles,
                image_count=len(images),
            )
            generation_detail = "rule_based with local evidence"
        elif file_memory_lines:
            if diary_only_mode:
                answer = (
                    "我仅根据 Aelin の日记命中了以下记录：\n"
                    + "\n".join(file_memory_lines[:4])
                    + "\n\n若你希望，我可以继续只在日记里追加检索，不触发联网。"
                )
            else:
                answer = (
                    f"我先从你的长期追踪记忆里查到了与“{payload.query.strip()}”相关的线索：\n"
                    + "\n".join(file_memory_lines[:4])
                    + "\n\n如果你需要，我可以继续结合联网结果补全并持续跟踪。"
                )
            generation_detail = "rule_based with file memory"
        elif web_evidence_lines:
            answer = _compose_web_first_answer(payload.query, web_results_for_answer)
            generation_detail = "rule_based with web evidence"
        else:
            answer = _rule_based_chat_answer(
                payload.query,
                memory_summary=memory_summary,
                brief_summary=brief_summary,
            )
            generation_detail = "rule_based chat-only"
    elif not service.is_configured():
        answer = (
            "当前模型连接不可用，Aelin 暂时无法调用外部模型。\n\n"
            "请先检查 Provider / Base URL / API Key 配置后重试。"
        )
        generation_detail = "llm not configured"
    else:
        evidence_block = "\n".join(
            f"- [{it.source_label}] {it.title} ({it.sender}, {it.received_at})"
            for it in citations[:8]
        ) if citations else ""
        prompt = (
            "You are Aelin, a signal-native assistant.\n"
            "Always answer in Simplified Chinese.\n"
            "Answer the user's question directly first.\n"
            "If retrieval evidence is provided, use it directly and do not ask user to search manually.\n"
            "If evidence is weak, state uncertainty and avoid fabrication.\n"
            + ("STRICT MODE: user requested diary-only context, never inject web facts.\n" if diary_only_mode else "")
            + "Keep response concise and practical.\n"
            + "You may use 0-2 natural emoji in the answer body when it helps tone.\n"
            + "Aelin has 11 expressions. Choose one according to semantics below:\n"
            + _expression_mapping_prompt()
            + "\n"
            + "You MUST append exactly one tag at the end: [expression:exp-XX].\n"
            + "Optional emoji control tag is allowed only before the final expression tag: [emoji:🙂]."
        )
        retrieval_note = (
            f"planner={planning_reason}; "
            f"local={'on' if need_local_search else 'off'}; "
            f"web={'on' if need_web_search else 'off'}; "
            f"file_mem={len(file_memory_items)}; "
            f"profile={len(profile_injection_lines)}; "
            f"structured_tools={len(structured_tool_runs)}"
        )
        user_msg = (
            f"用户问题: {payload.query.strip()}\n\n"
            f"工具规划: {retrieval_note}\n\n"
            + ("约束: 仅可使用 Aelin 日记/文件记忆命中，不可联网补充。\n\n" if diary_only_mode else "")
            + (
                "最近对话:\n"
                + "\n".join(
                    f"- {'用户' if turn['role'] == 'user' else 'Aelin'}: {turn['content'][:220]}"
                    for turn in history_turns[-6:]
                )
                + "\n\n"
                if history_turns else ""
            )
            + f"长期记忆摘要: {memory_summary or '暂无'}\n\n"
            + (
                "固定注入用户画像/备注:\n"
                + "\n".join(profile_injection_lines[:12])
                + "\n\n"
                if profile_injection_lines else "固定注入用户画像/备注: 暂无\n\n"
            )
            + f"今日简报: {brief_summary or '暂无'}\n\n"
            + f"待跟进事项: {'; '.join(todo_titles[:5]) if todo_titles else '暂无'}\n\n"
            + f"置顶建议: {'; '.join(pin_lines) if pin_lines else '暂无'}\n\n"
            + (
                "用户上传图片:\n"
                + "\n".join(f"- {img['name'] or 'image'}" for img in images)
                + "\n\n"
                if images else ""
            )
            + (f"本地证据:\n{evidence_block}\n\n" if evidence_block else "")
            + (f"文件记忆命中:\n{chr(10).join(file_memory_lines[:6])}\n\n" if file_memory_lines else "")
            + (f"结构化工具结果:\n{chr(10).join(structured_tool_lines[:8])}\n\n" if structured_tool_lines else "")
            + (f"联网证据:\n{chr(10).join(web_evidence_lines[:8])}\n" if web_evidence_lines else "")
        )
        llm_messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        if memory_prompt:
            llm_messages.append({"role": "system", "content": memory_prompt})
        if history_turns:
            llm_messages.extend(history_turns[-10:])
        if images:
            user_content: list[dict[str, Any]] = [{"type": "text", "text": user_msg}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": img["data_url"]}})
            llm_messages.append({"role": "user", "content": user_content})
        else:
            llm_messages.append({"role": "user", "content": user_msg})

        llm_error: str | None = None
        answer = ""
        try:
            raw = service._chat(
                messages=llm_messages,
                max_tokens=520,
                stream=False,
            )
            answer = str(raw).strip() if raw else ""
            generation_detail = "llm generation succeeded"
        except Exception as e:
            llm_error = str(e)
            llm_generation_failed = True
            generation_detail = f"llm failed: {llm_error[:120]}"
            if images:
                fallback_messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
                if memory_prompt:
                    fallback_messages.append({"role": "system", "content": memory_prompt})
                fallback_messages.append({"role": "user", "content": user_msg})
                try:
                    raw = service._chat(
                        messages=fallback_messages,
                        max_tokens=520,
                        stream=False,
                    )
                    maybe = str(raw).strip() if raw else ""
                    if maybe:
                        answer = "当前模型可能不支持图片输入，以下是基于文本上下文的回复：\n\n" + maybe
                        generation_detail = "llm fallback text-only succeeded"
                except Exception as e2:
                    if not llm_error:
                        llm_error = str(e2)
        if not answer:
            if citations:
                answer = _rule_based_answer(
                    payload.query,
                    memory_summary,
                    citations,
                    brief_summary=brief_summary,
                    todo_titles=todo_titles,
                    image_count=len(images),
                )
                generation_detail = "fallback to rule_based with citations"
            else:
                answer = (
                    "我刚才调用外部模型失败，先给你一个保底回复。"
                    + (f"\n\n错误：{llm_error}" if llm_error else "")
                    + "\n\n"
                    + _rule_based_chat_answer(
                        payload.query,
                        memory_summary=memory_summary,
                        brief_summary=brief_summary,
                    )
                )
                generation_detail = "fallback to rule_based chat"
        if answer and web_results_for_answer and _looks_like_link_dump_answer(answer):
            guarded = _compose_web_first_answer(payload.query, web_results_for_answer)
            if guarded:
                answer = guarded
            generation_detail = f"{generation_detail}; retrieval evidence guard applied"

    answer = _enforce_answer_first(
        query=payload.query,
        answer=answer,
        citations=citations,
        web_results=web_results_for_answer,
        memory_summary=memory_summary,
        brief_summary=brief_summary,
        todo_titles=todo_titles,
        image_count=len(images),
        allow_web_fallback=not diary_only_mode,
    )

    answer, tagged_expression = _extract_expression_tag(answer)
    answer, tagged_emoji = _extract_emoji_tag(answer)
    expression = tagged_expression or _pick_expression(payload.query, answer, generation_failed=llm_generation_failed)
    answer = _apply_answer_emoji(answer, expression, explicit_emoji=tagged_emoji)
    add_trace("generation", status="completed", detail=generation_detail, count=len(citations))

    add_trace("grounding_judge", status="running", detail="checking grounding", count=len(citations))
    grounded, grounding_reason = _judge_answer_grounding(
        query=payload.query,
        answer=answer,
        citations=citations,
        intent_contract=intent_contract,
        service=service,
        provider=provider,
    )
    add_trace(
        "grounding_judge",
        status="completed" if grounded else "failed",
        detail=grounding_reason,
        count=len(citations),
    )

    add_trace("coverage_verifier", status="running", detail="checking evidence coverage", count=len(citations))
    coverage_ok, coverage_reason = _check_evidence_coverage(
        query=payload.query,
        intent_contract=intent_contract,
        answer=answer,
        citations=citations,
        web_results=web_results_for_answer,
        diary_only_mode=diary_only_mode,
    )
    add_trace(
        "coverage_verifier",
        status="completed" if coverage_ok else "failed",
        detail=coverage_reason,
        count=len(citations),
    )

    add_trace("reply_verifier", status="running", detail="verifying reply quality", count=len(citations))
    verified, verify_reason = _verify_reply_answer(
        query=payload.query,
        answer=answer,
        need_web_search=need_web_search,
        citations=citations,
        diary_only_mode=diary_only_mode,
    )
    retried_web = 0
    has_web_evidence = any(str(it.source or "").strip().lower() == "web" for it in citations)
    requires_citations = bool(intent_contract.get("requires_citations")) if isinstance(intent_contract, dict) else False
    quality_failed = (not verified) or (not grounded) or (not coverage_ok)
    allow_quality_retry = (not diary_only_mode) and (
        bool(route.get("allow_web_retry")) or (requires_citations and (not has_web_evidence))
    )
    if quality_failed and allow_quality_retry:
        retry_queries = _build_retry_web_queries(
            payload.query,
            used_web_queries,
            intent_contract=intent_contract,
            tracking_snapshot=tracking_snapshot,
        )
        if retry_queries:
            retried_web = len(retry_queries)
            add_trace("web_search", status="running", detail=f"verifier retry x{len(retry_queries)}", count=len(web_citations))
            base_idx = len(web_boundaries)
            evidence_count = len(web_citations)
            retry_provider_totals: Counter[str] = Counter()
            retry_fetch_totals: Counter[str] = Counter()
            for idx, rq in enumerate(retry_queries, start=1):
                sub_stage = f"web_search_subagent_{base_idx + idx}"
                add_trace(sub_stage, status="running", detail=rq)
                try:
                    rows = _web_search.search_and_fetch(
                        rq,
                        max_results=_WEB_SEARCH_MAX_RESULTS,
                        fetch_top_k=_WEB_SEARCH_FETCH_TOP_K,
                    )
                except Exception as e:
                    add_trace(sub_stage, status="failed", detail=f"{rq}: {str(e)[:140]}")
                    continue
                if not rows:
                    add_trace(sub_stage, status="failed", detail=f"{rq}: no result")
                    continue
                web_results_for_answer.extend(rows[:5])
                provider_counts = Counter(str(getattr(it, "provider", "") or "unknown") for it in rows[:8])
                fetch_counts = Counter(str(getattr(it, "fetch_mode", "") or "none") for it in rows[:8])
                retry_provider_totals.update(provider_counts)
                retry_fetch_totals.update(fetch_counts)
                web_provider_totals.update(provider_counts)
                web_fetch_mode_totals.update(fetch_counts)
                provider_note = ",".join(f"{name}:{count}" for name, count in provider_counts.most_common(3))
                fetch_note = ",".join(f"{name}:{count}" for name, count in fetch_counts.most_common(3))
                persisted = _persist_web_search_results(
                    db,
                    current_user.id,
                    query=rq,
                    results=rows,
                )
                web_citations.extend(persisted)
                for ridx, cite in enumerate(persisted, start=1):
                    evidence_count += 1
                    snippet = ""
                    provider_name = "unknown"
                    fetch_mode = "none"
                    if ridx - 1 < len(rows):
                        row = rows[ridx - 1]
                        snippet = (
                            (getattr(row, "fetched_excerpt", "") or "").strip()
                            or (row.snippet or "").strip()
                        )[:280]
                        provider_name = str(getattr(row, "provider", "") or "unknown")
                        fetch_mode = str(getattr(row, "fetch_mode", "") or "none")
                    emit(
                        "evidence",
                        {
                            "citation": cite.model_dump(),
                            "snippet": snippet,
                            "query": rq,
                            "provider": provider_name,
                            "fetch_mode": fetch_mode,
                            "progress": {
                                "query_index": idx,
                                "query_total": len(retry_queries),
                                "evidence_count": evidence_count,
                            },
                        },
                    )
                add_trace(
                    sub_stage,
                    status="completed",
                    detail=f"{rq}; p={provider_note or 'unknown'}; f={fetch_note or 'none'}",
                    count=len(persisted),
                )
            retry_provider_note = ",".join(f"{name}:{count}" for name, count in retry_provider_totals.most_common(4))
            retry_fetch_note = ",".join(f"{name}:{count}" for name, count in retry_fetch_totals.most_common(4))
            add_trace(
                "web_search",
                status="completed" if web_citations else "failed",
                detail=f"verifier retry finished; p={retry_provider_note or 'none'}; f={retry_fetch_note or 'none'}",
                count=len(web_citations),
            )
            citations = _dedupe_citations([*local_citations, *web_citations], limit=max_citations)
            add_trace(
                "message_hub",
                status="completed",
                detail=f"post-retry merge local={len(local_citations)} web={len(web_citations)}",
                count=len(citations),
            )
            if web_results_for_answer and (
                provider == "rule_based"
                or _looks_like_link_dump_answer(answer)
                or not _answer_has_fact_signal(answer)
            ):
                guarded = _compose_web_first_answer(payload.query, web_results_for_answer)
                if guarded:
                    answer = guarded
                add_trace(
                    "generation",
                    status="completed",
                    detail="response refreshed after verifier retry; retrieval evidence guard applied",
                    count=len(citations),
                )
            verified, verify_reason = _verify_reply_answer(
                query=payload.query,
                answer=answer,
                need_web_search=bool(need_web_search or retried_web),
                citations=citations,
                diary_only_mode=diary_only_mode,
            )
            grounded, grounding_reason = _judge_answer_grounding(
                query=payload.query,
                answer=answer,
                citations=citations,
                intent_contract=intent_contract,
                service=service,
                provider=provider,
            )
            add_trace(
                "grounding_judge",
                status="completed" if grounded else "failed",
                detail=f"post_retry:{grounding_reason}",
                count=len(citations),
            )
            coverage_ok, coverage_reason = _check_evidence_coverage(
                query=payload.query,
                intent_contract=intent_contract,
                answer=answer,
                citations=citations,
                web_results=web_results_for_answer,
                diary_only_mode=diary_only_mode,
            )
            add_trace(
                "coverage_verifier",
                status="completed" if coverage_ok else "failed",
                detail=f"post_retry:{coverage_reason}",
                count=len(citations),
            )

    verifier_detail = verify_reason
    if retried_web:
        verifier_detail = f"{verify_reason}; retried_web={retried_web}"
    if not grounded:
        verifier_detail = f"{verifier_detail}; grounding={grounding_reason}"
    if not coverage_ok:
        verifier_detail = f"{verifier_detail}; coverage={coverage_reason}"
    add_trace(
        "reply_verifier",
        status="completed" if (verified and grounded and coverage_ok) else "failed",
        detail=verifier_detail,
        count=len(citations),
    )
    if parallel_draft_future is not None and parallel_draft_result is None:
        timeout_seconds = max(
            0.3,
            min(6.0, float(getattr(settings, "aelin_parallel_memory_draft_timeout_seconds", 2.0) or 2.0)),
        )
        try:
            parallel_draft_result = parallel_draft_future.result(timeout=timeout_seconds)
            add_trace(
                "parallel_draft",
                status="completed",
                detail=(
                    f"draft ready; evidence={int(parallel_draft_result.evidence_count or 0)}; "
                    f"conf={float(parallel_draft_result.confidence or 0.0):.2f}"
                ),
                count=int(parallel_draft_result.evidence_count or 0),
            )
        except Exception as exc:
            add_trace("parallel_draft", status="failed", detail=f"draft timeout/error:{str(exc)[:140]}", count=0)

    answer = _enforce_answer_first(
        query=payload.query,
        answer=answer,
        citations=citations,
        web_results=web_results_for_answer,
        memory_summary=memory_summary,
        brief_summary=brief_summary,
        todo_titles=todo_titles,
        image_count=len(images),
        allow_web_fallback=not diary_only_mode,
    )
    answer, maybe_expression = _extract_expression_tag(answer)
    if maybe_expression:
        expression = maybe_expression

    trace_should_run = bool(route.get("trace_agent")) or bool(planned_track_suggestion)
    track_suggestion = planned_track_suggestion if isinstance(planned_track_suggestion, dict) else None
    trace_local_citations: list[AelinCitation] = []
    trace_web_citations: list[AelinCitation] = []
    trace_web_results: list[WebSearchResult] = []
    if trace_should_run:
        add_trace(
            "trace_agent",
            status="running",
            detail=f"dispatching local={len(trace_local_boundaries)} web={len(trace_web_boundaries)}",
        )
        add_trace(
            "trace_dispatch",
            status="completed",
            detail=f"context_boundaries={len(trace_local_boundaries) + len(trace_web_boundaries)}",
            count=len(trace_local_boundaries) + len(trace_web_boundaries),
        )
        trace_jobs: list[dict[str, Any]] = []
        for idx, boundary in enumerate(trace_local_boundaries, start=1):
            sub_query = str(boundary.get("query") or payload.query).strip()[:180]
            sub_scope = str(boundary.get("scope") or sub_query).strip()[:120]
            add_trace(f"trace_local_subagent_{idx}", status="running", detail=sub_scope or sub_query)
            trace_jobs.append(
                {
                    "kind": "local",
                    "idx": idx,
                    "query": sub_query,
                    "scope": sub_scope,
                }
            )
        for idx, boundary in enumerate(trace_web_boundaries, start=1):
            sub_query = str(boundary.get("query") or payload.query).strip()[:180]
            sub_scope = str(boundary.get("scope") or sub_query).strip()[:120]
            add_trace(f"trace_web_subagent_{idx}", status="running", detail=sub_scope or sub_query)
            trace_jobs.append(
                {
                    "kind": "web",
                    "idx": idx,
                    "query": sub_query,
                    "scope": sub_scope,
                }
            )

        def _trace_local_lookup(raw_query: str) -> tuple[list[AelinCitation], str]:
            return _fetch_local_focus_citations(
                user_id=current_user.id,
                query=raw_query,
                max_citations=payload.max_citations,
            )

        def _trace_web_lookup(raw_query: str) -> list[WebSearchResult]:
            return _web_search.search_and_fetch(
                raw_query,
                max_results=_WEB_SEARCH_MAX_RESULTS,
                fetch_top_k=_WEB_SEARCH_FETCH_TOP_K,
            )

        futures: dict[Any, dict[str, Any]] = {}
        if trace_jobs:
            max_trace_workers = max(1, min(len(trace_jobs), _MAX_LOCAL_SUBAGENTS + _MAX_WEB_SUBAGENTS))
            with ThreadPoolExecutor(max_workers=max_trace_workers) as pool:
                for job in trace_jobs:
                    if job["kind"] == "local":
                        futures[pool.submit(_trace_local_lookup, str(job["query"]))] = job
                    else:
                        futures[pool.submit(_trace_web_lookup, str(job["query"]))] = job

                for fut in as_completed(futures):
                    job = futures[fut]
                    kind = str(job.get("kind") or "")
                    idx = int(job.get("idx") or 0)
                    query_text = str(job.get("query") or "")
                    scope_text = str(job.get("scope") or query_text)
                    if kind == "local":
                        sub_stage = f"trace_local_subagent_{idx}"
                        try:
                            cites, trace_local_error = fut.result()
                        except Exception as e:
                            add_trace(sub_stage, status="failed", detail=f"{scope_text or query_text}: {str(e)[:140]}")
                            continue
                        if trace_local_error:
                            add_trace(sub_stage, status="failed", detail=f"{scope_text or query_text}: {trace_local_error}")
                            continue
                        trace_local_citations.extend(cites or [])
                        add_trace(sub_stage, status="completed", detail=scope_text or query_text, count=len(cites or []))
                        continue

                    sub_stage = f"trace_web_subagent_{idx}"
                    try:
                        rows = fut.result() or []
                    except Exception as e:
                        add_trace(sub_stage, status="failed", detail=f"{scope_text or query_text}: {str(e)[:140]}")
                        continue
                    if not rows:
                        add_trace(sub_stage, status="failed", detail=f"{scope_text or query_text}: no result")
                        continue
                    trace_web_results.extend(rows[:_WEB_SEARCH_MAX_RESULTS])
                    provider_counts = Counter(
                        str(getattr(it, "provider", "") or "unknown")
                        for it in rows[:_WEB_SEARCH_MAX_RESULTS]
                    )
                    fetch_counts = Counter(
                        str(getattr(it, "fetch_mode", "") or "none")
                        for it in rows[:_WEB_SEARCH_MAX_RESULTS]
                    )
                    provider_note = ",".join(f"{name}:{count}" for name, count in provider_counts.most_common(3))
                    fetch_note = ",".join(f"{name}:{count}" for name, count in fetch_counts.most_common(3))
                    try:
                        persisted = _persist_web_search_results(
                            db,
                            current_user.id,
                            query=query_text,
                            results=rows,
                        )
                    except Exception:
                        persisted = []
                    trace_web_citations.extend(persisted)
                    add_trace(
                        sub_stage,
                        status="completed",
                        detail=f"{scope_text or query_text}; p={provider_note or 'unknown'}; f={fetch_note or 'none'}",
                        count=len(persisted),
                    )

        if trace_local_citations:
            trace_local_citations = _hydrate_citation_avatars(db, current_user.id, trace_local_citations)
        trace_merged = _dedupe_citations([*trace_local_citations, *trace_web_citations], limit=max_citations)
        if trace_merged:
            citations = _dedupe_citations([*citations, *trace_merged], limit=max_citations)
            add_trace(
                "message_hub",
                status="completed",
                detail=f"trace merge local={len(trace_local_citations)} web={len(trace_web_citations)}",
                count=len(citations),
            )
            web_results_for_answer.extend(trace_web_results[:_WEB_SEARCH_MAX_RESULTS])

        suggestion, trace_reason = _trace_agent_suggestion(
            query=payload.query,
            planned_track_suggestion=track_suggestion if isinstance(track_suggestion, dict) else None,
            citations=citations,
            need_web_search=bool(need_web_search or retried_web or trace_web_citations),
        )
        if suggestion:
            track_suggestion = suggestion
            source_list = sorted({str(it.source or "").strip() for it in citations if str(it.source or "").strip()})
            emit(
                "confirmed",
                {
                    "items": [str(track_suggestion.get("target") or "").strip()[:240]],
                    "source_count": len(source_list),
                    "sources": source_list[:5],
                },
            )
            add_trace("trace_agent", status="completed", detail=trace_reason, count=1)
        else:
            add_trace("trace_agent", status="completed", detail=trace_reason, count=0)
    else:
        add_trace("trace_agent", status="skipped", detail="trace route disabled")

    if media_result is not None and not media_summary_intent:
        save_note = "并写入 Aelinの日记。"
        if not media_save_state.get("written"):
            if not media_result.quality_usable:
                save_note = (
                    "但未写入 Aelinの日记（质量门禁未通过："
                    f"{media_result.quality_reason or 'quality_gate'}）。"
                )
            else:
                save_note = "但写入日记失败。"
        media_hint = (
            f"已完成链接内容摘要（{media_result.platform}/{media_result.source_type}），"
            + save_note
        )
        answer = f"{answer.strip()}\n\n{media_hint}".strip()

    if payload.use_memory and answer:
        try:
            _memory.update_after_turn(
                db,
                current_user.id,
                [{"role": "user", "content": payload.query}],
                answer,
            )
        except Exception:
            pass

    insight_write_result: dict[str, Any] = {"written": False, "reason": "not_evaluated"}
    try:
        insight_write_result = _maybe_write_tracking_insight(
            db,
            user_id=current_user.id,
            workspace=payload.workspace,
            query=payload.query,
            answer=answer,
            service=service,
            provider=provider,
            tracking_snapshot=tracking_snapshot,
            file_memory_lines=file_memory_lines,
            citations=citations,
        )
        if bool(insight_write_result.get("written")):
            detail = (
                f"target={str(insight_write_result.get('target') or '')[:80]}; "
                f"conf={float(insight_write_result.get('confidence') or 0.0):.2f}"
            )
            add_trace("insight_write", status="completed", detail=detail, count=1)
        else:
            add_trace(
                "insight_write",
                status="skipped",
                detail=str(insight_write_result.get("reason") or "planner_skip")[:160],
                count=0,
            )
    except Exception as exc:
        add_trace("insight_write", status="failed", detail=f"{str(exc)[:160]}", count=0)

    chat_diary_result: dict[str, Any] = {"written": False, "reason": "not_evaluated", "path": ""}
    try:
        chat_diary_result = _save_chat_diary_entry(
            db,
            user_id=current_user.id,
            workspace=_normalize_workspace(payload.workspace),
            query=payload.query,
            answer=answer,
            citations=citations,
        )
        if bool(chat_diary_result.get("written")):
            add_trace(
                "chat_diary_write",
                status="completed",
                detail=str(chat_diary_result.get("path") or "")[:220],
                count=1,
            )
        else:
            add_trace(
                "chat_diary_write",
                status="skipped",
                detail=str(chat_diary_result.get("reason") or "skip")[:160],
                count=0,
            )
    except Exception as exc:
        add_trace("chat_diary_write", status="failed", detail=f"{str(exc)[:160]}", count=0)
    if parallel_draft_result is None and parallel_draft_future is not None and parallel_draft_future.done():
        try:
            parallel_draft_result = parallel_draft_future.result()
            add_trace(
                "parallel_draft",
                status="completed",
                detail=(
                    f"draft ready (late); evidence={int(parallel_draft_result.evidence_count or 0)}; "
                    f"conf={float(parallel_draft_result.confidence or 0.0):.2f}"
                ),
                count=int(parallel_draft_result.evidence_count or 0),
            )
        except Exception as exc:
            add_trace("parallel_draft", status="failed", detail=f"draft late error:{str(exc)[:140]}", count=0)

    try:
        parallel_draft_commit = _save_parallel_draft_entry(
            db,
            user_id=current_user.id,
            workspace=_normalize_workspace(payload.workspace),
            query=payload.query,
            answer=answer,
            draft_result=parallel_draft_result,
            quality_passed=bool(verified and grounded and coverage_ok),
        )
        if bool(parallel_draft_commit.get("written")):
            add_trace(
                "parallel_draft_commit",
                status="completed",
                detail=str(parallel_draft_commit.get("path") or "")[:220],
                count=1,
            )
        else:
            add_trace(
                "parallel_draft_commit",
                status="skipped",
                detail=str(parallel_draft_commit.get("reason") or "skip")[:160],
                count=0,
            )
    except Exception as exc:
        add_trace("parallel_draft_commit", status="failed", detail=f"{str(exc)[:160]}", count=0)

    try:
        should_commit = False
        if payload.use_memory and answer:
            should_commit = True
        elif web_citations or trace_web_citations:
            should_commit = True
        elif bool(insight_write_result.get("written")):
            should_commit = True
        elif bool(chat_diary_result.get("written")):
            should_commit = True
        elif bool(parallel_draft_commit.get("written")):
            should_commit = True
        elif bool(media_save_state.get("written")) or bool(media_save_state.get("note_added")):
            should_commit = True
        if should_commit:
            db.commit()
    except Exception:
        db.rollback()

    final_memory_summary = str(active_bundle.get("summary") or memory_summary or "")
    actions = [
        *structured_tool_actions[:3],
        *_build_actions(
        payload.query,
        citations,
        has_todos=bool(todo_titles),
        track_suggestion=track_suggestion if isinstance(track_suggestion, dict) else None,
    )]
    if media_result is not None:
        actions.insert(
            0,
            AelinAction(
                kind="open_tracking",
                title="查看 Aelinの日记摘要",
                detail=(
                    str(media_save_state.get("diary_path") or "").strip()[:220]
                    if media_save_state.get("written")
                    else f"{media_result.platform} 摘要已生成（未落盘）"
                ),
                payload={"workspace": payload.workspace, "query": media_result.title[:120]},
            ),
        )
    if bool(insight_write_result.get("written")):
        target_id = int(insight_write_result.get("target_id") or 0)
        actions.insert(
            0,
            AelinAction(
                kind="open_tracking",
                title="已沉淀长期洞察",
                detail=str(insight_write_result.get("path") or "").strip()[:220],
                payload={
                    "target_id": str(target_id) if target_id > 0 else "",
                    "workspace": payload.workspace,
                },
            ),
        )
    if bool(parallel_draft_commit.get("written")):
        actions.insert(
            0,
            AelinAction(
                kind="open_tracking",
                title="查看并行记忆草稿",
                detail=str(parallel_draft_commit.get("path") or "").strip()[:220],
                payload={"workspace": payload.workspace, "query": payload.query[:120]},
            ),
        )

    response = AelinChatResponse(
        answer=answer,
        expression=expression,
        citations=citations,
        actions=actions,
        tool_trace=tool_trace[:64],
        memory_summary=final_memory_summary,
        generated_at=datetime.now(timezone.utc),
    )
    return response


_TRACK_CREATE_COMMAND_RE = re.compile(
    r"^(?:请|帮我|麻烦|给我)?\s*(?:创建|新建|添加|开始)?\s*(?:一个)?\s*(?:追踪|跟踪|监控|track(?:ing)?)",
    flags=re.I,
)


def _detect_forced_tracking_create(query: str) -> dict[str, str] | None:
    text = str(query or "").strip()
    if not text:
        return None
    lower = text.lower()
    has_track_word = any(token in text for token in ("追踪", "跟踪", "监控")) or any(
        token in lower for token in ("track", "tracking", "monitor")
    )
    has_create_word = any(token in text for token in ("创建", "新建", "添加", "开始"))
    if not has_track_word:
        return None
    if not (has_create_word or _TRACK_CREATE_COMMAND_RE.search(text)):
        return None

    target = ""
    for sep in ("：", ":"):
        if sep in text:
            left, right = text.split(sep, 1)
            if any(token in left for token in ("追踪", "跟踪", "监控")) or any(
                token in left.lower() for token in ("track", "tracking", "monitor")
            ):
                target = right.strip()
                break
    if not target:
        match = re.search(r"(?:追踪|跟踪|监控|track(?:ing)?)(?:目标|主题|一下)?\s*(.+)$", text, flags=re.I)
        if match:
            target = str(match.group(1) or "").strip()
    if not target:
        url_match = re.search(r"https?://[^\s<>()\"']+", text, flags=re.I)
        if url_match:
            target = str(url_match.group(0) or "").strip()

    target = re.sub(r"^[\s\-:：]+|[\s，,。！？!?]+$", "", target).strip()
    if len(target) < 2:
        return None

    source = _infer_tracking_source(target)
    return {
        "action": "create",
        "target": target[:240],
        "source": source[:32] or "web",
        "query": text[:500],
    }


def _try_agent_loop_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
    persist_memory: bool = True,
    force_disable_writes: bool = False,
    forced_tracking_create: dict[str, str] | None = None,
) -> AelinChatResponse | None:
    service, provider = _resolve_llm_service(db, current_user)
    if provider == "rule_based" or not service.is_configured():
        return None

    workspace = _normalize_workspace(payload.workspace)
    base_bundle = _build_cached_base_context_bundle(
        db,
        current_user.id,
        workspace=workspace,
    )
    memory_summary = str(base_bundle.get("summary") or "")
    history_turns = _normalize_history(payload.history)
    images = _normalize_images(payload.images)

    tool_hub = AelinToolHub(
        db=db,
        user_id=current_user.id,
        workspace=workspace,
        memory_service=_memory,
        tracking_service=_tracking,
        file_memory_bridge=_tracking_file_memory,
        web_search_service=_scoped_web_search_service(getattr(service.config, "web_search_proxy_url", "")),
    )

    prefixed_traces: list[AelinToolStep] = []
    prefixed_actions: list[AelinAction] = []
    forced_intent = ""
    forced_tool_runs: list[dict[str, Any]] = []

    def _emit_prefixed(stage: str, *, status: str, detail: str = "", count: int = 0) -> None:
        step = AelinToolStep(
            stage=str(stage or "agent_loop")[:80],
            status=str(status or "completed")[:24],
            detail=str(detail or "")[:240],
            count=max(0, int(count or 0)),
            ts=_now_ms(),
        )
        prefixed_traces.append(step)
        if event_cb is not None:
            try:
                event_cb("trace", {"step": step.model_dump()})
            except Exception:
                pass

    if forced_tracking_create and not force_disable_writes:
        forced_intent = "tracking_create"
        forced_args = {
            "action": "create",
            "target": str(forced_tracking_create.get("target") or "")[:240],
            "source": str(forced_tracking_create.get("source") or "web")[:32],
            "query": str(forced_tracking_create.get("query") or payload.query or "")[:500],
        }
        _emit_prefixed("intent_router", status="completed", detail="forced_tracking_create", count=1)
        started = time.perf_counter()
        forced_result = tool_hub.execute("tracking", forced_args)
        latency_ms = int((time.perf_counter() - started) * 1000)
        forced_tool_runs.append({"name": "tracking", "args": forced_args, "result": forced_result})
        if bool(forced_result.get("ok")) and int(forced_result.get("target_id") or 0) > 0:
            target_id = int(forced_result.get("target_id") or 0)
            prefixed_actions.append(
                AelinAction(
                    kind="open_tracking",
                    title="已创建追踪",
                    detail=str(forced_result.get("target") or f"target_id={target_id}")[:120],
                    payload={"target_id": str(target_id), "workspace": workspace},
                )
            )
            _emit_prefixed("forced_tool", status="completed", detail=f"tracking.create; latency_ms={latency_ms}", count=1)
        else:
            _emit_prefixed(
                "forced_tool",
                status="failed",
                detail=f"tracking.create failed:{str(forced_result.get('error') or 'unknown')[:140]}",
                count=0,
            )

    allow_write_tools = bool(getattr(settings, "aelin_agent_loop_allow_write_tools", False))
    if forced_tracking_create and not force_disable_writes:
        # Temporarily allow writes for this request scope only.
        allow_write_tools = True

    policy = AelinToolPolicy(
        max_calls_per_round=int(getattr(settings, "aelin_agent_loop_max_calls_per_round", 2) or 2),
        max_tool_calls=int(getattr(settings, "aelin_agent_loop_max_tool_calls", 6) or 6),
        max_write_calls=int(getattr(settings, "aelin_agent_loop_max_write_calls", 1) or 1),
        allow_write_tools=(
            False
            if force_disable_writes
            else allow_write_tools
        ),
    )
    runner = AelinAgentLoop(
        service=service,
        provider=provider,
        tool_hub=tool_hub,
        policy=policy,
        max_rounds=int(getattr(settings, "aelin_agent_loop_max_rounds", 3) or 3),
        round_timeout_seconds=float(getattr(settings, "aelin_agent_loop_round_timeout_seconds", 10.0) or 10.0),
        total_timeout_seconds=float(getattr(settings, "aelin_agent_loop_total_timeout_seconds", 12.0) or 12.0),
    )
    result = runner.run(
        query=payload.query,
        memory_summary=memory_summary,
        history_turns=history_turns,
        images=images,
        forced_intent=forced_intent,
        forced_tool_runs=forced_tool_runs,
    )

    trace_steps: list[AelinToolStep] = [*prefixed_traces]
    for step in result.trace_steps:
        trace = AelinToolStep(
            stage=str(step.stage or "agent_loop")[:80],
            status=str(step.status or "completed")[:24],
            detail=str(step.detail or "")[:240],
            count=max(0, int(step.count or 0)),
            ts=max(0, int(step.ts or _now_ms())),
        )
        trace_steps.append(trace)
        if event_cb is not None:
            try:
                event_cb("trace", {"step": trace.model_dump()})
            except Exception:
                pass

    if not bool(result.ok) or not str(result.answer or "").strip():
        if event_cb is not None:
            try:
                event_cb(
                    "trace",
                    {
                        "step": AelinToolStep(
                            stage="agent_loop",
                            status="failed",
                            detail=f"fallback_to_legacy:{str(result.stop_reason or 'unknown')[:120]}",
                            count=0,
                            ts=_now_ms(),
                        ).model_dump()
                    },
                )
            except Exception:
                pass
        return None

    if persist_memory and payload.use_memory:
        try:
            _memory.update_after_turn(
                db,
                current_user.id,
                [{"role": "user", "content": payload.query}],
                result.answer,
            )
            db.commit()
        except Exception:
            db.rollback()

    expression = _pick_expression(payload.query, result.answer)
    actions: list[AelinAction] = [*prefixed_actions]
    for raw in result.actions[:4]:
        kind = str(raw.get("kind") or "").strip()
        title = str(raw.get("title") or "").strip()
        detail = str(raw.get("detail") or "").strip()
        if not kind or not title:
            continue
        payload_map = {
            str(k): str(v)
            for k, v in raw.items()
            if str(k) not in {"kind", "title", "detail"} and str(v or "").strip()
        }
        actions.append(AelinAction(kind=kind[:32], title=title[:120], detail=detail[:220], payload=payload_map))

    return AelinChatResponse(
        answer=str(result.answer or "").strip(),
        expression=expression,
        citations=[],
        actions=actions,
        tool_trace=trace_steps[:64],
        memory_summary=memory_summary,
        generated_at=datetime.now(timezone.utc),
    )


def _dispatch_aelin_chat(
    payload: AelinChatRequest,
    db: Session,
    current_user: User,
    *,
    event_cb: Callable[[str, dict[str, Any]], None] | None = None,
) -> AelinChatResponse:
    return _dispatch_aelin_chat_service(
        payload,
        db,
        current_user,
        event_cb=event_cb,
        detect_forced_tracking_create=_detect_forced_tracking_create,
        try_agent_loop_chat=_try_agent_loop_chat,
        pick_expression=_pick_expression,
        now_ms=_now_ms,
    )
