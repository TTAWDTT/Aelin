from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import (
    AelinDailyBrief,
    AelinDailyBriefAction,
    AelinLayoutCard,
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinNotificationItem,
    AelinPinRecommendationItem,
    AelinTodoItem,
    AgentFocusItemOut,
    AgentMemoryNoteOut,
)
from app.services.agent_memory import AgentMemoryService, serialize_focus_item


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


def build_context_bundle(
    db: Session,
    user_id: int,
    *,
    workspace: str,
    query: str,
    memory_service: AgentMemoryService,
) -> dict:
    workspace_norm = workspace
    summary = memory_service.get_summary(db, user_id)
    note_rows = memory_service.list_notes(db, user_id, limit=24)
    focus_items = memory_service.build_focus_items(db, user_id, query=query, limit=8)
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

    todos_raw = memory_service.list_todos(db, user_id, include_done=False, limit=10)
    todos: list[AelinTodoItem] = []
    for row in todos_raw:
        try:
            todos.append(AelinTodoItem(**row))
        except Exception:
            continue

    pins_raw = memory_service.recommend_pins(db, user_id, limit=6)
    pin_recommendations: list[AelinPinRecommendationItem] = []
    for row in pins_raw:
        try:
            pin_recommendations.append(AelinPinRecommendationItem(**row))
        except Exception:
            continue

    layout_rows = memory_service.get_latest_layout_cards(db, user_id, workspace=workspace_norm)
    brief_raw = memory_service.build_daily_brief_from_items(
        db,
        user_id,
        focus_items=focus_items[:6],
        todos=todos_raw,
    )
    daily_brief = AelinDailyBrief(
        generated_at=brief_raw["generated_at"],
        summary=str(brief_raw.get("summary") or ""),
        top_updates=[AgentFocusItemOut(**item) for item in brief_raw.get("top_updates", [])],
        actions=[AelinDailyBriefAction(**item) for item in brief_raw.get("actions", [])],
    )

    layout_cards = _to_layout_cards(layout_rows)
    memory_layers_raw = memory_service.build_memory_layers_from_items(
        summary=summary,
        notes=note_rows,
        focus_items=focus_items,
        todos=todos_raw,
        layout_cards=layout_rows,
        workspace=workspace_norm,
        query=query,
    )
    memory_layers = AelinMemoryLayers(
        facts=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("facts") or [])],
        preferences=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("preferences") or [])],
        in_progress=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("in_progress") or [])],
        generated_at=datetime.now(timezone.utc),
    )
    notifications = [
        AelinNotificationItem(**item)
        for item in memory_service.build_notifications_from_items(
            db,
            user_id,
            brief=brief_raw,
            todos=todos_raw,
            limit=24,
        )
    ]

    serialized_focus_items = [serialize_focus_item(item) for item in focus_items]

    return {
        "workspace": workspace_norm,
        "summary": str(summary or ""),
        "focus_items": [AgentFocusItemOut(**item) for item in serialized_focus_items],
        "focus_items_raw": serialized_focus_items,
        "notes": notes,
        "notes_count": len(notes),
        "todos": todos,
        "pin_recommendations": pin_recommendations,
        "daily_brief": daily_brief,
        "layout_cards": layout_cards,
        "memory_layers": memory_layers,
        "notifications": notifications,
    }


def build_cached_base_context_bundle(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    memory_service: AgentMemoryService,
    ttl_seconds: float,
    max_entries: int,
    cache: dict[tuple[int, str], tuple[float, dict[str, Any]]],
    lock,
) -> dict[str, Any]:
    workspace_norm = workspace
    if ttl_seconds <= 0 or max_entries <= 0:
        return build_context_bundle(db, user_id, workspace=workspace_norm, query="", memory_service=memory_service)

    cache_key = (int(user_id), workspace_norm)
    now = time.monotonic()
    with lock:
        hit = cache.get(cache_key)
        if hit is not None:
            ts, cached_bundle = hit
            if (now - float(ts)) <= ttl_seconds and isinstance(cached_bundle, dict):
                return cached_bundle
            cache.pop(cache_key, None)

    bundle = build_context_bundle(db, user_id, workspace=workspace_norm, query="", memory_service=memory_service)
    with lock:
        cache[cache_key] = (now, bundle)
        _prune_ttl_cache(cache, max_entries=max_entries)
    return bundle


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

