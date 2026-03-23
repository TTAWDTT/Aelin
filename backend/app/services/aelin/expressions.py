from __future__ import annotations

import re


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

_FAILURE_TOKENS = ("失败", "错误", "抱歉", "无法", "暂不支持", "不确定")
_RISK_TOKENS = ("风险", "谨慎", "警告", "注意", "不建议")
_POSITIVE_TOKENS = ("谢谢", "感谢", "支持", "加油", "辛苦了")


def _normalize_expression_id(raw: str | None) -> str | None:
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        value = int(text)
        if 1 <= value <= 11:
            text = f"exp-{value:02d}"
    if text.startswith("exp_"):
        text = "exp-" + text[4:]
    if re.fullmatch(r"exp-\d{1,2}", text):
        value = int(text.split("-", 1)[1])
        if 1 <= value <= 11:
            text = f"exp-{value:02d}"
    if text in _AELIN_EXPRESSION_IDS:
        return text
    return None


def _extract_expression_tag(answer: str) -> tuple[str, str | None]:
    text = str(answer or "").strip()
    if not text:
        return "", None
    patterns = (
        r"\[(?:expression|expr|sticker|表情|情绪)\s*[:：]\s*([A-Za-z0-9_-]{1,16})\]",
        r"<(?:expression|expr|sticker)\s*[:：]\s*([A-Za-z0-9_-]{1,16})>",
    )
    cleaned = text
    expression: str | None = None
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.I)
        if not match:
            continue
        expression = _normalize_expression_id(match.group(1))
        cleaned = re.sub(pattern, "", cleaned, flags=re.I).strip()
        if expression:
            break
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, expression


def _pick_expression(query: str, answer: str, *, generation_failed: bool = False) -> str:
    query_text = str(query or "").lower()
    answer_text = str(answer or "").lower()
    text = f"{query_text}\n{answer_text}"

    if generation_failed or any(token in text for token in _FAILURE_TOKENS):
        return "exp-07"
    if any(token in text for token in _RISK_TOKENS):
        return "exp-05"
    if any(token in text for token in _POSITIVE_TOKENS):
        return "exp-03"
    if "?" in query_text or "？" in query_text:
        return "exp-04"
    if any(token in query_text for token in ("为什么", "怎么", "吗", "啥", "什么", "如何")):
        return "exp-04"
    return "exp-04"
