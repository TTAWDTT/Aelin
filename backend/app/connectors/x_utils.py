from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from html import escape, unescape
from typing import Any

from app.services.avatar import normalize_http_avatar_url


class _RateLimitError(Exception):
    """429 限流专用异常，上层策略链据此决定是否跳过低质量回退。"""


_X_API_BASE_URL = "https://api.x.com/2"
_X_API_RATE_LIMIT_WINDOW = 900  # 15 分钟窗口

_NITTER_INSTANCES = [
    "https://nitter.uni-sonia.com",
    "https://nitter.moomoo.me",
    "https://nitter.soopy.moe",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.lucabased.xyz",
    "https://nitter.net",
]

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_MAIN_JS_RE = re.compile(r"https://abs\.twimg\.com/responsive-web/client-web/main\.[^\"'<>]+\.js")
_GUEST_TOKEN_RE = re.compile(r'document\.cookie="gt=(\d+);')
_BEARER_TOKEN_RE = re.compile(r"AAAAA[0-9A-Za-z%]{60,}")
_TWITTER_DATETIME_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def _normalize_username(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if candidate.lower().startswith("x:"):
        candidate = candidate[2:]
    if "://" in candidate or "x.com/" in candidate.lower() or "twitter.com/" in candidate.lower():
        parsed = urllib.parse.urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = (parsed.netloc or "").lower().strip()
        parts = [part for part in (parsed.path or "").split("/") if part]
        if host.endswith("x.com") or host.endswith("twitter.com"):
            candidate = parts[0] if parts else candidate
        elif len(parts) >= 3 and parts[0] in {"x", "twitter"} and parts[1] == "user":
            candidate = parts[2]
        elif len(parts) >= 2 and parts[-1].lower() == "rss":
            candidate = parts[-2]
        elif parts:
            candidate = parts[0]
    candidate = candidate.lstrip("@").strip()
    if not candidate:
        return ""
    matched = re.search(r"[A-Za-z0-9_]{1,15}", candidate)
    return matched.group(0) if matched else candidate


def _parse_string_array(value: str) -> list[str]:
    return [matched.strip() for matched in re.findall(r'"([^"]+)"', value or "") if matched.strip()]


def _extract_operation_spec(bundle: str, operation_name: str) -> tuple[str, list[str], list[str]]:
    pattern = re.compile(
        rf'queryId:"(?P<query_id>[A-Za-z0-9_-]{{20,}})",operationName:"{re.escape(operation_name)}".*?metadata:\{{(?P<meta>[^}}]*)\}}',
        re.S,
    )
    matched = pattern.search(bundle)
    if not matched:
        raise ValueError(f"未能从 X 前端脚本解析 {operation_name} queryId")

    meta = matched.group("meta")
    feature_match = re.search(r"featureSwitches:\[(?P<items>[^\]]*)\]", meta, re.S)
    field_match = re.search(r"fieldToggles:\[(?P<items>[^\]]*)\]", meta, re.S)
    features = _parse_string_array(feature_match.group("items")) if feature_match else []
    field_toggles = _parse_string_array(field_match.group("items")) if field_match else []
    return matched.group("query_id"), features, field_toggles


def _parse_x_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, _TWITTER_DATETIME_FORMAT).astimezone(timezone.utc)
    except ValueError:
        return None


def _snowflake_datetime_from_id(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text.isdigit():
        return None
    try:
        timestamp_ms = (int(text) >> 22) + 1288834974657
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except Exception:
        return None


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", unescape(value or "")).strip()
    return normalized


def _unwrap_tweet_result(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    typename = str(value.get("__typename") or "").strip()
    if typename == "TweetWithVisibilityResults":
        nested = value.get("tweet")
        if isinstance(nested, dict):
            return nested
        return None
    if typename and typename not in {"Tweet", "TweetTombstone"}:
        return None
    return value


def _iter_item_contents(entry: dict[str, Any]) -> list[dict[str, Any]]:
    content = entry.get("content")
    if not isinstance(content, dict):
        return []
    result: list[dict[str, Any]] = []
    item_content = content.get("itemContent")
    if isinstance(item_content, dict):
        result.append(item_content)
    for module_item in content.get("items") or []:
        if not isinstance(module_item, dict):
            continue
        item = module_item.get("item")
        if not isinstance(item, dict):
            continue
        module_content = item.get("itemContent")
        if isinstance(module_content, dict):
            result.append(module_content)
    return result


def _extract_timeline_entries(instructions: object) -> list[dict[str, Any]]:
    if not isinstance(instructions, list):
        return []
    entries: list[dict[str, Any]] = []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        single_entry = instruction.get("entry")
        if isinstance(single_entry, dict):
            entries.append(single_entry)
        listed_entries = instruction.get("entries")
        if isinstance(listed_entries, list):
            entries.extend([entry for entry in listed_entries if isinstance(entry, dict)])
    return entries


def _extract_bottom_cursor(entries: list[dict[str, Any]]) -> str | None:
    for entry in entries:
        entry_id = str(entry.get("entryId") or "").strip().lower()
        if not entry_id.startswith("cursor-bottom"):
            continue
        content = entry.get("content")
        if not isinstance(content, dict):
            continue
        value = str(content.get("value") or "").strip()
        if value:
            return value
    return None


def _extract_first_image_url(legacy: dict[str, Any]) -> str | None:
    media_lists: list[object] = []
    extended_entities = legacy.get("extended_entities")
    if isinstance(extended_entities, dict):
        media_lists.append(extended_entities.get("media"))
    entities = legacy.get("entities")
    if isinstance(entities, dict):
        media_lists.append(entities.get("media"))

    for media_list in media_lists:
        if not isinstance(media_list, list):
            continue
        for media in media_list:
            if not isinstance(media, dict):
                continue
            url = (
                str(media.get("media_url_https") or "").strip()
                or str(media.get("media_url") or "").strip()
            )
            if url.startswith("http://") or url.startswith("https://"):
                return url
    return None


def _expand_urls(text: str, entities: object) -> str:
    normalized = text or ""
    if not isinstance(entities, dict):
        return _normalize_text(normalized)

    for item in entities.get("urls") or []:
        if not isinstance(item, dict):
            continue
        short_url = str(item.get("url") or "").strip()
        expanded_url = str(item.get("expanded_url") or item.get("display_url") or "").strip()
        if short_url and expanded_url:
            normalized = normalized.replace(short_url, expanded_url)

    for item in entities.get("media") or []:
        if not isinstance(item, dict):
            continue
        short_url = str(item.get("url") or "").strip()
        if short_url:
            normalized = normalized.replace(short_url, "")

    return _normalize_text(normalized)


def _build_preview_body(*, title: str, description: str, link: str, preview_image: str | None) -> str:
    title_safe = escape((title or "").strip() or "X 更新")
    description_safe = escape((description or "").strip())
    link_safe = escape((link or "").strip(), quote=True)
    image_safe = escape((preview_image or "").strip(), quote=True) if preview_image else ""

    parts = [
        '<article class="md-link-preview">',
        f'<meta property="og:title" content="{title_safe}" />',
        f'<meta property="og:description" content="{description_safe}" />',
        f'<meta property="og:url" content="{link_safe}" />',
    ]
    if image_safe:
        parts.append(f'<meta property="og:image" content="{image_safe}" />')
        parts.append(f'<img src="{image_safe}" alt="{title_safe}" />')
    parts.append(f"<h3>{title_safe}</h3>")
    if description_safe:
        parts.append(f"<p>{description_safe}</p>")
    parts.append(
        '<p><a href="'
        + link_safe
        + '" target="_blank" rel="noopener noreferrer">查看原帖</a></p>'
    )
    parts.append("</article>")
    return "".join(parts)


def _extract_user_avatar_url(user: dict[str, Any], user_legacy: dict[str, Any]) -> str | None:
    avatar_obj = user.get("avatar")
    if isinstance(avatar_obj, dict):
        normalized = normalize_http_avatar_url(avatar_obj.get("image_url"))
        if normalized:
            return normalized
    for key in ("profile_image_url_https", "profile_image_url"):
        normalized = normalize_http_avatar_url(user_legacy.get(key))
        if normalized:
            return normalized
    return None
