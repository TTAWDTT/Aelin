from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure `backend/` is on sys.path so `import app.*` works reliably across pytest import modes.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def _test_default_aelin_flags(monkeypatch):
    from app.settings import settings

    # Tests should remain deterministic and not depend on runtime hard-fail defaults.
    monkeypatch.setattr(settings, "aelin_agent_loop_hard_fail", False)
