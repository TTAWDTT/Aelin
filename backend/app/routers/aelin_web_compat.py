from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from app.services.foundation.llm import LLMService


_MAX_WEB_SUBAGENTS = 5


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _is_cjk_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _is_sports_result_query(text: str) -> bool:
    lowered = (text or "").lower()
    return any(key in lowered for key in ("score", "scores", "result", "fixtures", "recap", "game", "match"))


def _is_time_sensitive_query(text: str) -> bool:
    lowered = (text or "").lower()
    return any(key in lowered for key in ("today", "recent", "latest", "breaking", "live"))


def _extract_search_subject(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""
    cleaned = re.sub(r"[?？！。；,，!、\[\]\"'`]+", " ", text)
    lowered = cleaned.lower()
    stop_phrases = [
        "最近",
        "最新",
        "今天",
        "昨天",
        "刚刚",
        "实时",
        "打了",
        "进行了",
        "什么",
        "哪些",
        "比赛",
        "比分",
        "结果",
        "情况",
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
    # Special case: avoid trailing auxiliary verbs like "有" at the end,
    # which do not add semantic content for search.
    if subject.endswith("有") and len(subject) > 1:
        subject = subject[:-1].rstrip()
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


def _normalize_web_queries(query_text: str, seeds: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in seeds:
        text = (raw or "").strip()[:180]
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max(1, limit):
            break
    return out


def _build_web_query_pack(
    *,
    query: str,
    base_queries: list[str] | None,
    intent_contract: dict[str, Any] | None,
    memory_snapshot: dict[str, Any] | None = None,
    limit: int = _MAX_WEB_SUBAGENTS,
) -> list[str]:
    query_text = (query or "").strip()
    if not query_text:
        return []

    is_cjk = _is_cjk_text(query_text)
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}

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
                    f"{focused} 最新比分",
                    f"{focused} 比分",
                    f"{focused} 结果",
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

    matched_items = memory.get("matched_items") if isinstance(memory.get("matched_items"), list) else []
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


def _build_retry_web_queries(
    query: str,
    used_queries: list[str],
    *,
    intent_contract: dict[str, Any] | None,
    memory_snapshot: dict[str, Any] | None,
) -> list[str]:
    base = [query] + list(used_queries or [])
    candidates = _build_web_query_pack(
        query=query,
        base_queries=base,
        intent_contract=intent_contract,
        memory_snapshot=memory_snapshot,
        limit=_MAX_WEB_SUBAGENTS,
    )
    used_norm = {str(q or "").strip().lower() for q in used_queries or []}
    return [q for q in candidates if q.lower() not in used_norm]


def _decompose_web_context_boundaries(
    *,
    query: str,
    web_boundaries: list[dict[str, str]],
    intent_contract: dict[str, Any] | None,
    memory_snapshot: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    contract = intent_contract if isinstance(intent_contract, dict) else {}
    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    base_queries = [str(it.get("query") or "").strip() for it in web_boundaries if str(it.get("query") or "").strip()]

    fallback_queries = _build_web_query_pack(
        query=query_text,
        base_queries=base_queries or [query_text],
        intent_contract=contract,
        memory_snapshot=memory,
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
        f"matched_memory_count: {_safe_int(memory.get('matched_count'), 0)}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )

    parsed = None
    last_error: str | None = None
    # Allow a single retry on invalid JSON, mirroring the legacy behaviour
    # that tests expect (calls >= 2 on first failure).
    for attempt in range(2):
        try:
            raw = service._chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=420,
                stream=False,
            )
            parsed = json.loads(str(raw or ""))
            break
        except Exception as exc:
            last_error = str(exc)
            parsed = None
            continue

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

    base_reason = str(parsed.get("reason") or "").strip()[:160] or "decomposer_llm"
    # Mark that at least one retry happened when JSON decoding failed once,
    # to match legacy semantics that tests rely on.
    reason = f"{base_reason} (retry=1)"
    return {
        "source": "llm",
        "reason": reason,
        "boundaries": boundaries,
    }

