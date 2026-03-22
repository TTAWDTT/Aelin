from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse

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

    def _search_duckduckgo_lite(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        url = "https://lite.duckduckgo.com/lite/"
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url, params={"q": query})
            if resp.status_code != 200:
                return []
            html_text = resp.text or ""
            if _looks_blocked_page(html_text):
                return []
        except Exception:
            return []

        rows: list[WebSearchResult] = []
        matches = list(
            re.finditer(
                r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
                html_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )
        for m in matches:
            raw_href = unescape(m.group("href") or "").strip()
            title = _clean(unescape(m.group("title") or ""), limit=180)
            if not raw_href or not title:
                continue
            href = _decode_duckduckgo_redirect(raw_href)
            href = _normalize_url(href)
            if not href:
                continue
            tail = html_text[m.end() : m.end() + 800]
            snippet_match = re.search(r"<td[^>]*>(.*?)</td>", tail, flags=re.IGNORECASE | re.DOTALL)
            snippet_raw = snippet_match.group(1) if snippet_match else ""
            snippet = _clean(unescape(snippet_raw), limit=320)
            if not snippet:
                snippet = f"source: {_extract_domain(href)}"
            rows.append(WebSearchResult(title=title, url=href, snippet=snippet, provider="duckduckgo_lite"))
            if len(rows) >= max_results:
                break
        return rows

    def _search_duckduckgo_instant(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 0,
            "t": "aelin",
        }
        try:
            with self._new_http_client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        rows: list[WebSearchResult] = []
        abstract = _clean(str(data.get("AbstractText") or ""), limit=320)
        abstract_url = _normalize_url(str(data.get("AbstractURL") or "").strip())
        heading = _clean(str(data.get("Heading") or ""), limit=180)
        if abstract and abstract_url:
            rows.append(
                WebSearchResult(
                    title=heading or "DuckDuckGo",
                    url=abstract_url,
                    snippet=abstract,
                    provider="duckduckgo_instant",
                )
            )

        def _walk_related(items: list[Any]) -> None:
            for item in items:
                if len(rows) >= max_results:
                    return
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("Topics"), list):
                    _walk_related(item["Topics"])
                    continue
                text = _clean(str(item.get("Text") or ""), limit=260)
                first_url = _normalize_url(str(item.get("FirstURL") or "").strip())
                if not text or not first_url:
                    continue
                title = text.split(" - ", 1)[0].strip() or _extract_domain(first_url)
                rows.append(
                    WebSearchResult(
                        title=_clean(title, 160),
                        url=first_url,
                        snippet=text,
                        provider="duckduckgo_instant",
                    )
                )

        _walk_related(list(data.get("RelatedTopics") or []))
        return rows[:max_results]

    def _search_bing_html(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        encoded = quote(query.strip())
        url = f"https://www.bing.com/search?q={encoded}&setlang=en-us&mkt=en-US"
        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.8"}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
            if resp.status_code != 200:
                return []
            html_text = resp.text or ""
            if _looks_blocked_page(html_text):
                return []
        except Exception:
            return []

        rows: list[WebSearchResult] = []
        blocks = re.findall(
            r"<li[^>]+class=\"[^\"]*b_algo[^\"]*\"[^>]*>([\s\S]*?)</li>",
            html_text,
            flags=re.I,
        )
        for block in blocks:
            link_match = re.search(
                r"<h2[^>]*>\s*<a[^>]+href=\"(?P<href>[^\"]+)\"[^>]*>(?P<title>[\s\S]*?)</a>",
                block,
                flags=re.I,
            )
            if not link_match:
                continue
            href = _normalize_url(unescape(link_match.group("href") or "").strip())
            title = _clean(unescape(link_match.group("title") or ""), limit=180)
            if not href or not title:
                continue
            snippet_match = re.search(r"<p[^>]*>([\s\S]*?)</p>", block, flags=re.I)
            snippet = _clean(unescape(snippet_match.group(1) if snippet_match else ""), limit=320)
            if not snippet:
                snippet = f"source: {_extract_domain(href)}"
            rows.append(WebSearchResult(title=title, url=href, snippet=snippet, provider="bing_html"))
            if len(rows) >= max_results:
                break
        return rows

    def _search_wikipedia(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        is_cjk = _contains_cjk(query)
        base = "https://zh.wikipedia.org/w/api.php" if is_cjk else "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": 1,
            "format": "json",
            "srlimit": max(1, min(15, max_results)),
        }
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(base, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        search_rows = list((data.get("query") or {}).get("search") or [])
        rows: list[WebSearchResult] = []
        for item in search_rows[:max_results]:
            title = _clean(str(item.get("title") or ""), limit=180)
            snippet_html = str(item.get("snippet") or "")
            snippet = _clean(unescape(re.sub(r"<[^>]+>", " ", snippet_html)), limit=320)
            if not title:
                continue
            page_url = (
                f"https://zh.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                if is_cjk
                else f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            )
            rows.append(WebSearchResult(title=title, url=page_url, snippet=snippet, provider="wikipedia"))
        return rows

    def _search_google_news_rss(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        url = "https://news.google.com/rss/search"
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url, params=params)
            if resp.status_code != 200:
                return []
            xml_text = resp.text or ""
        except Exception:
            return []

        rows: list[WebSearchResult] = []
        items = re.findall(r"<item>([\s\S]*?)</item>", xml_text, flags=re.I)
        for raw in items[: max_results * 2]:
            title_match = re.search(r"<title>([\s\S]*?)</title>", raw, flags=re.I)
            link_match = re.search(r"<link>([\s\S]*?)</link>", raw, flags=re.I)
            desc_match = re.search(r"<description>([\s\S]*?)</description>", raw, flags=re.I)
            title = _clean(unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", str(title_match.group(1) if title_match else ""))), limit=180)
            href = _normalize_url(unescape(str(link_match.group(1) if link_match else "")).strip())
            desc = str(desc_match.group(1) if desc_match else "")
            snippet = _clean(unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", re.sub(r"<[^>]+>", " ", desc))), limit=320)
            if not title or not href:
                continue
            rows.append(WebSearchResult(title=title, url=href, snippet=snippet, provider="google_news_rss"))
            if len(rows) >= max_results:
                break
        return rows

    def _search_reddit_json(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        url = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": "new", "limit": max(3, min(25, max_results * 2))}
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        children = list((((data.get("data") or {}).get("children")) or []))
        rows: list[WebSearchResult] = []
        for child in children:
            node = child.get("data") if isinstance(child, dict) else None
            if not isinstance(node, dict):
                continue
            title = _clean(str(node.get("title") or ""), limit=180)
            permalink = str(node.get("permalink") or "").strip()
            outbound = _normalize_url(str(node.get("url") or "").strip())
            post_url = _normalize_url(f"https://www.reddit.com{permalink}") if permalink else ""
            href = outbound or post_url
            snippet = _clean(str(node.get("selftext") or ""), limit=320)
            if not snippet:
                snippet = f"subreddit: r/{str(node.get('subreddit') or '').strip()}".strip()
            if not title or not href:
                continue
            rows.append(WebSearchResult(title=title, url=href, snippet=snippet, provider="reddit_json"))
            if len(rows) >= max_results:
                break
        return rows

    def _search_hn_algolia(self, query: str, *, max_results: int) -> list[WebSearchResult]:
        url = "https://hn.algolia.com/api/v1/search_by_date"
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": max(3, min(20, max_results * 2)),
        }
        headers = {"User-Agent": _USER_AGENT}
        try:
            with self._new_http_client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                resp = client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        rows: list[WebSearchResult] = []
        for hit in list(data.get("hits") or []):
            if not isinstance(hit, dict):
                continue
            title = _clean(str(hit.get("title") or hit.get("story_title") or ""), limit=180)
            href = _normalize_url(str(hit.get("url") or hit.get("story_url") or "").strip())
            if not href:
                object_id = str(hit.get("objectID") or "").strip()
                if object_id:
                    href = f"https://news.ycombinator.com/item?id={object_id}"
            snippet = _clean(str(hit.get("story_text") or ""), limit=320)
            if not snippet:
                snippet = f"author: {str(hit.get('author') or '').strip()}".strip()
            if not title or not href:
                continue
            rows.append(WebSearchResult(title=title, url=href, snippet=snippet, provider="hn_algolia"))
            if len(rows) >= max_results:
                break
        return rows
