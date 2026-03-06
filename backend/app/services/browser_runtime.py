from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.settings import settings


class BrowserRuntimeBackend(Protocol):
    name: str

    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        max_items: int,
        pid: int = 0,
    ) -> dict[str, Any]: ...

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        include_dom: bool,
        include_a11y: bool,
        max_targets: int,
        max_items: int,
        pid: int = 0,
        profile_id: str = "",
    ) -> dict[str, Any]: ...

    def use(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        scope: str,
        profile_id: str = "",
    ) -> dict[str, Any]: ...

    def force_restart_to_cdp(
        self,
        *,
        timeout_seconds: float,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]: ...


@dataclass
class BrowserRuntimeService:
    backend: BrowserRuntimeBackend

    @property
    def name(self) -> str:
        return str(getattr(self.backend, "name", "") or "unknown")

    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        max_items: int,
        pid: int = 0,
    ) -> dict[str, Any]:
        return self.backend.list_sessions(
            user_id=user_id,
            workspace=workspace,
            scope=scope,
            max_items=max_items,
            pid=pid,
        )

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        include_dom: bool,
        include_a11y: bool,
        max_targets: int,
        max_items: int,
        pid: int = 0,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return self.backend.state_get(
            user_id=user_id,
            workspace=workspace,
            scope=scope,
            include_dom=include_dom,
            include_a11y=include_a11y,
            max_targets=max_targets,
            max_items=max_items,
            pid=pid,
            profile_id=profile_id,
        )

    def use(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        scope: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return self.backend.use(
            user_id=user_id,
            workspace=workspace,
            action=action,
            args=args,
            scope=scope,
            profile_id=profile_id,
        )

    def force_restart_to_cdp(
        self,
        *,
        timeout_seconds: float,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return self.backend.force_restart_to_cdp(
            timeout_seconds=timeout_seconds,
            user_id=user_id,
            workspace=workspace,
            profile_id=profile_id,
        )


class PlaywrightBrowserRuntimeBackend:
    name = "playwright"

    def __init__(self) -> None:
        from app.services.browser_automation import browser_automation_service

        self._service = browser_automation_service

    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        max_items: int,
        pid: int = 0,
    ) -> dict[str, Any]:
        return self._service.list_sessions(
            user_id=user_id,
            workspace=workspace,
            scope=scope,
            max_items=max_items,
            pid=pid,
        )

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        include_dom: bool,
        include_a11y: bool,
        max_targets: int,
        max_items: int,
        pid: int = 0,
        profile_id: str = "",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "workspace": workspace,
            "scope": scope,
            "include_dom": include_dom,
            "include_a11y": include_a11y,
            "max_targets": max_targets,
            "max_items": max_items,
            "pid": pid,
        }
        if profile_id:
            kwargs["profile_id"] = profile_id
        return self._service.state_get(**kwargs)

    def use(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        scope: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "workspace": workspace,
            "action": action,
            "args": args,
            "scope": scope,
        }
        if profile_id:
            kwargs["profile_id"] = profile_id
        return self._service.use(**kwargs)

    def force_restart_to_cdp(
        self,
        *,
        timeout_seconds: float,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "timeout_seconds": timeout_seconds,
            "user_id": user_id,
            "workspace": workspace,
        }
        if profile_id:
            kwargs["profile_id"] = profile_id
        return self._service.force_restart_to_cdp(**kwargs)


def create_browser_runtime_service() -> BrowserRuntimeService:
    backend_name = str(getattr(settings, "browser_runtime_backend", "playwright") or "playwright").strip().lower()
    if backend_name == "playwright":
        return BrowserRuntimeService(backend=PlaywrightBrowserRuntimeBackend())
    raise RuntimeError(f"unsupported_browser_runtime_backend:{backend_name}")


browser_runtime_service = create_browser_runtime_service()
