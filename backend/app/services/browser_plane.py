from __future__ import annotations

from uuid import uuid4
from typing import Any

from app.services.browser_automation import browser_automation_service
from app.services.browser_exec import run_sync_playwright_call
from app.services.browser_plane_task_store import browser_plane_task_store


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

    def task_create(
        self,
        *,
        user_id: int,
        workspace: str,
        kind: str,
        scope: str,
        action: str,
        input_payload: dict[str, Any],
        profile_id: str = "",
        tab_id: str = "",
    ) -> dict[str, Any]:
        task_id = f"btask-{uuid4().hex[:12]}"
        return browser_plane_task_store.create_task(
            task_id=task_id,
            user_id=int(user_id),
            workspace=workspace,
            profile_id=str(profile_id or ""),
            tab_id=str(tab_id or ""),
            kind=str(kind or "browser_use"),
            status="pending",
            scope=str(scope or "auto"),
            action=str(action or ""),
            input_payload=dict(input_payload or {}),
        )

    def task_get(
        self,
        *,
        user_id: int,
        workspace: str,
        task_id: str,
    ) -> dict[str, Any]:
        return browser_plane_task_store.get_task(
            task_id=task_id,
            user_id=int(user_id),
            workspace=workspace,
        )

    def task_resume(
        self,
        *,
        user_id: int,
        workspace: str,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.task_get(user_id=user_id, workspace=workspace, task_id=task_id)
        if not task:
            return {}

        kind = str(task.get("kind") or "").strip().lower()
        scope = str(task.get("scope") or "auto").strip().lower() or "auto"
        action = str(task.get("action") or "").strip().lower()
        input_payload = task.get("input") if isinstance(task.get("input"), dict) else {}
        profile_id = str(task.get("profile_id") or "").strip()

        if kind == "browser_use":
            result = self.use(
                user_id=int(user_id),
                workspace=workspace,
                action=action,
                args=dict(input_payload),
                scope=scope,
                profile_id=profile_id,
            )
        elif kind == "browser_state_get":
            result = self.state_get(
                user_id=int(user_id),
                workspace=workspace,
                scope=scope,
                include_dom=bool(input_payload.get("include_dom", False)),
                include_a11y=bool(input_payload.get("include_a11y", False)),
                max_targets=int(input_payload.get("max_targets") or 30),
                max_items=int(input_payload.get("max_items") or 20),
                pid=int(input_payload.get("pid") or 0),
                profile_id=profile_id,
            )
        else:
            result = {"ok": False, "error": f"unsupported_browser_task_kind:{kind}"}

        checkpoint_request_id = str(result.get("login_request_id") or "")
        status = "completed"
        if not bool(result.get("ok")):
            status = "blocked" if checkpoint_request_id or bool(result.get("requires_confirmation")) else "failed"
        updated = browser_plane_task_store.update_task(
            task_id=task_id,
            user_id=int(user_id),
            workspace=workspace,
            status=status,
            result_payload=result if isinstance(result, dict) else {},
            checkpoint_request_id=checkpoint_request_id,
            profile_id=str(result.get("profile_id") or profile_id or ""),
        )
        return updated

    def snapshot_get(
        self,
        *,
        user_id: int,
        workspace: str,
        task_id: str = "",
        scope: str = "auto",
        include_dom: bool = False,
        include_a11y: bool = False,
        max_targets: int = 30,
        max_items: int = 20,
        pid: int = 0,
        profile_id: str = "",
    ) -> dict[str, Any]:
        effective_profile_id = str(profile_id or "").strip()
        effective_scope = str(scope or "auto").strip().lower() or "auto"
        if task_id:
            task = self.task_get(user_id=user_id, workspace=workspace, task_id=task_id)
            if task:
                effective_profile_id = effective_profile_id or str(task.get("profile_id") or "").strip()
                effective_scope = str(task.get("scope") or effective_scope or "auto").strip().lower() or "auto"
        snap = self.state_get(
            user_id=int(user_id),
            workspace=workspace,
            scope=effective_scope,
            include_dom=bool(include_dom),
            include_a11y=bool(include_a11y),
            max_targets=int(max_targets),
            max_items=int(max_items),
            pid=int(pid),
            profile_id=effective_profile_id,
        )
        if isinstance(snap, dict):
            snap = dict(snap)
            if task_id:
                snap["task_id"] = str(task_id)
        return snap


browser_plane_adapter = BrowserPlaneAdapter()
