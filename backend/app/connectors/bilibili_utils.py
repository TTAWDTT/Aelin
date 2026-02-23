from __future__ import annotations

import hashlib
import re
import time
import urllib.parse as _up
from datetime import datetime, timezone
from html import escape

_UID_RE = re.compile(r"\d{3,20}")
_SPACE_UID_RE = re.compile(
    r"space\.bilibili\.com/(\d{3,20})", flags=re.IGNORECASE
)
_BVID_RE = re.compile(r"\b(BV[0-9A-Za-z]{10})\b")
_FACE_URL_RE = re.compile(
    r"(https?://[^\s)\]]*/bfs/face/[^\s)\]]+)", flags=re.IGNORECASE
)
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_RSSHUB_MIRRORS: list[str] = [
    "https://rsshub.rssforever.com",
    "https://rsshub.moeyy.cn",
    "https://rsshub-instance.zeabur.app",
    "https://rsshub.pseudoyu.com",
]


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


def _wbi_sign(
    params: dict[str, str], img_key: str, sub_key: str
) -> dict[str, str]:
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = str(int(time.time()))
    params = dict(sorted(params.items()))
    filtered = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in params.items()}
    query = _up.urlencode(filtered)
    params["w_rid"] = hashlib.md5(
        (query + mixin_key).encode()
    ).hexdigest()
    return params


def _extract_uid(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if candidate.lower().startswith("bilibili:"):
        candidate = candidate.split(":", 1)[1].strip()
    space_match = _SPACE_UID_RE.search(candidate)
    if space_match:
        return space_match.group(1)
    first_digits = _UID_RE.search(candidate)
    return first_digits.group(0) if first_digits else ""


def _to_datetime(value: object) -> datetime:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _build_preview_html(
    *, title: str, description: str, link: str, cover_url: str | None
) -> str:
    title_safe = escape((title or "").strip() or "B站更新")
    description_safe = escape((description or "").strip())
    link_safe = escape((link or "").strip(), quote=True)
    cover_safe = (
        escape((cover_url or "").strip(), quote=True) if cover_url else ""
    )
    parts = [
        '<article class="md-link-preview">',
        f'<meta property="og:title" content="{title_safe}" />',
        f'<meta property="og:description" content="{description_safe}" />',
        f'<meta property="og:url" content="{link_safe}" />',
    ]
    if cover_safe:
        parts.append(f'<meta property="og:image" content="{cover_safe}" />')
        parts.append(f'<img src="{cover_safe}" alt="{title_safe}" />')
    parts.append(f"<h3>{title_safe}</h3>")
    if description_safe:
        parts.append(f"<p>{description_safe}</p>")
    parts.append(
        '<p><a href="'
        + link_safe
        + '" target="_blank" rel="noopener noreferrer">查看视频</a></p>'
    )
    parts.append("</article>")
    return "".join(parts)


def _unique_bvids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result
