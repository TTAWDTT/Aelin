from __future__ import annotations

import threading
import time

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
