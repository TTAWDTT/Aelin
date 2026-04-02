from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from typing import Any

from app.services.deepagents.tools.runtime_context import ToolRuntimeContext


_TOOL_EXECUTOR_MAX_WORKERS = 4
_TOOL_EXECUTOR_SLOT_WAIT_SECONDS = 0.25
_TOOL_EXECUTOR: ThreadPoolExecutor | None = None
_TOOL_EXECUTOR_SEMAPHORE: threading.BoundedSemaphore | None = None
_TOOL_EXECUTOR_LOCK = threading.Lock()


def _ensure_tool_executor() -> tuple[ThreadPoolExecutor, threading.BoundedSemaphore]:
    global _TOOL_EXECUTOR, _TOOL_EXECUTOR_SEMAPHORE
    with _TOOL_EXECUTOR_LOCK:
        if _TOOL_EXECUTOR is None or _TOOL_EXECUTOR_SEMAPHORE is None:
            max_workers = max(1, int(_TOOL_EXECUTOR_MAX_WORKERS or 1))
            _TOOL_EXECUTOR = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="deepagents-tool",
            )
            _TOOL_EXECUTOR_SEMAPHORE = threading.BoundedSemaphore(max_workers)
        return _TOOL_EXECUTOR, _TOOL_EXECUTOR_SEMAPHORE


def _acquire_tool_executor_slot() -> tuple[ThreadPoolExecutor, threading.BoundedSemaphore] | None:
    executor, semaphore = _ensure_tool_executor()
    acquired = semaphore.acquire(timeout=max(0.0, float(_TOOL_EXECUTOR_SLOT_WAIT_SECONDS)))
    if not acquired:
        return None
    return executor, semaphore


def _submit_tool_future(
    executor: ThreadPoolExecutor,
    semaphore: threading.BoundedSemaphore,
    handler: Any,
    context: ToolRuntimeContext,
    args: dict[str, Any],
) -> Future:
    ctx = copy_context()
    try:
        future = executor.submit(ctx.run, handler, context, args)
    except Exception:
        semaphore.release()
        raise

    def _release_slot(_future: Future) -> None:
        try:
            semaphore.release()
        except Exception:
            pass

    future.add_done_callback(_release_slot)
    return future


def _reset_tool_executor_for_tests(max_workers: int = 4) -> None:
    global _TOOL_EXECUTOR, _TOOL_EXECUTOR_SEMAPHORE, _TOOL_EXECUTOR_MAX_WORKERS
    with _TOOL_EXECUTOR_LOCK:
        old_executor = _TOOL_EXECUTOR
        _TOOL_EXECUTOR = None
        _TOOL_EXECUTOR_SEMAPHORE = None
        _TOOL_EXECUTOR_MAX_WORKERS = max(1, int(max_workers or 1))
    if old_executor is not None:
        old_executor.shutdown(wait=False, cancel_futures=True)
