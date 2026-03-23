from __future__ import annotations

from html import unescape
import re
from typing import Any, Iterable
from urllib.parse import quote

import httpx
from app.services.web.web_search_common import (
    _clean,
    _contains_cjk,
    _decode_duckduckgo_redirect,
    _extract_domain,
    _looks_blocked_page,
    _normalize_url,
    _strip_html,
    _USER_AGENT,
)

from app.services.web.web_search import (
    WebSearchResult,
)


def search_duckduckgo_lite(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    url = "https://lite.duckduckgo.com/lite/"
    try:
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


def search_duckduckgo_instant(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 0,
        "t": "aelin",
    }
    try:
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

    def _walk_related(items: Iterable[Any]) -> None:
        for item in items:
            if len(rows) >= max_results:
                return
            if not isinstance(item, dict):
                continue
            first_url = _normalize_url(str(item.get("FirstURL") or "").strip())
            text = _clean(str(item.get("Text") or ""), limit=320)
            if not first_url or not text:
                continue
            rows.append(
                WebSearchResult(
                    title=_clean(str(item.get("Text") or ""), limit=180),
                    url=first_url,
                    snippet=text,
                    provider="duckduckgo_instant",
                )
            )

    _walk_related(list(data.get("RelatedTopics") or []))
    return rows[:max_results]


def search_bing_html(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    encoded = quote(query.strip())
    url = f"https://www.bing.com/search?q={encoded}&setlang=en-us&mkt=en-US"
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.8"}
    try:
        resp = client.get(url, headers=headers)
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


def search_wikipedia(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
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
        resp = client.get(base, params=params, headers=headers)
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


def search_google_news_rss(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    headers = {"User-Agent": _USER_AGENT}
    try:
        resp = client.get(url, params=params, headers=headers)
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


def search_reddit_json(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    url = "https://www.reddit.com/search.json"
    params = {"q": query, "sort": "new", "limit": max(3, min(25, max_results * 2))}
    headers = {"User-Agent": _USER_AGENT}
    try:
        resp = client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    children = list(((data.get("data") or {}).get("children")) or [])
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


def search_hn_algolia(
    query: str,
    *,
    max_results: int,
    client: httpx.Client,
) -> list[WebSearchResult]:
    url = "https://hn.algolia.com/api/v1/search_by_date"
    params = {
        "query": query,
        "tags": "story",
        "hitsPerPage": max(3, min(20, max_results * 2)),
    }
    headers = {"User-Agent": _USER_AGENT}
    try:
        resp = client.get(url, params=params, headers=headers)
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


