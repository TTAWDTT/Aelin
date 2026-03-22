from __future__ import annotations

from html import unescape
import re
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
_BLOCK_SIGNALS = (
    "captcha",
    "verify you are human",
    "unusual traffic",
    "anomaly",
    "are you a robot",
    "access denied",
    "bot check",
    "challenge",
)


def _clean(text: str, limit: int = 500) -> str:
    stripped = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: max(0, limit - 3)].rstrip() + "..."


def _strip_html(text: str) -> str:
    no_script = re.sub(r"<(script|style|noscript|svg|iframe)[^>]*>[\s\S]*?</\1>", " ", text or "", flags=re.I)
    no_comment = re.sub(r"<!--[\s\S]*?-->", " ", no_script)
    plain = re.sub(r"<[^>]+>", " ", no_comment)
    return _clean(unescape(plain), limit=20_000)


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().strip()
        return host or "web"
    except Exception:
        return "web"


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return ""
        query_parts = []
        for pair in (parsed.query or "").split("&"):
            if not pair:
                continue
            key = pair.split("=", 1)[0].strip().lower()
            if key.startswith("utm_") or key in {"gclid", "fbclid", "spm", "ref", "source"}:
                continue
            query_parts.append(pair)
        cleaned = parsed._replace(query="&".join(query_parts), fragment="")
        return urlunparse(cleaned)
    except Exception:
        return raw


def _decode_duckduckgo_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
            uddg = parse_qs(parsed.query).get("uddg", [])
            if uddg:
                return unquote(uddg[0])
    except Exception:
        return url
    return url


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _looks_blocked_page(text: str) -> bool:
    src = (text or "").lower()
    return any(sig in src for sig in _BLOCK_SIGNALS)


__all__ = [
    "_USER_AGENT",
    "_clean",
    "_strip_html",
    "_extract_domain",
    "_normalize_url",
    "_decode_duckduckgo_redirect",
    "_contains_cjk",
    "_looks_blocked_page",
]
