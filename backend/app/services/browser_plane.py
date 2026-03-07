from __future__ import annotations

from typing import Any

from app.services.browser_automation import browser_automation_service
from app.services.browser_exec import run_sync_playwright_call


class BrowserPlaneAdapter:
    """Adapter boundary between Aelin orchestration and the current browser runtime.

    Today this wraps the in-process browser automation service. Later it can be
    replaced with a true browser-plane client without forcing the rest of the
    orchestration layer to know the runtime details.
    """

    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str,
        max_items: int,
        pid: int = 0,
    ) -> dict[str, Any]:
        return run_sync_playwright_call(
            browser_automation_service.list_sessions,
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
        return run_sync_playwright_call(browser_automation_service.state_get, **kwargs)

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
        return run_sync_playwright_call(browser_automation_service.use, **kwargs)

    def list_login_states(
        self,
        *,
        user_id: int,
        workspace: str = "",
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return browser_automation_service.list_login_states(
            user_id=user_id,
            workspace=workspace,
            statuses=statuses,
            limit=limit,
        )

    def get_login_state(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return browser_automation_service.get_login_state(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
        )

    def attach_login_resume_context(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
        resume_query: str = "",
        resume_request: dict[str, Any] | None = None,
        continue_after_confirm: bool | None = None,
    ) -> dict[str, Any]:
        return browser_automation_service.attach_login_resume_context(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
            resume_query=resume_query,
            resume_request=resume_request,
            continue_after_confirm=continue_after_confirm,
        )

    def resolve_login_pending(
        self,
        *,
        user_id: int,
        workspace: str,
        request_id: str,
        profile_id: str = "",
        status: str = "resolved",
    ) -> dict[str, Any]:
        return browser_automation_service.resolve_login_pending(
            user_id=user_id,
            workspace=workspace,
            request_id=request_id,
            profile_id=profile_id,
            status=status,
        )

    def force_restart_to_cdp(
        self,
        *,
        timeout_seconds: float,
        user_id: int,
        workspace: str,
        profile_id: str = "",
    ) -> dict[str, Any]:
        return browser_automation_service.force_restart_to_cdp(
            timeout_seconds=timeout_seconds,
            user_id=user_id,
            workspace=workspace,
            profile_id=profile_id,
        )


browser_plane_adapter = BrowserPlaneAdapter()
