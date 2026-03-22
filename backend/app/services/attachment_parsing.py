from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Tuple


@dataclass(slots=True)
class ParsedBlock:
    content: str
    block_type: str
    loc: dict[str, Any]


ParsedResult = Tuple[str, list[ParsedBlock], dict[str, Any]]


def normalize_blocks_to_chunks(
    blocks: list[ParsedBlock],
    *,
    chunk_text: Callable[[str], list[str]],
    safe_json: Callable[[Any], str],
) -> list[dict[str, Any]]:
    """
    Helper used by AelinAttachmentService to convert parsed blocks into
    chunk rows, delegating the actual chunk splitting logic.
    """
    from collections import Counter

    rows: list[dict[str, Any]] = []
    chunk_idx = 0
    for block in blocks:
        for piece in chunk_text(block.content):
            tokens = piece.split()
            vec = Counter(tokens)
            rows.append(
                {
                    "chunk_index": chunk_idx,
                    "text": piece,
                    "token_count": len(tokens),
                    "keyword_vector_json": safe_json(dict(vec.most_common(64))),
                    "loc_json": safe_json(dict(block.loc or {})),
                }
            )
            chunk_idx += 1
    return rows


