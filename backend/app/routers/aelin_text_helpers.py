from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.schemas import AelinCitation

_AELIN_EXPRESSION_IDS = {
    "exp-01",
    "exp-02",
    "exp-03",
    "exp-04",
    "exp-05",
    "exp-06",
    "exp-07",
    "exp-08",
    "exp-09",
    "exp-10",
    "exp-11",
}

_AELIN_EXPRESSION_META: dict[str, dict[str, str]] = {
    "exp-01": {"label": "捂嘴惊喜", "usage": "害羞、惊喜、被夸时的可爱反馈"},
    "exp-02": {"label": "热情出击", "usage": "开场打招呼、推进执行、强积极反馈"},
    "exp-03": {"label": "温柔赞同", "usage": "支持、认可、安抚、温和鼓励"},
    "exp-04": {"label": "托腮思考", "usage": "解释、分析、答疑、默认交流"},
    "exp-05": {"label": "轻声提醒", "usage": "注意事项、风险提示、保守建议"},
    "exp-06": {"label": "偷看观察", "usage": "围观进展、持续关注、等待更多线索"},
    "exp-07": {"label": "低落求助", "usage": "失败、遗憾、道歉、需要帮助"},
    "exp-08": {"label": "不满委屈", "usage": "吐槽、不爽、抗议、情绪性反馈"},
    "exp-09": {"label": "指着大笑", "usage": "玩梗、幽默、轻松调侃"},
    "exp-10": {"label": "发财得意", "usage": "成果突出、搞定任务、高价值收获"},
    "exp-11": {"label": "趴桌躺平", "usage": "困倦、过载、精力不足、需要休息"},
}

_AELIN_EXPRESSION_ALIASES: dict[str, str] = {
    "惊喜": "exp-01",
    "害羞": "exp-01",
    "脸红": "exp-01",
    "开心": "exp-02",
    "兴奋": "exp-02",
    "期待": "exp-02",
    "比心": "exp-03",
    "支持": "exp-03",
    "安抚": "exp-03",
    "默认": "exp-04",
    "友好": "exp-04",
    "疑问": "exp-04",
    "困惑": "exp-04",
    "严肃": "exp-05",
    "警惕": "exp-05",
    "提醒": "exp-05",
    "围观": "exp-06",
    "观察": "exp-06",
    "失败": "exp-07",
    "抱歉": "exp-07",
    "委屈": "exp-08",
    "生气": "exp-08",
    "愤怒": "exp-08",
    "笑": "exp-09",
    "大笑": "exp-09",
    "调皮": "exp-09",
    "眨眼": "exp-09",
    "喜欢": "exp-10",
    "心动": "exp-10",
    "发财": "exp-10",
    "困": "exp-11",
    "困倦": "exp-11",
    "发懵": "exp-11",
    "躺平": "exp-11",
}

_AELIN_EMOJI_BY_EXPRESSION: dict[str, str] = {
    "exp-01": "🥹",
    "exp-02": "✨",
    "exp-03": "🤍",
    "exp-04": "🙂",
    "exp-05": "⚠️",
    "exp-06": "👀",
    "exp-07": "🥲",
    "exp-08": "😤",
    "exp-09": "😂",
    "exp-10": "💰",
    "exp-11": "😮‍💨",
}
_EMOJI_CHAR_RE = re.compile(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]")

_DIARY_TOPIC_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(nba|curry|warriors|lakers|basketball|湖人|勇士|库里|篮球)\b", flags=re.I), ["体育", "NBA"]),
    (re.compile(r"\b(epl|premier\s*league|英超|阿森纳|利物浦|曼城|曼联)\b", flags=re.I), ["体育", "英超"]),
    (re.compile(r"\b(mlb|棒球)\b", flags=re.I), ["体育", "棒球"]),
    (re.compile(r"\b(nfl|橄榄球)\b", flags=re.I), ["体育", "橄榄球"]),
    (re.compile(r"\b(ai|llm|agent|模型|提示词|智能体)\b", flags=re.I), ["技术", "AI"]),
    (re.compile(r"\b(bitcoin|btc|eth|crypto|加密|比特币)\b", flags=re.I), ["财经", "加密资产"]),
]


def _json_from_text(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_expression_id(raw: str | None) -> str | None:
    text = (raw or "").strip().lower()
    if not text:
        return None
    alias = _AELIN_EXPRESSION_ALIASES.get(text)
    if alias:
        return alias
    if text.isdigit():
        n = int(text)
        if 1 <= n <= 11:
            text = f"exp-{n:02d}"
    if text.startswith("exp_"):
        text = "exp-" + text[4:]
    if re.fullmatch(r"exp-\d{1,2}", text):
        n = int(text.split("-", 1)[1])
        if 1 <= n <= 11:
            text = f"exp-{n:02d}"
    if text in _AELIN_EXPRESSION_IDS:
        return text
    return None


def _extract_expression_tag(answer: str) -> tuple[str, str | None]:
    text = (answer or "").strip()
    if not text:
        return "", None
    patterns = [
        r"\[(?:expression|expr|sticker|表情|情绪)\s*[:：]\s*([A-Za-z0-9_-]{1,16})\]",
        r"<(?:expression|expr|sticker)\s*[:：]\s*([A-Za-z0-9_-]{1,16})>",
    ]
    expression: str | None = None
    cleaned = text
    for pat in patterns:
        match = re.search(pat, cleaned, flags=re.I)
        if not match:
            continue
        expression = _normalize_expression_id(match.group(1))
        cleaned = re.sub(pat, "", cleaned, flags=re.I).strip()
        if expression:
            break
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, expression


def _contains_emoji(text: str) -> bool:
    return bool(_EMOJI_CHAR_RE.search(str(text or "")))


def _normalize_emoji_token(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    snippet = text[:8]
    if not _contains_emoji(snippet):
        return None
    return snippet


def _extract_emoji_tag(answer: str) -> tuple[str, str | None]:
    text = (answer or "").strip()
    if not text:
        return "", None
    pattern = r"\[(?:emoji|emj|表情符号|emoji_tag)\s*[:：]\s*([^\]\n]{1,16})\]"
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return text, None
    emoji = _normalize_emoji_token(match.group(1))
    cleaned = re.sub(pattern, "", text, flags=re.I).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, emoji


def _apply_answer_emoji(answer: str, expression: str, *, explicit_emoji: str | None = None) -> str:
    text = (answer or "").strip()
    if not text:
        return explicit_emoji or _AELIN_EMOJI_BY_EXPRESSION.get(expression, "🙂")
    if _contains_emoji(text):
        return text
    emoji = _normalize_emoji_token(explicit_emoji) or _AELIN_EMOJI_BY_EXPRESSION.get(expression)
    if not emoji:
        return text
    return f"{text} {emoji}"


def _pick_expression(query: str, answer: str, *, generation_failed: bool = False) -> str:
    q = (query or "").lower()
    a = (answer or "").lower()
    text = f"{q}\n{a}"

    if generation_failed or any(token in text for token in ["失败", "错误", "抱歉", "无法", "暂不支持", "不确定"]):
        return "exp-07"
    if any(token in text for token in ["生气", "愤怒", "气死", "火大", "离谱"]):
        return "exp-08"
    if any(token in text for token in ["风险", "谨慎", "警告", "严肃", "注意", "不建议"]):
        return "exp-05"
    if any(token in text for token in ["过载", "太困", "睡了", "晚安", "休息", "累", "崩溃", "躺平"]):
        return "exp-11"
    if any(token in text for token in ["观察", "围观", "后续", "继续跟踪", "等等看"]):
        return "exp-06"
    if any(token in text for token in ["爱你", "喜欢", "心动", "可爱", "浪漫", "害羞", "脸红"]):
        return "exp-01"
    if any(token in text for token in ["赚", "盈利", "拿下", "搞定", "高收益", "发财"]):
        return "exp-10"
    if any(token in text for token in ["恭喜", "太棒", "厉害", "优秀", "好耶", "开心"]):
        return "exp-02"
    if any(token in text for token in ["谢谢", "感谢", "支持", "加油", "辛苦了"]):
        return "exp-03"
    if any(token in text for token in ["哈哈", "hh", "笑死", "有趣", "好玩"]):
        return "exp-09"
    if ("?" in q) or ("？" in q) or any(token in q for token in ["为什么", "怎么", "吗", "啥", "什么", "如何"]):
        return "exp-04"
    if any(token in text for token in ["收到", "明白", "ok", "好的", "安排"]):
        return "exp-06"
    return "exp-04"


def _expression_mapping_prompt() -> str:
    lines = []
    for exp_id in sorted(_AELIN_EXPRESSION_META.keys()):
        meta = _AELIN_EXPRESSION_META[exp_id]
        lines.append(f"- {exp_id}: {meta['label']}（{meta['usage']}）")
    return "\n".join(lines)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"


def _dedupe_citations(rows: list[AelinCitation], *, limit: int) -> list[AelinCitation]:
    out: list[AelinCitation] = []
    seen: set[tuple[int, str, str]] = set()
    safe_limit = max(1, min(20, int(limit or 6)))
    sorted_rows = sorted(rows, key=lambda item: float(item.score or 0.0), reverse=True)
    for item in sorted_rows:
        key = (int(item.message_id or 0), str(item.source or ""), str(item.title or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= safe_limit:
            break
    return out


def _extract_first_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    direct = _json_from_text(text)
    if direct:
        return direct
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    return _json_from_text(match.group(0))


def _infer_diary_topic_path(*texts: str, fallback_source: str = "综合") -> list[str]:
    merged = " ".join(str(item or "") for item in texts).strip()
    if not merged:
        return [str(fallback_source or "综合")[:32]]
    for pattern, topic in _DIARY_TOPIC_RULES:
        if pattern.search(merged):
            return topic
    fallback = str(fallback_source or "综合").strip()[:32] or "综合"
    return [fallback]


def _build_source_indices_from_citations(citations: list[AelinCitation]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cite in citations[:20]:
        msg_id = int(cite.message_id or 0)
        key = f"message:{msg_id}"
        if msg_id <= 0 or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "type": "message",
                "message_id": msg_id,
                "label": f"[{cite.source_label}] {cite.title}".strip()[:220],
            }
        )
    return out[:24]


def _sanitize_diary_answer(answer: str) -> str:
    rows: list[str] = []
    for raw in str(answer or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        lowered = line.lower()
        if "path=" in lowered:
            continue
        if "tracking snapshot" in lowered:
            continue
        if lowered.startswith("```") or lowered.startswith("{") or lowered.startswith("["):
            continue
        rows.append(line[:220])
        if len(rows) >= 6:
            break
    merged = re.sub(r"\s+", " ", " ".join(rows)).strip()
    if not merged:
        merged = re.sub(r"\s+", " ", str(answer or "")).strip()
    return merged[:420]


def _build_chat_diary_entry(query: str, answer: str, citations: list[AelinCitation]) -> tuple[str, str]:
    q = re.sub(r"\s+", " ", str(query or "").strip())[:220]
    a = _sanitize_diary_answer(answer)
    title = (f"聊天纪要：{q[:40]}" if q else "聊天纪要").strip()
    evidence_lines: list[str] = []
    for cite in citations[:4]:
        evidence_lines.append(f"- [{cite.source_label}] {cite.title}（{cite.sender}）")
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "- （本轮未生成可引用证据）"
    body = (
        f"今天主人问了我：「{q or '（未记录问题）'}」。\n\n"
        f"我给出的核心结论是：{a or '（未记录回答）'}\n\n"
        "这轮我参考的关键线索：\n"
        f"{evidence_text}\n\n"
        "我会继续观察这个主题，如果后续有新的事实或变化，会补写新的日记条目。"
    )
    markdown = "\n".join(
        [
            "## 今日对话",
            "",
            body,
            "",
            "## 小结",
            "",
            "这是一条面向后续检索的聊天日记，保留可复用结论与证据锚点。",
        ]
    )
    return title[:120], markdown.strip()
