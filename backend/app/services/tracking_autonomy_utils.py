from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

_TRACK_STATUS = {"active", "paused", "error", "deleted"}
_NOTIFY_LEVELS = {"all", "important", "critical"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json_dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return "{}"


def _json_loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_workspace(value: str) -> str:
    clean = " ".join((value or "").strip().split())
    return clean[:64] if clean else "default"


def _is_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _normalize_url_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not _is_url(raw):
        raw = f"https://{raw.lstrip('/')}"
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return ""
        return parsed._replace(fragment="").geturl()[:1000]
    except Exception:
        return raw[:1000]


def _normalize_term_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())[:900]


def _normalize_track_type(track_type: str | None, target: str) -> str:
    candidate = (track_type or "").strip().lower()
    if candidate in {"term", "url"}:
        return candidate
    return "url" if _is_url(target) else "term"


def _severity(change_type: str) -> str:
    mapping = {
        "new_item": "medium",
        "updated_item": "medium",
        "removed_item": "high",
        "status_change": "high",
        "metric_spike": "high",
        "fetch_error": "low",
        "recovered": "low",
    }
    return mapping.get(change_type, "medium")
