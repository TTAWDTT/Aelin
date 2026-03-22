from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.models import AttachmentChunk


def write_storage_if_missing(storage_path: Path, content: bytes) -> bool:
    """
    Atomically write attachment bytes to disk if the target path does not exist.

    This is extracted from AelinAttachmentService to keep the main service
    focused on orchestration rather than low-level filesystem details.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= int(getattr(os, "O_BINARY"))
    try:
        fd = os.open(str(storage_path), flags)
    except FileExistsError:
        return False
    handle = None
    try:
        handle = os.fdopen(fd, "wb")
        handle.write(content)
        handle.close()
        handle = None
    except Exception:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        else:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            storage_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return True


def build_chunk_rows(
    *,
    chunks: Iterable[str],
    loc_template: dict[str, Any],
    safe_json,
) -> list[dict[str, Any]]:
    """
    Small helper to build AttachmentChunk rows from text pieces.

    The caller is responsible for splitting text into chunks and passing a
    location template that will be JSON-serialised for each chunk.
    """
    rows: list[dict[str, Any]] = []
    chunk_idx = 0
    for piece in chunks:
        tokens = piece.split()
        vec = Counter(tokens)
        rows.append(
            {
                "chunk_index": chunk_idx,
                "text": piece,
                "token_count": len(tokens),
                "keyword_vector_json": safe_json(dict(vec.most_common(64))),
                "loc_json": safe_json(dict(loc_template or {})),
            }
        )
        chunk_idx += 1
    return rows


