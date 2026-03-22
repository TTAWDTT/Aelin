from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import httpx

_LOG = logging.getLogger(__name__)

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
_JS_REQUIRED_SIGNALS = (
    "enable javascript",
    "javascript is required",
    "please turn javascript on",
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


def _looks_recent(text: str) -> bool:
    src = (text or "").lower()
    if not src:
        return False
    if any(token in src for token in ("latest", "today", "recent", "breaking", "updated", "live")):
        return True
    if re.search(r"\b20\d{2}\b", src):
        return True
    return False


def _looks_blocked_page(text: str) -> bool:
    src = (text or "").lower()
    return any(sig in src for sig in _BLOCK_SIGNALS)


def _looks_js_required(text: str) -> bool:
    src = (text or "").lower()
    return any(sig in src for sig in _JS_REQUIRED_SIGNALS)


def _tokenize(text: str) -> list[str]:
    src = (text or "").lower()
    parts = re.split(r"[^a-z0-9\u4e00-\u9fff]+", src)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = part.strip()
        if len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= 16:
            break
    return out


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str = "web"
    fetched_excerpt: str = ""
    provider: str = "unknown"
    fetch_mode: str = "none"
    rank: int = 0
    fetched_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class WebSearchService:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_parallel_providers: int = 6,
        max_parallel_fetch: int = 4,
        enable_reader_fallback: bool = True,
        enable_browser_fallback: bool = True,
        proxy_url: str = "",
    ):
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self.max_parallel_providers = max(1, min(6, int(max_parallel_providers)))
        self.max_parallel_fetch = max(1, min(8, int(max_parallel_fetch)))
        self.enable_reader_fallback = bool(enable_reader_fallback)
        self.enable_browser_fallback = bool(enable_browser_fallback)
        self.proxy_url = str(proxy_url or "").strip()
        self._browser_ready: bool | None = None

    def _new_http_client(
        self,
        *,
        timeout: float | None = None,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": timeout if timeout is not None else self.timeout_seconds,
            "follow_redirects": follow_redirects,
        }
        if headers:
            kwargs["headers"] = headers
        if self.proxy_url and self.proxy_url.lower() != "off":
            kwargs["proxy"] = self.proxy_url
        try:
            return httpx.Client(**kwargs)
        except TypeError:
            proxy = kwargs.pop("proxy", None)
            if proxy:
                kwargs["proxies"] = proxy
            return httpx.Client(**kwargs)

    def search(self, query: str, *, max_results: int = 15) -> list[WebSearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        n = max(1, min(15, int(max_results or 6)))
        rows = self._search_with_ensemble(q, max_results=n)
        if not rows:
            return []
        return rows[:n]

    def fetch_page_excerpt(self, url: str, *, max_chars: int = 1800) -> tuple[str, str]:
        title, excerpt, _ = self._fetch_page_excerpt_best(url, max_chars=max_chars)
        return title, excerpt

    def search_and_fetch(
        self,
        query: str,
        *,
        max_results: int = 15,
        fetch_top_k: int = 3,
    ) -> list[WebSearchResult]:
        rows = self.search(query, max_results=max_results)
        if not rows:
            return []

        top_k = max(0, min(len(rows), int(fetch_top_k or 0)))
        if top_k <= 0:
            return rows

        indexed: list[tuple[int, WebSearchResult]] = list(enumerate(rows[:top_k]))
        max_workers = max(1, min(top_k, self.max_parallel_fetch))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._fetch_page_excerpt_best, row.url, max_chars=1800): (idx, row)
                for idx, row in indexed
            }
            for fut in as_completed(futures):
                idx, row = futures[fut]
                try:
                    page_title, excerpt, mode = fut.result()
                except Exception:
                    page_title, excerpt, mode = "", "", "error"
                if page_title and len((row.title or "").strip()) < 8:
                    row.title = page_title
                if excerpt:
                    row.fetched_excerpt = excerpt
                    if not row.snippet or len(row.snippet.strip()) < 40:
                        row.snippet = _clean(excerpt, limit=320)
                row.fetch_mode = mode
                row.fetched_at = datetime.now(timezone.utc).isoformat()
                rows[idx] = row
        return rows

    def _search_with_ensemble(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        from app.services import web_search_providers as providers_mod

        providers: list[tuple[str, Any]] = [
            ("bing_html", providers_mod.search_bing_html),
            ("duckduckgo_lite", providers_mod.search_duckduckgo_lite),
            ("duckduckgo_instant", providers_mod.search_duckduckgo_instant),
            ("google_news_rss", providers_mod.search_google_news_rss),
            ("reddit_json", providers_mod.search_reddit_json),
            ("hn_algolia", providers_mod.search_hn_algolia),
            ("wikipedia", providers_mod.search_wikipedia),
        ]

        rows_with_score: list[tuple[float, WebSearchResult]] = []
        query_tokens = _tokenize(query)
        per_provider_limit = max(3, min(15, max_results + 3))

        with ThreadPoolExecutor(max_workers=min(len(providers), self.max_parallel_providers)) as pool:
            # Each provider receives a short‑lived HTTP client configured via
            # the shared _new_http_client helper so proxy/timeout settings are
            # consistently applied.
            futures = {}
            for idx, (provider_name, fn) in enumerate(providers):
                client = self._new_http_client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": _USER_AGENT},
                )
                futures[pool.submit(fn, query, max_results=per_provider_limit, client=client)] = (provider_name, idx, client)
            for fut in as_completed(futures):
                provider_name, provider_index, client = futures[fut]
                try:
                    provider_rows = fut.result() or []
                except Exception as exc:
                    _LOG.debug("web provider %s failed: %s", provider_name, exc)
                    provider_rows = []
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass
                for rank_in_provider, row in enumerate(provider_rows, start=1):
                    if not isinstance(row, WebSearchResult):
                        continue
                    clean_url = _normalize_url(row.url)
                    if not clean_url:
                        continue
                    row.url = clean_url
                    row.provider = provider_name
                    row.source = "web"
                    row.rank = rank_in_provider
                    score = self._score_result(
                        row,
                        query_tokens=query_tokens,
                        provider_index=provider_index,
                        rank_in_provider=rank_in_provider,
                    )
                    rows_with_score.append((score, row))

        if not rows_with_score:
            return []

        rows_with_score.sort(key=lambda it: it[0], reverse=True)
        dedup: dict[str, WebSearchResult] = {}
        for _, row in rows_with_score:
            key = (row.url or "").strip().lower() or (row.title or "").strip().lower()
            if not key or key in dedup:
                continue
            dedup[key] = row
            if len(dedup) >= max_results:
                break
        out = list(dedup.values())[:max_results]
        for idx, row in enumerate(out, start=1):
            row.rank = idx
        return out

    def _score_result(
        self,
        row: WebSearchResult,
        *,
        query_tokens: list[str],
        provider_index: int,
        rank_in_provider: int,
    ) -> float:
        provider_boost = {
            "bing_html": 4.0,
            "duckduckgo_lite": 3.5,
            "duckduckgo_instant": 2.0,
            "google_news_rss": 3.2,
            "reddit_json": 2.8,
            "hn_algolia": 2.6,
            "wikipedia": 1.0,
        }
        score = 80.0
        score += provider_boost.get(row.provider, 0.0)
        score -= float(provider_index) * 1.0
        score -= float(rank_in_provider) * 1.2

        blob = f"{row.title} {row.snippet}".lower()
        token_hits = 0
        for token in query_tokens:
            if token and token in blob:
                token_hits += 1
        score += min(10.0, float(token_hits) * 2.0)
        if _looks_recent(blob):
            score += 2.5
        if len((row.snippet or "").strip()) >= 80:
            score += 1.2
        if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", blob):
            score += 0.8
        return score

    def _fetch_page_excerpt_best(self, url: str, *, max_chars: int = 1800) -> tuple[str, str, str]:
        clean_url = (url or "").strip()
        if not clean_url.startswith(("http://", "https://")):
            return "", "", "invalid_url"

        title, excerpt, meta = self._fetch_page_excerpt_http(clean_url, max_chars=max_chars)
        blocked = bool(meta.get("blocked"))
        js_required = bool(meta.get("js_required"))

        if self._excerpt_is_good(excerpt):
            return title, excerpt, "http"

        if self.enable_reader_fallback and (not blocked):
            title_reader, excerpt_reader = self._fetch_page_excerpt_reader(clean_url, max_chars=max_chars)
            if self._excerpt_is_good(excerpt_reader):
                return title_reader or title, excerpt_reader, "reader"

        if self.enable_browser_fallback and (blocked or js_required or not self._excerpt_is_good(excerpt)):
            title_browser, excerpt_browser = self._fetch_page_excerpt_browser(clean_url, max_chars=max_chars)
            if self._excerpt_is_good(excerpt_browser):
                return title_browser or title, excerpt_browser, "browser"

        if self.enable_reader_fallback and (blocked or js_required):
            title_reader, excerpt_reader = self._fetch_page_excerpt_reader(clean_url, max_chars=max_chars)
            if self._excerpt_is_good(excerpt_reader):
                return title_reader or title, excerpt_reader, "reader"

        return title, excerpt, "http"

    def _excerpt_is_good(self, excerpt: str) -> bool:
        text = (excerpt or "").strip()
        if len(text) < 120:
            return False
        if _looks_blocked_page(text):
            return False
        return True

    def _fetch_page_excerpt_http(self, url: str, *, max_chars: int) -> tuple[str, str, dict[str, Any]]:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                return "", "", {"status_code": resp.status_code}
            content_type = str(resp.headers.get("content-type") or "").lower()
            body = resp.text or ""
        except Exception:
            return "", "", {"status_code": 0}

        title = ""
        excerpt = ""
        if "html" in content_type or "<html" in body.lower():
            title, excerpt = self._extract_html_excerpt(body, max_chars=max_chars)
        elif "text/plain" in content_type:
            excerpt = _clean(body, limit=max_chars)
        else:
            excerpt = _clean(_strip_html(body), limit=max_chars)

        meta = {
            "status_code": int(resp.status_code),
            "blocked": _looks_blocked_page(body),
            "js_required": _looks_js_required(body),
            "content_type": content_type,
        }
        return title, excerpt, meta

    def _extract_html_excerpt(self, body: str, *, max_chars: int) -> tuple[str, str]:
        m = re.search(r"<title[^>]*>([\s\S]*?)</title>", body, flags=re.I)
        title = _clean(unescape(m.group(1)) if m else "", limit=180)
        blocks = re.findall(
            r"<(?:article|main|section|p|li|h1|h2|h3|blockquote|td)[^>]*>([\s\S]*?)</(?:article|main|section|p|li|h1|h2|h3|blockquote|td)>",
            body,
            flags=re.I,
        )
        segments: list[str] = []
        seen: set[str] = set()
        for raw in blocks:
            item = _clean(unescape(re.sub(r"<[^>]+>", " ", raw)), limit=420)
            if len(item) < 30:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            segments.append(item)
            if len(segments) >= 28:
                break
        joined = " ".join(segments).strip()
        excerpt = _clean(joined, limit=max_chars) if joined else _clean(_strip_html(body), limit=max_chars)
        return title, excerpt

    def _fetch_page_excerpt_reader(self, url: str, *, max_chars: int) -> tuple[str, str]:
        reader_url = f"https://r.jina.ai/http://{url}"
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=max(8.0, self.timeout_seconds), follow_redirects=True, headers=headers) as client:
                resp = client.get(reader_url)
            if resp.status_code >= 400:
                return "", ""
            text = (resp.text or "").strip()
        except Exception:
            return "", ""

        if not text:
            return "", ""

        title = ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[:8]:
            if line.lower().startswith("title:"):
                title = _clean(line.split(":", 1)[1], limit=180)
                break
        excerpt = _clean(text, limit=max_chars)
        return title, excerpt

    def _fetch_page_excerpt_browser(self, url: str, *, max_chars: int) -> tuple[str, str]:
        if not self.enable_browser_fallback:
            return "", ""
        if self._browser_ready is False:
            return "", ""

        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self._browser_ready = False
            return "", ""

        title = ""
        excerpt = ""
        timeout_ms = int(max(8.0, self.timeout_seconds) * 1000)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=2500)
                except Exception:
                    pass
                title = _clean(page.title() or "", limit=180)
                extracted = page.evaluate(
                    """() => {
                        const selectors = ["article","main","section","p","li","h1","h2","h3","blockquote","td"];
                        const out = [];
                        const seen = new Set();
                        for (const sel of selectors) {
                          const nodes = document.querySelectorAll(sel);
                          for (const node of nodes) {
                            const text = (node && node.innerText ? node.innerText : "").replace(/\\s+/g, " ").trim();
                            if (!text || text.length < 30) continue;
                            const key = text.slice(0, 160).toLowerCase();
                            if (seen.has(key)) continue;
                            seen.add(key);
                            out.push(text);
                            if (out.length >= 40) break;
                          }
                          if (out.length >= 40) break;
                        }
                        if (!out.length) {
                          const body = (document.body && document.body.innerText ? document.body.innerText : "").replace(/\\s+/g, " ").trim();
                          if (body) out.push(body);
                        }
                        return out.join(" ");
                    }"""
                )
                excerpt = _clean(str(extracted or ""), limit=max_chars)
                # Optional AX tree via CDP. page.accessibility is removed in modern Playwright.
                if not excerpt:
                    try:
                        session = context.new_cdp_session(page)
                        ax_tree = session.send("Accessibility.getFullAXTree")
                        names: list[str] = []
                        for node in list(ax_tree.get("nodes") or [])[:200]:
                            role = str(((node.get("role") or {}).get("value") or "")).strip().lower()
                            name = str(((node.get("name") or {}).get("value") or "")).strip()
                            if not name:
                                continue
                            if role in {"text", "statictext", "paragraph", "heading", "link", "button"}:
                                names.append(name)
                            if len(names) >= 80:
                                break
                        excerpt = _clean(" ".join(names), limit=max_chars)
                    except Exception:
                        pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
            self._browser_ready = True
            if self._excerpt_is_good(excerpt):
                return title, excerpt
            return "", ""
        except Exception as exc:
            msg = str(exc or "")
            if "Executable doesn't exist" in msg or "browserType.launch" in msg:
                self._browser_ready = False
            _LOG.debug("browser fallback failed: %s", exc)
            return "", ""
