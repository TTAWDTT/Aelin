from __future__ import annotations

import importlib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version

from packaging.version import Version

from deepagents.backends.composite import CompositeBackend


_SUPPORTED_DEEPAGENTS_MIN = Version("0.4.11")
_SUPPORTED_DEEPAGENTS_MAX = Version("0.5.0")
_SUPPORTED_LANGSMITH_MIN = Version("0.6.3")
_SUPPORTED_LANGSMITH_MAX = Version("0.7.0")


def _format_range(min_version: Version, max_version: Version) -> str:
    return f">={min_version},<{max_version}"


def _load_version(name: str) -> Version:
    try:
        return Version(package_version(name))
    except PackageNotFoundError as exc:  # pragma: no cover - depends on host environment
        module_name = str(name or "").replace("-", "_")
        try:
            module = importlib.import_module(module_name)
        except Exception:
            module = None
        raw_version = str(getattr(module, "__version__", "") or "").strip() if module is not None else ""
        if raw_version:
            return Version(raw_version)
        raise RuntimeError(
            f"Aelin requires `{name}` to be installed. Run `cd backend && python -m pip install -r requirements.txt`."
        ) from exc


@lru_cache(maxsize=1)
def validate_deepagents_environment() -> dict[str, str]:
    deepagents_version = _load_version("deepagents")
    langsmith_version = _load_version("langsmith")

    if not (_SUPPORTED_DEEPAGENTS_MIN <= deepagents_version < _SUPPORTED_DEEPAGENTS_MAX):
        raise RuntimeError(
            "Unsupported `deepagents` version for Aelin. "
            f"Detected {deepagents_version}, expected {_format_range(_SUPPORTED_DEEPAGENTS_MIN, _SUPPORTED_DEEPAGENTS_MAX)}."
        )

    if not (_SUPPORTED_LANGSMITH_MIN <= langsmith_version < _SUPPORTED_LANGSMITH_MAX):
        raise RuntimeError(
            "Unsupported `langsmith` version for Aelin. "
            f"Detected {langsmith_version}, expected {_format_range(_SUPPORTED_LANGSMITH_MIN, _SUPPORTED_LANGSMITH_MAX)}."
        )

    missing_attrs = [
        attr
        for attr in ("adownload_files", "aupload_files", "als_info")
        if not hasattr(CompositeBackend, attr)
    ]
    if missing_attrs:
        joined = ", ".join(missing_attrs)
        raise RuntimeError(
            "Installed `deepagents` backend API is incompatible with Aelin. "
            f"`CompositeBackend` is missing: {joined}. "
            f"Expected deepagents {_format_range(_SUPPORTED_DEEPAGENTS_MIN, _SUPPORTED_DEEPAGENTS_MAX)}."
        )

    return {
        "deepagents": str(deepagents_version),
        "langsmith": str(langsmith_version),
    }
