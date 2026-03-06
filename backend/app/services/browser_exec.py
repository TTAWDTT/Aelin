from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any


def has_running_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except Exception:
        return False


def run_in_browser_thread(callable_obj, *args: Any, timeout: int = 45, **kwargs: Any):
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="aelin-browser-tool") as pool:
        future = pool.submit(callable_obj, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            raise RuntimeError("browser_tool_timeout") from exc


def run_sync_playwright_call(callable_obj, *args: Any, timeout: int = 45, **kwargs: Any):
    """Run sync Playwright-backed calls off-thread when the current thread already owns an event loop."""
    if not has_running_event_loop():
        return callable_obj(*args, **kwargs)
    return run_in_browser_thread(callable_obj, *args, timeout=timeout, **kwargs)
