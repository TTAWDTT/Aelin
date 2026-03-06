from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services import browser_exec


def test_run_in_browser_thread_returns_result():
    out = browser_exec.run_in_browser_thread(lambda value: value + 1, 2, timeout=1)
    assert out == 3


def test_run_in_browser_thread_timeout_does_not_wait_for_completion():
    started = threading.Event()
    release = threading.Event()

    def _slow_call():
        started.set()
        release.wait(timeout=5.0)
        return "done"

    begin = time.perf_counter()
    with pytest.raises(RuntimeError, match="browser_tool_timeout"):
        browser_exec.run_in_browser_thread(_slow_call, timeout=0.05)
    elapsed = time.perf_counter() - begin

    assert started.wait(timeout=1.0) is True
    assert elapsed < 0.5
    release.set()


def test_run_in_browser_thread_returns_busy_when_inflight_slots_are_exhausted(monkeypatch):
    original_pool = browser_exec._BROWSER_THREAD_POOL
    original_semaphore = browser_exec._BROWSER_INFLIGHT_SEMAPHORE

    monkeypatch.setattr(
        browser_exec,
        "_BROWSER_THREAD_POOL",
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-browser-exec"),
    )
    monkeypatch.setattr(browser_exec, "_BROWSER_INFLIGHT_SEMAPHORE", threading.BoundedSemaphore(value=1))
    monkeypatch.setattr(browser_exec, "_BROWSER_INFLIGHT_ACQUIRE_TIMEOUT_SECONDS", 0.05)

    started = threading.Event()
    release = threading.Event()
    worker_done = threading.Event()

    def _slow_call():
        started.set()
        release.wait(timeout=5.0)
        return "done"

    def _run_slow():
        try:
            browser_exec.run_in_browser_thread(_slow_call, timeout=1.0)
        finally:
            worker_done.set()

    thread = threading.Thread(target=_run_slow, daemon=True)
    thread.start()
    assert started.wait(timeout=1.0) is True

    begin = time.perf_counter()
    with pytest.raises(RuntimeError, match="browser_tool_busy"):
        browser_exec.run_in_browser_thread(lambda: "never-runs", timeout=1.0)
    elapsed = time.perf_counter() - begin

    assert elapsed < 0.5
    release.set()
    assert worker_done.wait(timeout=2.0) is True

    browser_exec._BROWSER_THREAD_POOL.shutdown(wait=True, cancel_futures=True)
    monkeypatch.setattr(browser_exec, "_BROWSER_THREAD_POOL", original_pool)
    monkeypatch.setattr(browser_exec, "_BROWSER_INFLIGHT_SEMAPHORE", original_semaphore)
