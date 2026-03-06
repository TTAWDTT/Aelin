from __future__ import annotations

import atexit
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

_BROWSER_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aelin-browser-tool")
_BROWSER_INFLIGHT_SEMAPHORE = threading.BoundedSemaphore(value=8)
_BROWSER_INFLIGHT_ACQUIRE_TIMEOUT_SECONDS = 0.25


def _shutdown_browser_thread_pool() -> None:
    try:
        _BROWSER_THREAD_POOL.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass


atexit.register(_shutdown_browser_thread_pool)


def has_running_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except Exception:
        return False


def run_in_browser_thread(callable_obj, *args: Any, timeout: int = 45, **kwargs: Any):
    acquired = _BROWSER_INFLIGHT_SEMAPHORE.acquire(timeout=_BROWSER_INFLIGHT_ACQUIRE_TIMEOUT_SECONDS)
    if not acquired:
        raise RuntimeError("browser_tool_busy")

    release_lock = threading.Lock()
    released = False

    def _release_slot() -> None:
        nonlocal released
        with release_lock:
            if released:
                return
            released = True
        _BROWSER_INFLIGHT_SEMAPHORE.release()

    try:
        future = _BROWSER_THREAD_POOL.submit(callable_obj, *args, **kwargs)
    except Exception:
        _release_slot()
        raise

    future.add_done_callback(lambda _future: _release_slot())
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        future.cancel()
        raise RuntimeError("browser_tool_timeout") from exc


def run_sync_playwright_call(callable_obj, *args: Any, timeout: int = 45, **kwargs: Any):
    """Run sync Playwright-backed calls off-thread when the current thread already owns an event loop."""
    if not has_running_event_loop():
        return callable_obj(*args, **kwargs)
    return run_in_browser_thread(callable_obj, *args, timeout=timeout, **kwargs)
