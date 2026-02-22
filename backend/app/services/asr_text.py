from __future__ import annotations

import re
from typing import Callable

_ASR_FILLER_RE = re.compile(r"(?i)(?:\b(?:uh|um|erm|ah|oh)\b|[嗯啊呃哈哎呀]{2,})")
_ASR_REPEAT_FRAGMENT_RE = re.compile(r"(.{2,8}?)(?:\1){2,}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
_MULTISPACE_RE = re.compile(r"\s+")


class ASRTextProcessor:
    def __init__(
        self,
        *,
        normalize_text: Callable[[str], str],
        split_sentences: Callable[[str], list[str]],
        is_low_signal_fragment: Callable[[str], bool],
        max_model_input_chars: int,
    ) -> None:
        self._normalize_text = normalize_text
        self._split_sentences = split_sentences
        self._is_low_signal_fragment = is_low_signal_fragment
        self._max_model_input_chars = max(500, int(max_model_input_chars or 12000))

    def sanitize(self, text: str) -> str:
        normalized = self._normalize_text(text)
        if not normalized:
            return ""
        lowered = _ASR_FILLER_RE.sub(" ", normalized)
        lowered = _MULTISPACE_RE.sub(" ", lowered)
        chunks = re.split(r"[。！？!?；;，,\n]+", lowered)

        out: list[str] = []
        seen: set[str] = set()
        total_len = 0
        for chunk in chunks:
            clean = _MULTISPACE_RE.sub(" ", str(chunk or "")).strip(" -|•·")
            if not clean:
                continue
            clean = re.sub(r"(.)\1{4,}", r"\1\1", clean)
            clean = _ASR_REPEAT_FRAGMENT_RE.sub(r"\1", clean)
            clean = _MULTISPACE_RE.sub(" ", clean).strip()
            if len(clean) < 8:
                continue
            if self._is_low_signal_fragment(clean):
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(clean[:220])
            total_len += len(clean)
            if total_len >= self._max_model_input_chars or len(out) >= 24:
                break
        if not out:
            return ""
        return self._normalize_text("。".join(out))

    def noise_score(self, text: str) -> float:
        normalized = self._normalize_text(text)
        if not normalized:
            return 1.0
        compact = re.sub(r"\s+", "", normalized)
        if not compact:
            return 1.0
        repeat_hits = len(_ASR_REPEAT_FRAGMENT_RE.findall(compact[:3000]))
        filler_hits = len(_ASR_FILLER_RE.findall(normalized))
        tokens = _TOKEN_RE.findall(normalized)
        token_count = len(tokens)
        unique_ratio = (len(set(tokens)) / max(1, token_count)) if token_count else 0.0
        sentences = self._split_sentences(normalized)
        short_sentence_count = 0
        for sent in sentences:
            if len(sent) < 14:
                short_sentence_count += 1
        short_sentence_ratio = short_sentence_count / max(1, len(sentences))

        score = 0.0
        score += min(0.6, repeat_hits * 0.14)
        score += min(0.2, filler_hits * 0.02)
        if unique_ratio < 0.28:
            score += min(0.2, (0.28 - unique_ratio) * 1.0)
        score += min(0.2, short_sentence_ratio * 0.25)
        if len(normalized) < 120:
            score += 0.12
        return round(max(0.0, min(1.0, score)), 3)

