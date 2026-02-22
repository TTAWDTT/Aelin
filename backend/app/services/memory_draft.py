from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")

_TOPIC_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(nba|curry|warriors|lakers|basketball|湖人|勇士|库里|篮球)\b", flags=re.I), ["体育", "NBA"]),
    (re.compile(r"\b(epl|premier\s*league|英超|阿森纳|利物浦|曼城|曼联)\b", flags=re.I), ["体育", "英超"]),
    (re.compile(r"\b(ai|llm|agent|模型|提示词|智能体)\b", flags=re.I), ["技术", "AI"]),
    (re.compile(r"\b(bitcoin|btc|eth|crypto|加密|比特币)\b", flags=re.I), ["财经", "加密资产"]),
]


def _normalize_text(value: str, *, max_len: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _infer_topic_path(*segments: str, fallback: str = "综合") -> list[str]:
    merged = " ".join(_normalize_text(item, max_len=600) for item in segments if str(item or "").strip())
    if not merged:
        return [fallback]
    for pattern, topic in _TOPIC_RULES:
        if pattern.search(merged):
            return topic
    for token in _TOKEN_RE.findall(merged):
        safe = token.strip()
        if len(safe) < 2:
            continue
        if re.fullmatch(r"[0-9_]+", safe):
            continue
        return [fallback, safe[:24]]
    return [fallback]


def _confidence(citations: int, file_hits: int, web_hits: int) -> float:
    score = 0.24 + min(0.36, citations * 0.06) + min(0.24, file_hits * 0.08) + min(0.18, web_hits * 0.03)
    return round(max(0.25, min(0.92, score)), 3)


@dataclass(slots=True)
class ParallelMemoryDraftResult:
    title: str
    markdown: str
    confidence: float
    topic_path: list[str]
    source_indices: list[dict[str, Any]]
    evidence_count: int
    reason: str = ""


def build_parallel_memory_draft(
    *,
    query: str,
    citations: list[dict[str, Any]],
    file_memory_items: list[dict[str, Any]],
    web_results: list[dict[str, Any]],
    memory_summary: str = "",
    brief_summary: str = "",
) -> ParallelMemoryDraftResult:
    query_text = _normalize_text(query, max_len=220)
    citation_rows = citations[:10] if isinstance(citations, list) else []
    file_rows = file_memory_items[:8] if isinstance(file_memory_items, list) else []
    web_rows = web_results[:8] if isinstance(web_results, list) else []
    source_indices: list[dict[str, Any]] = []
    evidence_lines: list[str] = []
    observed_lines: list[str] = []

    for row in citation_rows:
        if not isinstance(row, dict):
            continue
        message_id = int(row.get("message_id") or 0)
        title = _normalize_text(str(row.get("title") or "本地证据"), max_len=160)
        source = _normalize_text(str(row.get("source_label") or row.get("source") or "local"), max_len=24)
        sender = _normalize_text(str(row.get("sender") or ""), max_len=32)
        snippet = _normalize_text(str(row.get("snippet") or row.get("preview") or ""), max_len=180)
        line = f"- [{source}] {title}"
        if sender:
            line += f"（{sender}）"
        if snippet:
            line += f" | {snippet}"
        evidence_lines.append(line)
        observed_lines.append(f"{title} {snippet}".strip())
        if message_id > 0:
            source_indices.append(
                {
                    "type": "message",
                    "message_id": message_id,
                    "label": title,
                    "path": "",
                    "url": "",
                }
            )

    for row in file_rows:
        if not isinstance(row, dict):
            continue
        path = _normalize_text(str(row.get("path") or ""), max_len=500)
        title = _normalize_text(str(row.get("title") or row.get("target") or "日记命中"), max_len=160)
        preview = _normalize_text(str(row.get("preview") or ""), max_len=180)
        topic_path = _normalize_text(str(row.get("topic_path") or ""), max_len=140)
        line = f"- [日记] {title}"
        if topic_path:
            line += f" | topic={topic_path}"
        if preview:
            line += f" | {preview}"
        evidence_lines.append(line)
        observed_lines.append(f"{title} {preview}".strip())
        source_indices.append(
            {
                "type": "file",
                "message_id": 0,
                "label": title,
                "path": path,
                "url": "",
            }
        )

    for row in web_rows:
        if not isinstance(row, dict):
            continue
        title = _normalize_text(str(row.get("title") or "web"), max_len=160)
        host = _normalize_text(str(row.get("host") or row.get("domain") or row.get("source") or ""), max_len=48)
        snippet = _normalize_text(str(row.get("snippet") or row.get("fetched_excerpt") or ""), max_len=180)
        url = _normalize_text(str(row.get("url") or ""), max_len=500)
        line = f"- [Web] {title}"
        if host:
            line += f" ({host})"
        if snippet:
            line += f" | {snippet}"
        evidence_lines.append(line)
        observed_lines.append(f"{title} {snippet}".strip())
        source_indices.append(
            {
                "type": "url",
                "message_id": 0,
                "label": title,
                "path": "",
                "url": url,
            }
        )

    evidence_lines = evidence_lines[:12]
    source_indices = source_indices[:24]
    evidence_count = len(evidence_lines)
    conf = _confidence(len(citation_rows), len(file_rows), len(web_rows))
    title = f"并行记忆草稿：{(query_text or '当前对话')[:42]}"
    topic_path = _infer_topic_path(
        query_text,
        " ".join(observed_lines[:8]),
        memory_summary,
        brief_summary,
        fallback="对话",
    )

    summary_line = _normalize_text("；".join([line.lstrip("- ").strip() for line in evidence_lines[:3]]), max_len=500)
    if not summary_line:
        summary_line = "当前轮次缺少稳定证据，暂不沉淀为长期记忆。"

    markdown = "\n".join(
        [
            "## 草稿背景",
            "",
            f"用户问题：{query_text or '（未记录）'}",
            "",
            "## 并行提炼（草稿）",
            "",
            summary_line,
            "",
            "## 证据锚点（并行采集）",
            "",
            *(evidence_lines or ["- （本轮没有可复用证据）"]),
            "",
            "## 记忆策略",
            "",
            "该草稿在回复构建期间并行生成，仅在最终校验通过后提交到正式日记。",
        ]
    ).strip()

    reason = "parallel_draft_ready" if evidence_count > 0 else "no_evidence"
    return ParallelMemoryDraftResult(
        title=title,
        markdown=markdown,
        confidence=conf,
        topic_path=topic_path,
        source_indices=source_indices,
        evidence_count=evidence_count,
        reason=reason,
    )
