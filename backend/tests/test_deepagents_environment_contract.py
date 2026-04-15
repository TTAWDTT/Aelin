from __future__ import annotations

import pytest
from packaging.version import Version

from app.services.deepagents import environment_contract as env


def test_validate_deepagents_environment_accepts_current_stack():
    env.validate_deepagents_environment.cache_clear()
    info = env.validate_deepagents_environment()
    assert Version(info["deepagents"]) >= Version("0.4.11")
    assert Version(info["langsmith"]) >= Version("0.6.3")


def test_validate_deepagents_environment_rejects_unsupported_deepagents(monkeypatch):
    env.validate_deepagents_environment.cache_clear()

    def _fake_load_version(name: str) -> Version:
        if name == "deepagents":
            return Version("0.4.10")
        if name == "langsmith":
            return Version("0.6.3")
        raise AssertionError(name)

    class _CompatibleCompositeBackend:
        adownload_files = object()
        aupload_files = object()
        als_info = object()

    monkeypatch.setattr(env, "_load_version", _fake_load_version)
    monkeypatch.setattr(env, "CompositeBackend", _CompatibleCompositeBackend)

    with pytest.raises(RuntimeError, match="Unsupported `deepagents` version"):
        env.validate_deepagents_environment()


def test_validate_deepagents_environment_rejects_incompatible_backend_api(monkeypatch):
    env.validate_deepagents_environment.cache_clear()

    def _fake_load_version(name: str) -> Version:
        if name == "deepagents":
            return Version("0.4.11")
        if name == "langsmith":
            return Version("0.6.3")
        raise AssertionError(name)

    class _IncompatibleCompositeBackend:
        adownload_files = object()

    monkeypatch.setattr(env, "_load_version", _fake_load_version)
    monkeypatch.setattr(env, "CompositeBackend", _IncompatibleCompositeBackend)

    with pytest.raises(RuntimeError, match="CompositeBackend` is missing"):
        env.validate_deepagents_environment()
