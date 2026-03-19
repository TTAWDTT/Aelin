from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas import AelinCitation
from app.services.aelin_chat_answering import _extract_score_clues, _looks_like_link_dump_answer
from app.services.llm import LLMService
from app.services.web_search import WebSearchResult

#
# Section: JSON parsing & low-level helpers
# ----------------------------------------
# These helpers are shared across intent planning, tool planning and web
# boundary decomposition. They do not perform any I/O and are intentionally
# tolerant of imperfect LLM outputs.
#

_MAX_WEB_SUBAGENTS = 5
_MAX_LOCAL_SUBAGENTS = 5
_MAX_CONTEXT_BOUNDARIES = 10

def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # Accept common fenced format: ```json { ... } ```
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None

def _parse_json_payload(raw: str) -> Any | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Accept fenced JSON payloads and both object/array roots.
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except Exception:
            continue
    return None

def _normalize_web_queries(query: str, items: Any, *, limit: int = _MAX_WEB_SUBAGENTS) -> list[str]:
    safe_limit = max(1, min(_MAX_WEB_SUBAGENTS, int(limit or _MAX_WEB_SUBAGENTS)))
    out: list[str] = []
    seen: set[str] = set()
    seen_sig: set[str] = set()

    def _query_sig(text: str) -> str:
        base = str(text or "").strip().lower()
        if not base:
            return ""
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", base)
        for phrase in (
            "latest",
            "recent",
            "today",
            "yesterday",
            "now",
            "current",
            "\u6700\u65b0",  # 最新
            "\u6700\u8fd1",  # 最近
            "\u4eca\u5929",  # 今天
            "\u6628\u5929",  # 昨天
            "\u524d\u5929",  # 前天
            "\u521a\u521a",  # 刚刚
            "\u5b9e\u65f6",  # 实时
            "\u76ee\u524d",  # 目前
            "\u6709\u4ec0\u4e48",  # 有什么
            "\u6709\u54ea\u4e9b",  # 有哪些
            "\u6709\u5565",  # 有啥
            "\u6709\u6ca1\u6709",  # 有没有
            "\u8bf7\u95ee",  # 请问
            "\u5e2e\u6211",  # 帮我
            "\u544a\u8bc9\u6211",  # 告诉我
        ):
            normalized = normalized.replace(phrase, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", normalized).strip()
        return normalized or base

    if isinstance(items, list):
        for it in items:
            text = str(it or "").strip()[:180]
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            sig = _query_sig(text)
            if sig and sig in seen_sig:
                continue
            seen.add(key)
            if sig:
                seen_sig.add(sig)
            out.append(text)
            if len(out) >= safe_limit:
                break
    if not out and query.strip():
        out.append(query.strip()[:180])
    return out[:safe_limit]

def _is_cjk_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


#
# Section: Web search subject & query pack builders
#

def _extract_search_subject_dynamic(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""

    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text)
    lowered = cleaned.lower()
    stop_phrases_cjk = [
        "\u6700\u8fd1",
        "\u6700\u65b0",
        "\u4eca\u5929",
        "\u6628\u5929",
        "\u524d\u5929",
        "\u521a\u521a",
        "\u5b9e\u65f6",
        "\u6253\u4e86",
        "\u6253\u4ec0\u4e48",
        "\u8fdb\u884c\u4e86",
        "\u6709\u4ec0\u4e48",
        "\u6709\u54ea\u4e9b",
        "\u6709\u5565",
        "\u6709\u6ca1\u6709",
        "\u6709\u5426",
        "\u4ec0\u4e48",
        "\u54ea\u4e9b",
        "\u51e0\u573a",
        "\u6bd4\u8d5b",
        "\u8d5b\u679c",
        "\u6bd4\u5206",
        "\u7ed3\u679c",
        "\u60c5\u51b5",
        "\u662f\u591a\u5c11",
        "\u591a\u5c11",
        "\u544a\u8bc9\u6211",
        "\u5e2e\u6211",
        "\u4e00\u4e0b",
        "\u8bf7\u95ee",
        "\u600e\u4e48",
        "\u5982\u4f55",
    ]
    stop_phrases_en = [
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
    for phrase in stop_phrases_cjk:
        subject = subject.replace(phrase, " ")
    for phrase in stop_phrases_en:
        subject = re.sub(rf"\b{re.escape(phrase)}\b", " ", subject)
    subject = re.sub(r"\s+", " ", subject).strip()
    # Drop dangling one-letter latin leftovers such as the trailing "s" from "games".
    subject = " ".join(token for token in subject.split(" ") if (len(token) > 1 or bool(re.search(r"[\u4e00-\u9fff]", token))))
    subject = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", subject).strip()
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

def _build_web_query_pack_dynamic(
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
    subject = _extract_search_subject_dynamic(query_text) or query_text
    focused = subject if len(subject) >= 2 else query_text

    seeds: list[str] = []
    if focused and focused != query_text:
        seeds.append(focused[:180])

    # Put one recency-aware facet early so it survives top-k truncation.
    if time_sensitive:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u4eca\u5929",
                    f"{focused} {today}",
                ]
            )
        else:
            seeds.extend(
                [
                    f"{focused} today",
                    f"{focused} {today}",
                    f"{focused} latest",
                ]
            )

    if sports_intent:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u6bd4\u8d5b\u7ed3\u679c",
                    f"{focused} \u8d5b\u7a0b",
                    f"{focused} \u6218\u62a5",
                    f"{focused} \u5b98\u65b9 \u8d5b\u7a0b",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} \u6bd4\u8d5b\u7ed3\u679c",
                ]
            )
        else:
            seeds.extend(
                [
                    f"{focused} match result",
                    f"{focused} fixtures",
                    f"{focused} recap",
                    f"{focused} official schedule",
                    f"{focused} box score",
                    f"{focused} game recap",
                    f"{focused} {today} result",
                ]
            )

    if time_sensitive:
        if is_cjk:
            seeds.extend(
                [
                    f"{focused} \u6700\u65b0",
                    f"{focused} \u4eca\u5929",
                    f"{focused} {today}",
                    f"{focused} {yesterday}",
                ]
            )
            if freshness_hours <= 48:
                seeds.append(f"{focused} \u6700\u8fd124\u5c0f\u65f6")
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
            seeds.extend(
                [
                    f"{focused} \u5b98\u65b9",
                    f"{focused} \u6570\u636e",
                    f"{focused} \u6765\u6e90",
                ]
            )
        else:
            seeds.extend([f"{focused} official", f"{focused} data", f"{focused} source"])

    matched_items = memory.get("matched_items") if isinstance(memory.get("matched_items"), list) else []
    for row in matched_items[:2]:
        target = str(row.get("target") or row.get("query") or "").strip()[:140]
        if not target:
            continue
        if is_cjk:
            seeds.append(f"{target} \u6700\u65b0")
        else:
            seeds.append(f"{target} latest")

    if isinstance(base_queries, list):
        seeds.extend(str(it or "").strip()[:180] for it in base_queries if str(it or "").strip())
    seeds.append(query_text[:180])

    return _normalize_web_queries(query_text, seeds, limit=limit)

def _decompose_web_context_boundaries_dynamic(
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

    fallback_queries = _build_web_query_pack_dynamic(
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
        "You are Aelin Query Decomposer Agent.\n"
        "Dynamically create temporary web-search subagents (facets) for this request.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"facets\": [{\"scope\": string, \"query\": string, \"priority\": number, \"why\": string}],"
        "\"reason\": string"
        "}\n"
        "Rules:\n"
        "- Create 3 to 5 facets when possible.\n"
        "- Queries must be short search-ready strings.\n"
        "- Avoid near-duplicate paraphrases.\n"
        "- Cover direct answer + verification + authoritative source.\n"
        "- If time-sensitive, include explicit date/recency facets.\n"
    )
    user_msg = (
        f"user_query: {query_text}\n"
        f"intent_contract: {json.dumps(contract, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
        f"existing_web_queries: {json.dumps(base_queries, ensure_ascii=False, separators=(',', ':'))[:600]}\n"
        f"matched_memory_count: {_safe_int(memory.get('matched_count'), 0)}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )

    parsed_payload: Any | None = None
    retry_used = False
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed_payload = _parse_json_payload(str(raw or ""))
    except Exception:
        parsed_payload = None

    if parsed_payload is None:
        retry_used = True
        retry_prompt = (
            "Return JSON only. Root can be {\"facets\": [...], \"reason\": \"...\"} "
            "or a JSON array of facets."
        )
        retry_msg = (
            f"user_query: {query_text}\n"
            f"intent_contract: {json.dumps(contract, ensure_ascii=False, separators=(',', ':'))[:800]}\n"
            f"fallback_candidates: {json.dumps(fallback_queries, ensure_ascii=False, separators=(',', ':'))[:600]}\n"
            "Generate 3-5 orthogonal facets and return JSON only."
        )
        try:
            raw_retry = service._chat(
                messages=[
                    {"role": "system", "content": retry_prompt},
                    {"role": "user", "content": retry_msg},
                ],
                max_tokens=320,
                stream=False,
            )
            parsed_payload = _parse_json_payload(str(raw_retry or ""))
        except Exception:
            parsed_payload = None

    if parsed_payload is None:
        return {
            "source": "fallback",
            "reason": "decomposer_invalid_json_retry_failed",
            "boundaries": fallback_boundaries,
        }

    parsed_reason = "decomposer_llm"
    if isinstance(parsed_payload, dict):
        parsed_reason = str(parsed_payload.get("reason") or "").strip()[:180] or parsed_reason

    raw_facets: Any = None
    if isinstance(parsed_payload, dict):
        raw_facets = (
            parsed_payload.get("facets")
            or parsed_payload.get("queries")
            or parsed_payload.get("boundaries")
            or parsed_payload.get("tasks")
        )
    elif isinstance(parsed_payload, list):
        raw_facets = parsed_payload

    if not isinstance(raw_facets, list):
        return {
            "source": "fallback",
            "reason": "decomposer_no_facets",
            "boundaries": fallback_boundaries,
        }

    normalized: list[tuple[int, dict[str, str]]] = []
    seen: set[str] = set()
    seen_sig: set[str] = set()

    def _facet_sig(text: str) -> str:
        base = str(text or "").strip().lower()
        if not base:
            return ""
        normalized_text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", base)
        for phrase in (
            "latest",
            "recent",
            "today",
            "yesterday",
            "now",
            "current",
            "\u6700\u65b0",
            "\u6700\u8fd1",
            "\u4eca\u5929",
            "\u6628\u5929",
            "\u524d\u5929",
            "\u5b9e\u65f6",
            "\u521a\u521a",
            "\u6709\u4ec0\u4e48",
            "\u6709\u54ea\u4e9b",
            "\u6709\u5565",
            "\u6709\u6ca1\u6709",
            "\u8bf7\u95ee",
            "\u5e2e\u6211",
        ):
            normalized_text = normalized_text.replace(phrase, " ")
        normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
        normalized_text = re.sub(r"[\u6709\u662f\u4e86\u5417\u5462\u5427\u5440\u554a\u4e48\u561b]+$", "", normalized_text).strip()
        return normalized_text or base

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
        sig = _facet_sig(q)
        if sig and sig in seen_sig:
            continue
        seen.add(key)
        if sig:
            seen_sig.add(sig)
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
    reason = parsed_reason
    if retry_used:
        reason = f"{reason};retry=1"
    return {
        "source": "llm",
        "reason": reason,
        "boundaries": boundaries,
    }

def _extract_search_subject(query: str) -> str:
    return _extract_search_subject_dynamic(query)

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
                    f"{focused} 最新 比分",
                    f"{focused} 比分",
                    f"{focused} 赛果",
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

    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
    except Exception:
        parsed = None

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

    reason = str(parsed.get("reason") or "").strip()[:180] or "decomposer_llm"
    return {
        "source": "llm",
        "reason": reason,
        "boundaries": boundaries,
    }

def _normalize_context_boundaries(
    query: str,
    raw_boundaries: Any,
    *,
    need_local_search: bool,
    need_web_search: bool,
    web_queries: list[str],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def count_kind(kind: str) -> int:
        return sum(1 for it in out if it["kind"] == kind)

    def push(kind: str, q: str, scope: str = "") -> None:
        k = (kind or "").strip().lower()
        if k not in {"local", "web"}:
            return
        if k == "local" and count_kind("local") >= _MAX_LOCAL_SUBAGENTS:
            return
        if k == "web" and count_kind("web") >= _MAX_WEB_SUBAGENTS:
            return
        text = (q or "").strip()[:180]
        if not text:
            return
        key = (k, text.lower())
        if key in seen:
            return
        seen.add(key)
        out.append({"kind": k, "query": text, "scope": (scope or text).strip()[:120]})

    if isinstance(raw_boundaries, list):
        for row in raw_boundaries:
            if len(out) >= _MAX_CONTEXT_BOUNDARIES:
                break
            if isinstance(row, str):
                push("web", row, row)
                continue
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or row.get("type") or row.get("source") or "").strip().lower()
            query_text = str(
                row.get("query") or row.get("facet") or row.get("task") or row.get("goal") or ""
            ).strip()
            scope = str(row.get("scope") or row.get("label") or "").strip()
            if kind in {"local_search", "local"}:
                push("local", query_text or query, scope)
            elif kind in {"web_search", "web"}:
                push("web", query_text or query, scope)

    if need_local_search and not any(it["kind"] == "local" for it in out):
        push("local", query, "local context")
    if need_web_search and not any(it["kind"] == "web" for it in out):
        for q in (web_queries or [query]):
            if len(out) >= _MAX_CONTEXT_BOUNDARIES:
                break
            push("web", q, q)

    out.sort(key=lambda x: 0 if x["kind"] == "local" else 1)
    return out[:_MAX_CONTEXT_BOUNDARIES]

def _build_trace_context_boundaries(
    *,
    query: str,
    raw_boundaries: Any,
    need_local_search: bool,
    need_web_search: bool,
    web_queries: list[str],
    intent_contract: dict[str, Any] | None,
    memory_snapshot: dict[str, Any] | None,
    max_local: int = 2,
    max_web: int = 3,
) -> list[dict[str, str]]:
    local_cap = max(0, min(_MAX_LOCAL_SUBAGENTS, int(max_local or 2)))
    web_cap = max(0, min(_MAX_WEB_SUBAGENTS, int(max_web or 3)))
    boundaries = _normalize_context_boundaries(
        query,
        raw_boundaries,
        need_local_search=need_local_search,
        need_web_search=need_web_search,
        web_queries=web_queries,
    )
    local = [it for it in boundaries if str(it.get("kind") or "") == "local"][:local_cap]
    web = [it for it in boundaries if str(it.get("kind") or "") == "web"][:web_cap]

    # When trace route is enabled but planner does not provide explicit boundaries,
    # synthesize lightweight web facets so Trace Agent can verify trackability.
    if need_web_search and (not web):
        seeds = _build_web_query_pack(
            query=(query or "").strip(),
            base_queries=web_queries or [(query or "").strip()],
            intent_contract=intent_contract if isinstance(intent_contract, dict) else None,
            memory_snapshot=memory_snapshot if isinstance(memory_snapshot, dict) else None,
            limit=web_cap,
        )
        for q in seeds[:web_cap]:
            web.append({"kind": "web", "query": q[:180], "scope": q[:120]})

    if need_local_search and (not local) and query.strip() and local_cap > 0:
        local.append(
            {
                "kind": "local",
                "query": query.strip()[:180],
                "scope": "trace local context",
            }
        )

    return [*local[:local_cap], *web[:web_cap]][:_MAX_CONTEXT_BOUNDARIES]

def _normalize_search_mode(raw: str) -> str:
    return "auto"

def _is_smalltalk_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return True
    signals = [
        "你好",
        "hello",
        "hi ",
        "在吗",
        "聊聊",
        "你觉得",
        "你怎么看",
        "心情",
        "焦虑",
        "emo",
        "哈哈",
        "谢谢",
        "晚安",
    ]
    return any(sig in text for sig in signals)

def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())

def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)

def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)

def _fallback_intent_contract(
    *,
    query: str,
    memory_summary: str,
    memory_snapshot: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    query_text = (query or "").strip()
    smalltalk = _is_smalltalk_query(query_text)
    time_sensitive = _is_time_sensitive_query(query_text)
    sports_result_intent = _is_sports_result_query(query_text)
    matched_count = 0
    if isinstance(memory_snapshot, dict):
        matched_count = _safe_int(memory_snapshot.get("matched_count"), 0)

    intent_type = "chat"
    if not smalltalk:
        intent_type = "retrieval"
    time_scope = "any"
    if time_sensitive:
        time_scope = "recent"
    if "today" in query_text.lower():
        time_scope = "today"
    freshness_hours = 720
    if time_scope == "today":
        freshness_hours = 24
    elif time_scope == "recent":
        freshness_hours = 72
    if sports_result_intent:
        freshness_hours = min(freshness_hours, 24)

    requires_citations = bool((not smalltalk) and (time_sensitive or sports_result_intent))
    requires_factuality = not smalltalk

    ambiguities: list[str] = []
    if len(query_text) <= 6:
        ambiguities.append("query_too_short")
    if intent_type == "retrieval" and matched_count > 0 and not time_sensitive:
        ambiguities.append("could_use_existing_memory_only")
    if intent_type == "retrieval" and not (memory_summary or "").strip():
        ambiguities.append("limited_personal_memory_context")

    return {
        "goal": query_text[:240] or "chat",
        "intent_type": intent_type,
        "time_scope": time_scope,
        "freshness_hours": max(1, min(720, int(freshness_hours))),
        "requires_citations": requires_citations,
        "requires_factuality": requires_factuality,
        "sports_result_intent": sports_result_intent,
        "ambiguities": ambiguities[:4],
        "confidence": 0.62 if not smalltalk else 0.8,
        "reason": reason[:180],
        "intent_source": "fallback",
    }

def _normalize_intent_contract(
    *,
    raw: dict[str, Any] | None,
    query: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    out = dict(fallback)
    if not isinstance(raw, dict):
        return out

    goal = str(raw.get("goal") or "").strip()
    if goal:
        out["goal"] = goal[:240]

    intent_type = str(raw.get("intent_type") or "").strip().lower()
    if intent_type in {"chat", "retrieval", "analysis"}:
        out["intent_type"] = intent_type

    time_scope = str(raw.get("time_scope") or "").strip().lower()
    if time_scope in {"any", "today", "recent", "historical", "realtime"}:
        out["time_scope"] = time_scope

    freshness_hours = _safe_int(raw.get("freshness_hours"), _safe_int(out.get("freshness_hours"), 72))
    out["freshness_hours"] = max(1, min(720, freshness_hours))

    if raw.get("requires_citations") is not None:
        out["requires_citations"] = bool(raw.get("requires_citations"))
    if raw.get("requires_factuality") is not None:
        out["requires_factuality"] = bool(raw.get("requires_factuality"))

    out["sports_result_intent"] = bool(raw.get("sports_result_intent")) or _is_sports_result_query(query)

    ambiguities = raw.get("ambiguities")
    if isinstance(ambiguities, list):
        normalized_ambiguities: list[str] = []
        for row in ambiguities:
            text = str(row or "").strip()
            if not text:
                continue
            normalized_ambiguities.append(text[:120])
            if len(normalized_ambiguities) >= 4:
                break
        out["ambiguities"] = normalized_ambiguities

    confidence = _safe_float(raw.get("confidence"), _safe_float(out.get("confidence"), 0.62))
    out["confidence"] = max(0.0, min(1.0, confidence))

    reason = str(raw.get("reason") or "").strip()
    if reason:
        out["reason"] = reason[:180]
    return out

def _build_intent_contract(
    *,
    query: str,
    service: LLMService,
    provider: str,
    memory_summary: str,
    memory_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = _fallback_intent_contract(
        query=query,
        memory_summary=memory_summary,
        memory_snapshot=memory_snapshot,
        reason="intent_fallback",
    )
    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "intent_planner_unavailable"
        if provider == "rule_based":
            fallback_reason = "intent_rule_based"
        elif not service.is_configured():
            fallback_reason = "intent_not_configured"
        fallback["reason"] = fallback_reason
        return fallback

    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    active_count = _safe_int(memory.get("active_count"), 0)
    matched_count = _safe_int(memory.get("matched_count"), 0)
    now_utc = datetime.now(timezone.utc).isoformat()

    prompt = (
        "You are Aelin Intent Lens Agent.\n"
        "Infer user intent with explicit time understanding and factuality requirements.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"goal\": string,"
        "\"intent_type\": \"chat|retrieval|analysis\","
        "\"time_scope\": \"any|today|recent|historical|realtime\","
        "\"freshness_hours\": number,"
        "\"requires_citations\": boolean,"
        "\"requires_factuality\": boolean,"
        "\"sports_result_intent\": boolean,"
        "\"ambiguities\": string[],"
        "\"confidence\": number,"
        "\"reason\": string"
        "}\n"
        "If user uses relative time words like today/recent/latest, convert them into explicit time_scope and freshness."
    )
    user_msg = (
        f"user_query: {query.strip()}\n"
        f"memory_summary_available: {'yes' if bool((memory_summary or '').strip()) else 'no'}\n"
        f"active_memory_count: {active_count}\n"
        f"matched_memory_count: {matched_count}\n"
        f"current_utc: {now_utc}\n"
        "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=320,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        normalized = _normalize_intent_contract(raw=parsed if isinstance(parsed, dict) else None, query=query, fallback=fallback)
        normalized["intent_source"] = "llm"
        if not isinstance(parsed, dict):
            normalized["reason"] = "intent_invalid_json"
            normalized["intent_source"] = "fallback"
        return normalized
    except Exception:
        fallback["reason"] = "intent_error"
        return fallback

def _plan_tool_usage(
    *,
    query: str,
    service: LLMService,
    provider: str,
    memory_summary: str,
    memory_snapshot: dict[str, Any] | None = None,
    intent_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _fallback_plan(reason: str) -> dict[str, Any]:
        contract = intent_contract if isinstance(intent_contract, dict) else {}
        contract_intent_type = str(contract.get("intent_type") or "").strip().lower()
        contract_time_scope = str(contract.get("time_scope") or "").strip().lower()
        contract_requires_citations = bool(contract.get("requires_citations"))
        contract_sports_intent = bool(contract.get("sports_result_intent"))

        memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
        active_items = memory.get("active_items") if isinstance(memory.get("active_items"), list) else []
        matched_items = memory.get("matched_items") if isinstance(memory.get("matched_items"), list) else []

        query_text = (query or "").strip()
        conversational = _is_smalltalk_query(query_text)
        time_sensitive = contract_time_scope in {"today", "recent", "realtime"} or _is_time_sensitive_query(query_text)
        has_memory = bool((memory_summary or "").strip())
        has_memory_match = bool(matched_items)

        recent_memory_match = False
        now = datetime.now(timezone.utc)
        for it in matched_items[:5]:
            updated_raw = str(it.get("updated_at") or "").strip()
            if not updated_raw:
                continue
            try:
                updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if (now - updated_at).total_seconds() <= 36 * 3600:
                recent_memory_match = True
                break

        retrieval_like = bool(query_text) and (not conversational)
        if contract_intent_type == "chat":
            retrieval_like = False
        elif contract_intent_type in {"retrieval", "analysis"}:
            retrieval_like = True
        sports_result_intent = bool(contract_sports_intent or _is_sports_result_query(query_text))
        need_local = retrieval_like and (has_memory or has_memory_match or bool(active_items))
        need_web = False
        if retrieval_like:
            if time_sensitive or sports_result_intent or contract_requires_citations:
                need_web = not recent_memory_match
            elif (not has_memory) and (not has_memory_match):
                need_web = True

        web_seed: list[str] = []
        if need_web:
            web_seed.append(query_text)
            if sports_result_intent:
                web_seed.extend(
                    [
                        f"{query_text} \u6700\u65b0 \u6bd4\u5206",
                        f"{query_text} \u8d5b\u679c",
                        f"{query_text} box score",
                        f"{query_text} game recap",
                    ]
                )
            for it in matched_items[:2]:
                target = str(it.get("target") or it.get("query") or "").strip()[:120]
                if target:
                    web_seed.append(f"{target} latest")
        web_queries = _normalize_web_queries(query_text, web_seed, limit=_MAX_WEB_SUBAGENTS) if need_web else []
        context_boundaries = _normalize_context_boundaries(
            query_text,
            [],
            need_local_search=need_local,
            need_web_search=need_web,
            web_queries=web_queries,
        )
        need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
        need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
        web_queries = (
            _normalize_web_queries(
                query_text,
                [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"],
            )
            if need_web
            else []
        )

        trace_context_boundaries: list[dict[str, str]] = []
        reason_bits = [reason]
        if conversational:
            reason_bits.append("smalltalk")
        if time_sensitive:
            reason_bits.append("time_sensitive")
        if sports_result_intent:
            reason_bits.append("sports_result_intent")
        if recent_memory_match:
            reason_bits.append("memory_match_recent")
        elif has_memory_match:
            reason_bits.append("memory_match_stale")
        if need_local:
            reason_bits.append("local_context")
        if need_web:
            reason_bits.append("web_context")
        return {
            "need_local_search": need_local,
            "need_web_search": need_web,
            "web_queries": web_queries,
            "context_boundaries": context_boundaries,
            "trace_context_boundaries": trace_context_boundaries,
            "route": {
                "reply_agent": True,
                "trace_agent": False,
                "allow_web_retry": bool(need_web and time_sensitive),
            },
            "reason": ";".join(reason_bits),
            "planner_source": "fallback",
        }

    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "planner_unavailable"
        if provider == "rule_based":
            fallback_reason = "planner_rule_based"
        elif not service.is_configured():
            fallback_reason = "planner_not_configured"
        return _fallback_plan(fallback_reason)

    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    active_items = memory.get("active_items") if isinstance(memory.get("active_items"), list) else []
    matched_items = memory.get("matched_items") if isinstance(memory.get("matched_items"), list) else []

    planning_prompt = (
        "You are Aelin Main Agent planner.\n"
        "Decide dynamic dispatch by context boundaries.\n"
        "You must obey intent contract constraints from Intent Lens Agent.\n"
        "Do not rely on rigid keyword-only rules; decide from query + memory context.\n"
        "Both local and web subagents are optional.\n"
        "You may dispatch up to 5 web subagents and up to 5 local subagents in parallel.\n"
        "If existing memory already covers the asked topic, you may skip web retrieval.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"need_local_search\": boolean,"
        "\"need_web_search\": boolean,"
        "\"web_queries\": string[],"
        "\"context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"trace_context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"reply_agent\": boolean,"
        "\"trace_agent\": boolean,"
        "\"allow_web_retry\": boolean,"
        "\"reason\": string"
        "}\n"
        "context_boundaries is the primary dispatch plan.\n"
        "reply_agent defaults to true and can be omitted unless you want it disabled."
    )
    matched_lines = [
        f"- {str(it.get('target') or '').strip()} ({str(it.get('source') or 'auto').strip()} / {str(it.get('updated_at') or '').strip()})"
        for it in matched_items[:5]
        if str(it.get("target") or "").strip()
    ]
    active_lines = [
        f"- {str(it.get('target') or '').strip()} ({str(it.get('source') or 'auto').strip()})"
        for it in active_items[:5]
        if str(it.get("target") or "").strip()
    ]
    user_msg = (
        f"user_query: {query.strip()}\n"
        + (
            f"intent_contract: {json.dumps(intent_contract, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
            if isinstance(intent_contract, dict)
            else ""
        )
        +
        f"memory_summary_available: {'yes' if bool((memory_summary or '').strip()) else 'no'}\n"
        f"active_memory_count: {len(active_items)}\n"
        + ("matched_memory:\n" + "\n".join(matched_lines) + "\n" if matched_lines else "matched_memory: none\n")
        + ("recent_memory:\n" + "\n".join(active_lines) + "\n" if active_lines else "recent_memory: none\n")
        + "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": planning_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=420,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return _fallback_plan("planner_invalid_json")

        need_local_hint = bool(parsed.get("need_local_search"))
        need_web_hint = bool(parsed.get("need_web_search"))
        web_queries = _normalize_web_queries(query, parsed.get("web_queries"))
        context_boundaries = _normalize_context_boundaries(
            query,
            parsed.get("context_boundaries"),
            need_local_search=need_local_hint,
            need_web_search=need_web_hint,
            web_queries=web_queries,
        )
        need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
        need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
        web_queries = _normalize_web_queries(
            query,
            [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"] or web_queries,
        )
        reason = str(parsed.get("reason") or "").strip()[:200] or "llm_planner"
        reply_agent = bool(parsed.get("reply_agent", True))
        trace_agent = False
        allow_web_retry_raw = parsed.get("allow_web_retry")
        allow_web_retry = bool(allow_web_retry_raw) if allow_web_retry_raw is not None else need_web

        trace_context_boundaries: list[dict[str, str]] = []

        if need_web and not web_queries:
            web_queries = [query.strip()[:180]] if query.strip() else []
        return {
            "need_local_search": need_local,
            "need_web_search": need_web,
            "web_queries": web_queries,
            "context_boundaries": context_boundaries,
            "trace_context_boundaries": trace_context_boundaries,
            "route": {
                "reply_agent": reply_agent,
                "trace_agent": trace_agent,
                "allow_web_retry": allow_web_retry,
            },
            "reason": f"llm:{reason}",
            "planner_source": "llm",
        }
    except Exception:
        return _fallback_plan("planner_error")

def _critic_tool_plan(
    *,
    query: str,
    intent_contract: dict[str, Any] | None,
    tool_plan: dict[str, Any],
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    def _fallback_critic(reason: str) -> dict[str, Any]:
        contract = intent_contract if isinstance(intent_contract, dict) else {}
        requires_citations = bool(contract.get("requires_citations"))
        intent_type = str(contract.get("intent_type") or "").strip().lower()
        sports_result_intent = bool(contract.get("sports_result_intent")) or _is_sports_result_query(query)

        need_local = bool(tool_plan.get("need_local_search"))
        need_web = bool(tool_plan.get("need_web_search"))
        web_queries = _normalize_web_queries(query, tool_plan.get("web_queries"))
        boundaries = _normalize_context_boundaries(
            query,
            tool_plan.get("context_boundaries"),
            need_local_search=need_local,
            need_web_search=need_web,
            web_queries=web_queries,
        )
        has_local = any(str(it.get("kind") or "") == "local" for it in boundaries)
        has_web = any(str(it.get("kind") or "") == "web" for it in boundaries)
        route = tool_plan.get("route") if isinstance(tool_plan.get("route"), dict) else {}
        issues: list[str] = []
        patch: dict[str, Any] = {}

        retrieval_intent = intent_type in {"retrieval", "analysis"} or (not _is_smalltalk_query(query))
        if retrieval_intent and (not has_local) and (not has_web):
            issues.append("no_retrieval_path")
            patch["need_local_search"] = True
            patch["context_boundaries"] = [{"kind": "local", "query": query.strip()[:180], "scope": "critic_local_context"}]

        if (requires_citations or sports_result_intent) and (not has_web):
            issues.append("missing_web_path_for_factual_intent")
            patch["need_web_search"] = True
            patch["web_queries"] = _normalize_web_queries(
                query,
                [
                    query.strip()[:180],
                    f"{query.strip()[:160]} 最新",
                    f"{query.strip()[:160]} 比分" if sports_result_intent else f"{query.strip()[:160]} 官方",
                ],
                limit=_MAX_WEB_SUBAGENTS,
            )
            patch_boundaries = patch.get("context_boundaries")
            if not isinstance(patch_boundaries, list):
                patch_boundaries = list(boundaries)
            patch_boundaries.extend(
                {"kind": "web", "query": q, "scope": q}
                for q in patch.get("web_queries", [])[:2]
            )
            patch["context_boundaries"] = patch_boundaries

        accepted = not issues
        return {
            "accepted": accepted,
            "issues": issues,
            "patch": patch if patch else None,
            "reason": reason if accepted else f"{reason}:{','.join(issues)}",
            "critic_source": "fallback",
        }

    if provider == "rule_based" or not service.is_configured():
        fallback_reason = "critic_unavailable"
        if provider == "rule_based":
            fallback_reason = "critic_rule_based"
        elif not service.is_configured():
            fallback_reason = "critic_not_configured"
        return _fallback_critic(fallback_reason)

    contract_payload = intent_contract if isinstance(intent_contract, dict) else {}
    prompt = (
        "You are Aelin Plan Critic Agent.\n"
        "Evaluate whether dispatch plan fully covers intent contract.\n"
        "If weak, provide a corrective patch.\n"
        "Return strict JSON only with schema:\n"
        "{"
        "\"accepted\": boolean,"
        "\"issues\": string[],"
        "\"patch\": {"
        "\"need_local_search\": boolean,"
        "\"need_web_search\": boolean,"
        "\"web_queries\": string[],"
        "\"context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"trace_context_boundaries\": [{\"kind\":\"local|web\",\"query\":\"string\",\"scope\":\"string\"}],"
        "\"route\": {\"reply_agent\": boolean,\"trace_agent\": boolean,\"allow_web_retry\": boolean}"
        "},"
        "\"reason\": string"
        "}\n"
        "Rules:\n"
        "- For time-sensitive factual intents, ensure evidence path exists.\n"
        "- For sports result intents, prefer web path with score/result oriented queries.\n"
        "- Keep patch minimal and deterministic."
    )
    user_msg = (
        f"user_query: {query.strip()}\n"
        f"intent_contract: {json.dumps(contract_payload, ensure_ascii=False, separators=(',', ':'))[:1200]}\n"
        f"tool_plan: {json.dumps(tool_plan, ensure_ascii=False, separators=(',', ':'))[:1800]}\n"
        "Return JSON only."
    )
    try:
        raw = service._chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=320,
            stream=False,
        )
        parsed = _parse_json_object(str(raw or ""))
        if not isinstance(parsed, dict):
            return _fallback_critic("critic_invalid_json")
        accepted = bool(parsed.get("accepted"))
        issues_raw = parsed.get("issues")
        issues: list[str] = []
        if isinstance(issues_raw, list):
            for row in issues_raw:
                text = str(row or "").strip()
                if not text:
                    continue
                issues.append(text[:120])
                if len(issues) >= 6:
                    break
        patch_raw = parsed.get("patch")
        patch: dict[str, Any] | None = None
        if isinstance(patch_raw, dict):
            patch = {}
            if patch_raw.get("need_local_search") is not None:
                patch["need_local_search"] = bool(patch_raw.get("need_local_search"))
            if patch_raw.get("need_web_search") is not None:
                patch["need_web_search"] = bool(patch_raw.get("need_web_search"))
            if patch_raw.get("web_queries") is not None:
                patch["web_queries"] = _normalize_web_queries(query, patch_raw.get("web_queries"), limit=_MAX_WEB_SUBAGENTS)
            if isinstance(patch_raw.get("context_boundaries"), list):
                patch["context_boundaries"] = patch_raw.get("context_boundaries")
            if isinstance(patch_raw.get("trace_context_boundaries"), list):
                patch["trace_context_boundaries"] = patch_raw.get("trace_context_boundaries")
            if isinstance(patch_raw.get("route"), dict):
                route_raw = patch_raw.get("route") or {}
                patch["route"] = {
                    "reply_agent": bool(route_raw.get("reply_agent", True)),
                    "trace_agent": bool(route_raw.get("trace_agent", False)),
                    "allow_web_retry": bool(route_raw.get("allow_web_retry", False)),
                }
        reason = str(parsed.get("reason") or "").strip()[:180] or "critic_llm"
        if (not accepted) and (not patch):
            fallback = _fallback_critic(f"critic_patch_missing:{reason}")
            fallback["critic_source"] = "fallback"
            return fallback
        return {
            "accepted": accepted,
            "issues": issues,
            "patch": patch,
            "reason": reason,
            "critic_source": "llm",
        }
    except Exception:
        return _fallback_critic("critic_error")

def _apply_plan_patch(
    *,
    query: str,
    tool_plan: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    out = dict(tool_plan or {})
    need_local = bool(patch.get("need_local_search", out.get("need_local_search")))
    need_web = bool(patch.get("need_web_search", out.get("need_web_search")))
    web_queries_seed = patch.get("web_queries") if patch.get("web_queries") is not None else out.get("web_queries")
    web_queries = _normalize_web_queries(query, web_queries_seed, limit=_MAX_WEB_SUBAGENTS)
    context_seed = patch.get("context_boundaries") if isinstance(patch.get("context_boundaries"), list) else out.get("context_boundaries")
    context_boundaries = _normalize_context_boundaries(
        query,
        context_seed,
        need_local_search=need_local,
        need_web_search=need_web,
        web_queries=web_queries,
    )
    need_local = any(str(it.get("kind") or "") == "local" for it in context_boundaries)
    need_web = any(str(it.get("kind") or "") == "web" for it in context_boundaries)
    web_queries = _normalize_web_queries(
        query,
        [it.get("query") for it in context_boundaries if str(it.get("kind") or "") == "web"] or web_queries,
        limit=_MAX_WEB_SUBAGENTS,
    )

    base_route = out.get("route") if isinstance(out.get("route"), dict) else {}
    patch_route = patch.get("route") if isinstance(patch.get("route"), dict) else {}
    merged_route = {
        "reply_agent": bool(patch_route.get("reply_agent", base_route.get("reply_agent", True))),
        "trace_agent": False,
        "allow_web_retry": bool(patch_route.get("allow_web_retry", base_route.get("allow_web_retry", need_web))),
    }
    trace_seed = patch.get("trace_context_boundaries") if isinstance(patch.get("trace_context_boundaries"), list) else out.get("trace_context_boundaries")
    trace_enabled = bool(merged_route.get("trace_agent"))
    trace_context_boundaries = _build_trace_context_boundaries(
        query=query,
        raw_boundaries=trace_seed,
        need_local_search=trace_enabled and need_local,
        need_web_search=trace_enabled and bool(need_web or merged_route.get("allow_web_retry")),
        web_queries=web_queries,
        intent_contract=None,
        memory_snapshot=None,
    )

    out["need_local_search"] = need_local
    out["need_web_search"] = need_web
    out["web_queries"] = web_queries
    out["context_boundaries"] = context_boundaries
    out["trace_context_boundaries"] = trace_context_boundaries
    out["route"] = merged_route
    out["planner_source"] = str(out.get("planner_source") or "fallback") + "+critic_patch"
    out["reason"] = str(out.get("reason") or "planner") + ";critic_patch"
    return out

def _is_sports_result_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    signals = [
        "nba",
        "wnba",
        "cba",
        "nfl",
        "nhl",
        "mlb",
        "epl",
        "\u6bd4\u8d5b",
        "\u6bd4\u5206",
        "\u8d5b\u7a0b",
        "\u8d5b\u679c",
        "\u6218\u7ee9",
        "\u6253\u4e86\u4ec0\u4e48",
        "\u8c01\u8d62\u4e86",
        "\u5bf9\u9635",
        "\u5b63\u540e\u8d5b",
        "\u5e38\u89c4\u8d5b",
        "score",
        "box score",
        "result",
        "results",
        "fixture",
        "fixtures",
        "match",
        "matches",
        "who won",
        "standings",
        "game recap",
    ]
    return any(sig in text for sig in signals)

def _is_time_sensitive_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    signals = [
        "\u4eca\u5929",
        "\u6628\u5929",
        "\u524d\u5929",
        "\u521a\u521a",
        "\u6700\u65b0",
        "\u6700\u8fd1",
        "\u8fd1\u671f",
        "\u8fd1\u51e0\u5929",
        "\u5b9e\u65f6",
        "\u5373\u65f6",
        "\u76ee\u524d",
        "\u6bd4\u5206",
        "\u6218\u7ee9",
        "\u8d5b\u679c",
        "\u65b0\u95fb",
        "\u80a1\u4ef7",
        "\u4ef7\u683c",
        "\u6c47\u7387",
        "now",
        "today",
        "yesterday",
        "latest",
        "recent",
        "recently",
        "breaking",
        "live",
        "score",
        "result",
        "results",
        "price",
        "quote",
        "this week",
        "last week",
        "past",
    ]
    if any(sig in text for sig in signals):
        return True
    if re.search(r"\b(last|past)\s+(24|48|72)\s*(h|hour|hours|d|day|days)\b", text):
        return True
    if re.search(r"\b(last|past|recent)\s+\d+\s*(day|days|week|weeks|month|months)\b", text):
        return True
    return False

def _build_retry_web_queries(
    query: str,
    used_queries: list[str],
    *,
    intent_contract: dict[str, Any] | None = None,
    memory_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    base = (query or "").strip()
    if not base:
        return []
    used = {q.strip().lower() for q in used_queries if q.strip()}
    query_pack = _build_web_query_pack(
        query=base,
        base_queries=[base],
        intent_contract=intent_contract if isinstance(intent_contract, dict) else None,
        memory_snapshot=memory_snapshot if isinstance(memory_snapshot, dict) else None,
        limit=min(_MAX_WEB_SUBAGENTS + 2, 7),
    )
    out: list[str] = []
    for candidate in query_pack:
        text = candidate.strip()[:180]
        if not text:
            continue
        key = text.lower()
        if key in used:
            continue
        used.add(key)
        out.append(text)
        if len(out) >= 3:
            break
    return out


def _decompose_web_context_boundaries(
    *,
    query: str,
    web_boundaries: list[dict[str, str]],
    intent_contract: dict[str, Any] | None,
    memory_snapshot: dict[str, Any] | None,
    service: LLMService,
    provider: str,
) -> dict[str, Any]:
    """
    Public wrapper that delegates to the dynamic implementation. Keeping this
    indirection makes it easier to evolve the dynamic behaviour (including
    retry) without changing the external surface or tests.
    """
    return _decompose_web_context_boundaries_dynamic(
        query=query,
        web_boundaries=web_boundaries,
        intent_contract=intent_contract,
        memory_snapshot=memory_snapshot,
        service=service,
        provider=provider,
    )
