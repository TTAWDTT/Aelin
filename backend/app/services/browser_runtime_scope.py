from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.browser_automation import BrowserSession


class BrowserScopeRuntimeMixin:
    def _error_payload(
        self,
        *,
        error: str,
        scope: str = "",
        action: str = "",
        requires_cdp: bool = False,
        hint: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(error or "unknown_error")[:180],
        }
        if scope:
            payload["scope"] = str(scope)[:24]
        if action:
            payload["action"] = str(action)[:24]
        if requires_cdp:
            payload["requires_cdp"] = True
        if hint:
            payload["hint"] = str(hint)[:220]
        return payload

    def _system_scope_payload(self, *, scope: str, proc_limit: int, pid: int) -> dict[str, Any]:
        if proc_limit <= 0:
            return {
                "ok": True,
                "scope": scope,
                "system_processes": [],
                "scope_note": (
                    "系统浏览器进程视图（fast path，未枚举进程详情）。"
                    if scope == "system"
                    else "external scope fast path：未枚举系统进程详情。"
                ),
            }
        return {
            "ok": True,
            "scope": scope,
            "system_processes": self._list_system_browser_processes(
                max_items=proc_limit,
                pid=int(pid or 0),
                include_details=False,
            ),
            "scope_note": (
                "系统浏览器进程视图（不保证可获得每个标签页 URL）。"
                if scope == "system"
                else "external scope 仅能读取系统浏览器进程级状态，无法直接读取 DOM。"
            ),
        }

    def _resolve_state_runtime_scope(
        self,
        *,
        user_scope: str,
        include_dom: bool,
        include_a11y: bool,
        proc_limit: int,
        pid: int,
    ) -> tuple[str, str, dict[str, Any] | None]:
        if user_scope == "system":
            return user_scope, "", self._system_scope_payload(scope=user_scope, proc_limit=proc_limit, pid=pid)
        if user_scope == "external":
            if include_dom or include_a11y:
                return "", "", self._error_payload(
                    error="external_scope_requires_cdp_for_dom",
                    scope="external",
                    requires_cdp=True,
                    hint="external scope 不支持 DOM/A11y 读取，请改用 scope=auto 或 scope=cdp。",
                )
            return user_scope, "", self._system_scope_payload(scope=user_scope, proc_limit=proc_limit, pid=pid)

        if user_scope == "managed":
            return "", "", self._error_payload(
                error="managed_scope_soft_deleted",
                scope="managed",
                hint="managed 已软下线，请改用 scope=cdp 或 scope=external。",
            )

        if user_scope == "cdp":
            if not self._cdp_enabled:
                return "", "cdp_disabled", self._error_payload(
                    error="cdp_disabled",
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未启用受控浏览器（CDP），请先启用后再重试。",
                )
            if not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未配置 CDP 端点，请先完成配置后再重试。",
                )
            return "cdp", "", None

        if user_scope != "auto":
            return "", "", self._error_payload(error=f"unsupported_scope:{user_scope}", scope=user_scope)

        cdp_reachable = bool(
            self._cdp_enabled
            and self._cdp_endpoint
            and self._probe_cdp_endpoint(self._cdp_endpoint, timeout_seconds=0.25)
        )
        if cdp_reachable:
            return "cdp", "", None

        if include_dom or include_a11y:
            if not self._cdp_enabled and not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="auto",
                    requires_cdp=True,
                    hint="当前已软下线 managed；请配置 CDP 端点后重试。",
                )
            if not self._cdp_enabled:
                return "", "cdp_disabled", self._error_payload(
                    error="cdp_disabled",
                    scope="auto",
                    requires_cdp=True,
                    hint="DOM/A11y 读取需要受控浏览器（CDP），当前未启用。",
                )
            if not self._cdp_endpoint:
                return "", "cdp_endpoint_unconfigured", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    scope="auto",
                    requires_cdp=True,
                    hint="当前已软下线 managed；请配置 CDP 端点后重试。",
                )
            return "cdp", "", None

        if not self._cdp_enabled:
            fallback_reason = "cdp_disabled" if self._cdp_endpoint else "cdp_endpoint_unconfigured"
        else:
            fallback_reason = "cdp_probe_failed" if self._cdp_endpoint else "cdp_endpoint_unconfigured"
        if not include_dom and not include_a11y and proc_limit <= 0:
            fast_payload = {
                "ok": True,
                "scope": "external",
                "system_processes": [],
                "scope_note": "CDP 暂不可用，fast path 已返回 external 轻量状态。",
            }
            if fallback_reason:
                fast_payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            return "", fallback_reason, fast_payload

        system_processes = self._list_system_browser_processes(
            max_items=proc_limit,
            pid=int(pid or 0),
            include_details=False,
        )
        if system_processes:
            payload = {
                "ok": True,
                "scope": "external",
                "system_processes": system_processes,
                "scope_note": "检测到用户浏览器正在运行；当前为进程级状态读取，若需 DOM 级读取请启用 CDP。",
            }
            if self._cdp_endpoint:
                payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            return "", fallback_reason, payload

        if not self._cdp_endpoint:
            return "", fallback_reason, self._error_payload(
                error="cdp_endpoint_unconfigured",
                scope="auto",
                requires_cdp=True,
                hint="当前已软下线 managed；请配置 CDP 端点后重试。",
            )
        return "", fallback_reason, self._error_payload(
            error=f"cdp_unavailable:{fallback_reason}",
            scope="auto",
            requires_cdp=True,
            hint="CDP 暂不可用，请稍后重试。",
        )

    def _acquire_cdp_session(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        action: str = "",
        allow_restart_confirmation: bool = False,
        confirmed: bool = False,
        next_args: dict[str, Any] | None = None,
    ) -> tuple[BrowserSession | None, dict[str, Any] | None]:
        try:
            session = self._get_session(user_id=user_id, workspace=workspace, mode="cdp", profile_id=profile_id)
            return session, None
        except Exception as exc:
            reason = str(exc)[:160]
            if allow_restart_confirmation and "cdp_requires_browser_restart" in reason:
                if confirmed:
                    restart_meta = self.force_restart_to_cdp(
                        timeout_seconds=self._recommended_restart_timeout_seconds(),
                        user_id=user_id,
                        workspace=workspace,
                        profile_id=profile_id,
                    )
                    if bool(restart_meta.get("ok")):
                        try:
                            session = self._get_session(
                                user_id=user_id,
                                workspace=workspace,
                                mode="cdp",
                                profile_id=profile_id,
                            )
                            return session, None
                        except Exception as retry_exc:
                            retry_reason = str(retry_exc)[:160]
                            return None, self._error_payload(
                                error=f"cdp_unavailable:{retry_reason}",
                                action=action,
                                scope="cdp",
                            )
                    fail_payload = self._error_payload(
                        error="browser_restart_failed_for_cdp",
                        action=action,
                        scope="cdp",
                    )
                    fail_payload["restart"] = {
                        "attempted": True,
                        "ok": False,
                        "error": str(restart_meta.get("error") or "")[:180],
                        "terminated_pids": list(restart_meta.get("terminated_pids") or []),
                        "killed_pids": list(restart_meta.get("killed_pids") or []),
                        "failed_pids": list(restart_meta.get("failed_pids") or []),
                        "remaining_pids": list(restart_meta.get("remaining_pids") or []),
                    }
                    return None, fail_payload
                confirm_args = dict(next_args or {})
                confirm_args["scope"] = "cdp"
                confirm_args["confirm"] = True
                return None, {
                    "ok": False,
                    "error": "browser_restart_required_for_cdp",
                    "requires_confirmation": True,
                    "confirm_kind": "restart_to_cdp",
                    "risk_level": "medium",
                    "action": action,
                    "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                    "next_call": {
                        "tool": "browser_use",
                        "action": action,
                        "args": confirm_args,
                    },
                }
            return None, self._error_payload(error=f"cdp_unavailable:{reason}", action=action)

    def _resolve_use_runtime_scope(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str,
        action: str,
        args: dict[str, Any],
        user_scope: str,
    ) -> tuple[str, bool, dict[str, Any] | None]:
        runtime_scope = user_scope
        prefer_existing_cdp = False
        sticky_scope = self._get_preferred_scope(user_id=int(user_id), workspace=workspace)

        if runtime_scope == "auto":
            if action == "navigate":
                prefer_existing_cdp = bool(self._cdp_enabled) and (
                    sticky_scope == "cdp"
                    or self._has_reusable_cdp_session(
                        user_id=int(user_id),
                        workspace=workspace,
                        profile_id=profile_id,
                    )
                )
                runtime_scope = "cdp" if prefer_existing_cdp else "external"
            elif self._is_complex_auto_action(action):
                if not self._cdp_enabled:
                    return "", False, self._error_payload(
                        error="cdp_disabled",
                        action=action,
                        scope="auto",
                        requires_cdp=True,
                        hint="该操作需要受控浏览器（CDP），当前未启用。",
                    )
                if not self._cdp_endpoint:
                    return "", False, self._error_payload(
                        error="cdp_endpoint_unconfigured",
                        action=action,
                        scope="auto",
                        requires_cdp=True,
                        hint="该操作需要受控浏览器（CDP），但当前未配置 CDP 端点。",
                    )
                has_system_browser = self._has_system_browser_process()
                cdp_ready = bool(
                    self._cdp_endpoint
                    and self._probe_cdp_endpoint(self._cdp_endpoint, timeout_seconds=0.35)
                )
                if has_system_browser and (not cdp_ready) and not bool(args.get("confirm")):
                    next_args = dict(args or {})
                    next_args["scope"] = "cdp"
                    next_args["confirm"] = True
                    return "", False, {
                        "ok": False,
                        "error": "browser_restart_confirmation_required",
                        "requires_confirmation": True,
                        "confirm_kind": "restart_to_cdp",
                        "risk_level": "medium",
                        "action": action,
                        "user_prompt": "该任务较为复杂，需要重启浏览器后才能执行，是否确认？",
                        "hint": "请在下一次 browser_use 调用中设置 confirm=true 以继续。",
                        "next_call": {
                            "tool": "browser_use",
                            "action": action,
                            "args": next_args,
                        },
                    }
                runtime_scope = "cdp"
        elif runtime_scope == "external" and sticky_scope == "cdp" and self._cdp_enabled:
            runtime_scope = "cdp"
            prefer_existing_cdp = True

        if runtime_scope in {"system", "all"}:
            return "", False, self._error_payload(
                error="unsupported_scope_for_use",
                action=action,
                scope=runtime_scope,
            )

        if runtime_scope == "cdp":
            if not self._cdp_enabled:
                return "", False, self._error_payload(
                    error="cdp_disabled",
                    action=action,
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未启用受控浏览器（CDP），无法执行该操作。",
                )
            if not self._cdp_endpoint:
                return "", False, self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    action=action,
                    scope="cdp",
                    requires_cdp=True,
                    hint="当前未配置 CDP 端点，无法执行该操作。",
                )

        return runtime_scope, prefer_existing_cdp, None
