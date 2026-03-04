from __future__ import annotations

import re
from urllib.parse import urlparse

from app.services.web_search import WebSearchResult

def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.strip().lower()
        return host or "web"
    except Exception:
        return "web"

def _extract_score_clues(text: str) -> list[str]:
    src = (text or "").strip()
    if not src:
        return []
    out: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"([A-Za-z\u4e00-\u9fff·]{1,24})?\s*(\d{2,3})\s*[-:：]\s*(\d{2,3})\s*([A-Za-z\u4e00-\u9fff·]{1,24})?"
    )
    for m in pattern.finditer(src):
        a = int(m.group(2))
        b = int(m.group(3))
        if a < 50 or b < 50 or a > 200 or b > 200:
            continue
        left = (m.group(1) or "").strip()
        right = (m.group(4) or "").strip()
        clue = re.sub(r"\s+", " ", f"{left} {a}:{b} {right}".strip())
        if not clue or clue in seen:
            continue
        seen.add(clue)
        out.append(clue)
        if len(out) >= 8:
            break
    return out

def _looks_like_link_dump_answer(answer: str) -> bool:
    text = (answer or "").strip().lower()
    if not text:
        return False
    bad_signals = [
        "可以在多个网站",
        "以下是一些可供参考的网站",
        "您可以访问这些网站",
        "你可以访问这些网站",
        "网站查询到",
        "duckduckgo",
        "yahoo",
    ]
    return any(sig in text for sig in bad_signals)

def _compose_web_first_answer(query: str, results: list[WebSearchResult]) -> str:
    if not results:
        return ""
    score_clues: list[str] = []
    highlights: list[str] = []
    seen_highlights: set[str] = set()
    for row in results[:10]:
        blob = f"{row.title} {row.snippet}".strip()
        for clue in _extract_score_clues(blob):
            if clue not in score_clues:
                score_clues.append(clue)
            if len(score_clues) >= 6:
                break
        snippet = (row.snippet or "").strip()
        if snippet:
            line = f"{row.title}：{snippet}"
            if line not in seen_highlights:
                seen_highlights.add(line)
                highlights.append(line)
        if len(highlights) >= 4 and len(score_clues) >= 6:
            break

    if score_clues:
        return (
            f"我先联网检索了“{query.strip()}”，当前抓到的比分线索如下：\n"
            + "\n".join(f"- {item}" for item in score_clues[:6])
            + "\n\n这些来自公开网页抓取，若你愿意我可以继续自动跟踪并持续更新。"
        )
    if highlights:
        return (
            f"我已经先联网检索了“{query.strip()}”。目前可确认的信息：\n"
            + "\n".join(f"- {item}" for item in highlights[:4])
            + "\n\n如果你希望，我可以继续自动跟踪这个主题。"
        )
    first = results[0]
    return (
        f"我已经先联网检索了“{query.strip()}”，但当前抓到的结果细节不足以直接下结论。"
        f"\n\n目前最相关线索：{first.title}（{_domain_from_url(first.url)}）"
        "\n\n我可以继续补抓更高质量的结果后再给你更具体的答案。"
    )

def _rule_based_chat_answer(query: str, *, memory_summary: str = "", brief_summary: str = "") -> str:
    q = (query or "").strip()
    if not q:
        return "我在。你可以直接告诉我想聊什么，或让我帮你跟进某个来源的更新。"
    if any(token in q.lower() for token in ["你好", "hi", "hello"]):
        return "你好，我在这。你可以把我当作长期记忆型助手，聊想法或让我去跟进你的信息源都可以。"
    if re.search(r"[?？吗么嘛]$", q) or "是不是" in q or "有没有" in q:
        base = f"先给你直接结论：围绕“{q[:36]}”，我建议先以当前上下文做判断，再按需补证据。"
    elif any(token in q for token in ["怎么看", "看法", "觉得", "为什么", "如何", "怎么"]):
        base = f"我的直接看法是：关于“{q[:36]}”，要先抓住最近变化，再结合你长期关注点来判断。"
    else:
        base = f"直接回答：你提到的“{q[:36]}”可以先按当前已知信息处理。"
    if memory_summary:
        base += "\n\n我也会参考你已有的长期记忆来保持上下文连续。"
    if brief_summary:
        base += f"\n\n如果你需要，我也可以基于今日简报继续展开：{brief_summary}"
    base += "\n\n如果问题涉及外部事实，我会先自动检索，再直接给你结论。"
    return base

def _looks_like_non_answer(answer: str) -> bool:
    text = re.sub(r"\s+", " ", (answer or "").strip().lower())
    if not text:
        return True
    bad_starts = (
        "这是个好问题",
        "我也会参考你已有的长期记忆",
        "如果你需要",
        "可以直接说",
        "帮我检索相关更新",
    )
    if any(text.startswith(s) for s in bad_starts):
        return True
    if "帮你检索" in text and ("结论" not in text and "回答" not in text):
        return True
    if "你可以手动" in text:
        return True
    if len(text) < 24:
        return True
    return False
