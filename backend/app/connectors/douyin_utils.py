from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape

_SEC_UID_RE = re.compile(r"sec_uid=([A-Za-z0-9_-]+)")
_USER_ID_RE = re.compile(r"user/([A-Za-z0-9_-]+)")

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_RSSHUB_MIRRORS: list[str] = [
    "https://rsshub.rssforever.com",
    "https://rsshub.moeyy.cn",
    "https://rsshub-instance.zeabur.app",
    "https://rsshub.pseudoyu.com",
]

_POST_API_PATTERN = "/aweme/v1/web/aweme/post/"


def _extract_sec_uid(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""

    if candidate.lower().startswith("douyin:"):
        candidate = candidate.split(":", 1)[1].strip()

    sec_uid_match = _SEC_UID_RE.search(candidate)
    if sec_uid_match:
        return sec_uid_match.group(1)

    user_match = _USER_ID_RE.search(candidate)
    if user_match:
        return user_match.group(1)

    return candidate


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
    title_safe = escape((title or "").strip() or "抖音更新")
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
