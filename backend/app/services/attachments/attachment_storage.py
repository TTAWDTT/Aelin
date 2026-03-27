from __future__ import annotations

import os
from pathlib import Path


def write_storage_if_missing(storage_path: Path, content: bytes) -> bool:
    """
    Atomically write attachment bytes to disk if the target path does not exist.

This is extracted from AttachmentService to keep the main service
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
