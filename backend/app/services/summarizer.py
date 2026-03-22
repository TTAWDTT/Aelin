from __future__ import annotations

import re


class RuleBasedSummarizer:
    def summarize(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        if not cleaned:
            return ""
        if len(cleaned) <= 160:
            return cleaned
        return f"{cleaned[:157]}..."
