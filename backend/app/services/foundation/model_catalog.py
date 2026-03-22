from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import httpx

from app.schemas import ModelCatalogResponse, ModelInfo, ModelProviderInfo
from app.settings import settings


@dataclass
class _CatalogCache:
    fetched_at: datetime | None = None
    data: ModelCatalogResponse | None = None


_cache = _CatalogCache()
_cache_lock = Lock()


def _fallback_catalog() -> ModelCatalogResponse:
    now = datetime.now(timezone.utc)
    return ModelCatalogResponse(
        source_url=settings.models_catalog_url,
        fetched_at=now,
        providers=[
            ModelProviderInfo(
                id="openai",
                name="OpenAI",
                api="https://api.openai.com/v1",
                doc="https://platform.openai.com/docs/models",
                env=["OPENAI_API_KEY"],
                model_count=3,
                models=[
                    ModelInfo(id="gpt-4o-mini", name="GPT-4o mini"),
                    ModelInfo(id="gpt-4.1-mini", name="GPT-4.1 mini"),
                    ModelInfo(id="gpt-5-mini", name="GPT-5 mini"),
                ],
            )
        ],
    )


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_provider(provider_id: str, payload: Any) -> ModelProviderInfo:
    models_obj = payload.get("models") if isinstance(payload, dict) else None
    models: list[ModelInfo] = []
    if isinstance(models_obj, dict):
        for model_id, model_payload in models_obj.items():
            info = model_payload if isinstance(model_payload, dict) else {}
            models.append(
                ModelInfo(
                    id=str(model_id),
                    name=str(info.get("name") or model_id),
                    family=str(info.get("family") or "") or None,
                    reasoning=bool(info["reasoning"]) if "reasoning" in info else None,
                    tool_call=bool(info["tool_call"]) if "tool_call" in info else None,
                    temperature=bool(info["temperature"]) if "temperature" in info else None,
                )
            )
    models.sort(key=lambda m: m.name.lower())

    return ModelProviderInfo(
        id=str(payload.get("id") or provider_id),
        name=str(payload.get("name") or provider_id),
        api=str(payload.get("api") or "") or None,
        doc=str(payload.get("doc") or "") or None,
        env=_as_str_list(payload.get("env") if isinstance(payload, dict) else []),
        model_count=len(models),
        models=models,
    )


def _download_catalog() -> ModelCatalogResponse:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(settings.models_catalog_url)
    resp.raise_for_status()
    raw = resp.json()
    if not isinstance(raw, dict):
        raise ValueError("models catalog payload is not an object")

    providers: list[ModelProviderInfo] = []
    for provider_id, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        providers.append(_normalize_provider(provider_id, payload))
    providers.sort(key=lambda p: p.name.lower())

    return ModelCatalogResponse(
        source_url=settings.models_catalog_url,
        fetched_at=datetime.now(timezone.utc),
        providers=providers,
    )


def get_model_catalog(*, force_refresh: bool = False) -> ModelCatalogResponse:
    with _cache_lock:
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and _cache.data is not None
            and _cache.fetched_at is not None
            and now - _cache.fetched_at < timedelta(seconds=max(60, settings.models_catalog_refresh_seconds))
        ):
            return _cache.data

    try:
        catalog = _download_catalog()
    except Exception:
        catalog = _fallback_catalog()

    with _cache_lock:
        _cache.data = catalog
        _cache.fetched_at = catalog.fetched_at
    return catalog
