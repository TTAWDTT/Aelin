from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from pathlib import Path


@dataclass(slots=True)
class OcrConfig:
    min_chars: int
    languages: str


def norm_text(text: str) -> str:
    return " ".join(str(text or "").split())


