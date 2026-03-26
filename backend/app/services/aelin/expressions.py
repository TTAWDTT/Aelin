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
    del query, answer
    if generation_failed:
        return "exp-07"
    return "exp-04"
