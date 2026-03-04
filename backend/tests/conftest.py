from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure `backend/` is on sys.path so `import app.*` works reliably across pytest import modes.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_PYTEST_RUNTIME_ROOT = BACKEND_DIR / "_pytest_runtime"
_PYTEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _make_runtime_dir(root: Path, prefix: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = root / f"{prefix}{uuid4().hex[:10]}"
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            continue


@pytest.fixture(scope="session", autouse=True)
def _patch_tempfile_for_windows_acl():
    if os.name != "nt":
        yield
        return

    original_mkdtemp = tempfile.mkdtemp
    original_tempdir_cls = tempfile.TemporaryDirectory

    def _safe_mkdtemp(suffix: str | None = None, prefix: str | None = None, dir: str | None = None) -> str:
        root = Path(str(dir or tempfile.gettempdir()))
        root.mkdir(parents=True, exist_ok=True)
        safe_prefix = str(prefix or "tmp-")
        safe_suffix = str(suffix or "")
        while True:
            candidate = root / f"{safe_prefix}{uuid4().hex[:10]}{safe_suffix}"
            try:
                candidate.mkdir(parents=False, exist_ok=False)
                return str(candidate)
            except FileExistsError:
                continue

    class _SafeTemporaryDirectory:
        def __init__(
            self,
            suffix: str | None = None,
            prefix: str | None = None,
            dir: str | None = None,
            ignore_cleanup_errors: bool = False,
            **kwargs: object,
        ) -> None:
            self.name = _safe_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
            self._ignore_cleanup_errors = bool(ignore_cleanup_errors)
            self._delete = bool(kwargs.get("delete", True))
            self._closed = False

        def __enter__(self) -> str:
            return self.name

        def __exit__(self, exc_type, exc, tb) -> None:
            self.cleanup()

        def cleanup(self) -> None:
            if self._closed:
                return
            self._closed = True
            if not self._delete:
                return
            shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)

        def __del__(self) -> None:
            self.cleanup()

    tempfile.mkdtemp = _safe_mkdtemp  # type: ignore[assignment]
    tempfile.TemporaryDirectory = _SafeTemporaryDirectory  # type: ignore[assignment]
    try:
        yield
    finally:
        tempfile.mkdtemp = original_mkdtemp  # type: ignore[assignment]
        tempfile.TemporaryDirectory = original_tempdir_cls  # type: ignore[assignment]


@pytest.fixture(scope="session", autouse=True)
def _force_local_temp_runtime():
    if os.name != "nt":
        yield
        return

    temp_root = _PYTEST_RUNTIME_ROOT / "runtime"
    temp_dir = str(_make_runtime_dir(temp_root, "session-"))
    old_tempdir = tempfile.tempdir
    old_env = {k: os.environ.get(k) for k in ("TMP", "TEMP", "TMPDIR")}
    try:
        for key in ("TMP", "TEMP", "TMPDIR"):
            os.environ[key] = temp_dir
        tempfile.tempdir = temp_dir
        yield
    finally:
        tempfile.tempdir = old_tempdir
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def tmp_path(tmp_path_factory):
    if os.name != "nt":
        yield tmp_path_factory.mktemp("case")
        return
    # Override pytest's built-in tmp_path fixture on Windows in this repo.
    # Default fixture creates 0o700 directories that are inaccessible here.
    path = _make_runtime_dir(_PYTEST_RUNTIME_ROOT / "tmp_path", "case-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _test_media_dir(monkeypatch):
    from app.settings import settings

    path = _make_runtime_dir(_PYTEST_RUNTIME_ROOT / "media", "aelin-test-media-")
    monkeypatch.setattr(settings, "media_dir", str(path))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _test_default_aelin_flags(monkeypatch):
    from app.settings import settings

    # Tests should remain deterministic and not depend on runtime hard-fail defaults.
    monkeypatch.setattr(settings, "aelin_agent_loop_hard_fail", False)
