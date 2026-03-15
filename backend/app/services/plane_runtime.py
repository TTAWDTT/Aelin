from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session


class PlaneAdapter(Protocol):
    def delegate(self, *, goal: str) -> dict[str, Any]: ...

    def status(self, *, task_id: str) -> dict[str, Any]: ...

    def continue_task(self, *, task_id: str, goal: str) -> dict[str, Any]: ...

    def close(self, *, task_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PlaneMetadata:
    slug: str
    name: str
    backing_system: str
    summary: str
    delegation_hint: str
    when_to_use: tuple[str, ...]
    actions: tuple[str, ...]
    skill_slug: str = ""


@dataclass(frozen=True)
class PlaneRegistryEntry:
    metadata: PlaneMetadata
    adapter_factory: Callable[..., PlaneAdapter]


def _build_browser_plane_adapter(
    *,
    db: Session | None,
    user_id: int,
    workspace: str,
    session_executor: Callable[..., tuple[str, dict[str, Any], str, int]],
) -> PlaneAdapter:
    from app.services.browser_plane_adapter import PinchTabBrowserPlaneAdapter

    return PinchTabBrowserPlaneAdapter(
        db=db,
        user_id=user_id,
        workspace=workspace,
        session_executor=session_executor,
    )


@lru_cache(maxsize=1)
def default_plane_registry() -> tuple[PlaneRegistryEntry, ...]:
    return (
        PlaneRegistryEntry(
            metadata=PlaneMetadata(
                slug="browser",
                name="Browser Plane",
                backing_system="PinchTab",
                summary="负责网页登录、导航、滚动、抽取页面内容等复杂浏览器任务。",
                delegation_hint="复杂网站任务优先整单委派给 browser plane，而不是自己微操浏览器步骤。",
                when_to_use=(
                    "需要登录网站",
                    "需要多步导航或滚动加载",
                    "需要持续复用同一个网页会话",
                ),
                actions=("catalog", "delegate", "status", "continue", "close"),
                skill_slug="pinchtab",
            ),
            adapter_factory=_build_browser_plane_adapter,
        ),
    )


def get_plane_registry_entry(slug: str) -> PlaneRegistryEntry | None:
    normalized = str(slug or "").strip().lower()
    for entry in default_plane_registry():
        if entry.metadata.slug == normalized:
            return entry
    return None


def plane_catalog_metadata() -> list[PlaneMetadata]:
    return [entry.metadata for entry in default_plane_registry()]
