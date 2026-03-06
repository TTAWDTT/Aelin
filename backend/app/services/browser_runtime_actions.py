from __future__ import annotations

import re
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    PlaywrightTimeoutError = RuntimeError


def _clamp_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)
    return max(int(low), min(int(high), out))


class BrowserActionRuntimeMixin:
    def _resolve_locator(self, *, page: Any, target: str, strategy: str, role: str = "") -> Any:
        text = str(target or "").strip()
        mode = str(strategy or "auto").strip().lower()
        if mode == "selector":
            return page.locator(text).first
        if mode == "text":
            return page.get_by_text(text, exact=False).first
        if mode == "role":
            role_name = str(role or "button").strip().lower() or "button"
            return page.get_by_role(role_name, name=text).first
        if self._is_selector_like(text):
            return page.locator(text).first
        for role_name in ("button", "link", "textbox", "menuitem"):
            try:
                locator = page.get_by_role(role_name, name=text).first
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        return page.get_by_text(text, exact=False).first

    def _handle_external_scope(
        self,
        *,
        action: str,
        args: dict[str, Any],
        runtime_scope: str,
        url: str,
        profile: Any,
    ) -> tuple[str, dict[str, Any] | None]:
        if runtime_scope != "external":
            return runtime_scope, None
        if action != "navigate":
            if bool(args.get("confirm")):
                if not self._cdp_enabled:
                    return "", self._error_payload(
                        error="cdp_disabled",
                        action=action,
                        scope="external",
                        requires_cdp=True,
                        hint="当前外部浏览器模式仅支持打开链接；该操作需要先启用 CDP。",
                    )
                if not self._cdp_endpoint:
                    return "", self._error_payload(
                        error="cdp_endpoint_unconfigured",
                        action=action,
                        scope="external",
                        requires_cdp=True,
                        hint="当前外部浏览器模式仅支持打开链接；该操作需要先配置 CDP 端点。",
                    )
                return "cdp", None
            if not self._cdp_enabled:
                return "", self._error_payload(
                    error="cdp_disabled",
                    action=action,
                    scope="external",
                    requires_cdp=True,
                    hint="当前外部浏览器模式仅支持打开链接；该操作需要先启用 CDP。",
                )
            if not self._cdp_endpoint:
                return "", self._error_payload(
                    error="cdp_endpoint_unconfigured",
                    action=action,
                    scope="external",
                    requires_cdp=True,
                    hint="当前外部浏览器模式仅支持打开链接；该操作需要先配置 CDP 端点。",
                )
            next_args = dict(args or {})
            next_args["scope"] = "cdp"
            next_args["confirm"] = True
            return "", {
                "ok": False,
                "error": "external_scope_requires_cdp_for_dom",
                "requires_confirmation": True,
                "confirm_kind": "restart_to_cdp",
                "risk_level": "medium",
                "action": action,
                "scope": "external",
                "user_prompt": "当前外部浏览器模式仅支持打开链接。该任务需要切换到受控浏览器（CDP）继续执行，是否确认？",
                "hint": "确认后将自动切换到 CDP 继续执行当前步骤。",
                "next_call": {
                    "tool": "browser_use",
                    "action": action,
                    "args": next_args,
                },
            }

        if not re.match(r"^https?://", url, flags=re.I):
            return "", self._error_payload(error="invalid_url", action=action, scope="external")
        opened = self._open_external_url(url)
        if not opened:
            return "", self._error_payload(error="external_open_failed", action=action, scope="external")
        return "", {
            "ok": True,
            "action": action,
            "scope": "external",
            "effect_summary": f"opened_external:{url[:120]}",
            "requires_confirmation": False,
            "risk_level": "low",
            "external_opened": True,
            "before": {"url": "", "title": ""},
            "after": {"url": url[:800], "title": ""},
            "session_id": "",
            "profile_id": profile.profile_id,
            "profile": self._profile_payload(profile),
        }

    def _handle_auth_and_risk_guards(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        url: str,
        target: str,
        value: str,
        profile: Any,
        prefer_existing_cdp: bool,
    ) -> dict[str, Any] | None:
        if (
            action == "navigate"
            and self._is_sensitive_auth_domain(url)
            and not bool(args.get("confirm"))
            and not prefer_existing_cdp
        ):
            next_args = dict(args or {})
            next_args["confirm"] = True
            login_state = self.mark_login_pending(
                user_id=user_id,
                workspace=workspace,
                domain=self._extract_hostname(url),
                next_call={"tool": "browser_use", "action": action, "args": next_args},
                profile_id=profile.profile_id,
                reason="auth_guard",
            )
            return {
                "ok": False,
                "error": "auth_permission_required",
                "requires_confirmation": True,
                "confirm_kind": "auth_guard",
                "risk_level": "auth_guard",
                "action": action,
                "domain": self._extract_hostname(url),
                "profile_id": profile.profile_id,
                "profile": self._profile_payload(profile),
                "login_request_id": str(login_state.get("request_id") or ""),
                "login_state": login_state,
                "fallback_scope": "external",
                "supported_scopes": ["auto", "cdp", "external"],
                "hint": (
                    "使用 confirm=true 可继续受控浏览器导航；"
                    "若需要继承用户登录态，可改用 scope=external。"
                ),
                "next_call": {
                    "tool": "browser_use",
                    "action": action,
                    "args": next_args,
                },
            }
        if self._is_high_risk(action, target=target, value=value, url=url) and not bool(args.get("confirm")):
            next_args = dict(args or {})
            next_args["confirm"] = True
            return {
                "ok": False,
                "error": "confirmation_required",
                "requires_confirmation": True,
                "confirm_kind": "high_risk_action",
                "risk_level": "high",
                "action": action,
                "next_call": {
                    "tool": "browser_use",
                    "action": action,
                    "args": next_args,
                },
            }
        return None

    def _build_confirm_retry_args(
        self,
        *,
        args: dict[str, Any],
        url: str,
        target: str,
        value: str,
    ) -> dict[str, Any]:
        return {
            "url": url,
            "target": target,
            "value": value,
            "strategy": str(args.get("strategy") or "auto").strip().lower(),
            "role": str(args.get("role") or "").strip().lower(),
            "press_enter": bool(args.get("press_enter")),
            "direction": str(args.get("direction") or "").strip().lower(),
            "amount": _clamp_int(args.get("amount"), 720, low=-6000, high=6000),
            "wait_ms": _clamp_int(args.get("wait_ms"), 900, low=100, high=20000),
            "timeout_ms": _clamp_int(args.get("timeout_ms"), self._default_timeout_ms, low=500, high=120000),
            "scope": "cdp",
            "confirm": True,
        }

    def _acquire_use_session(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str,
        action: str,
        args: dict[str, Any],
        runtime_scope: str,
        confirm_retry_args: dict[str, Any],
    ) -> tuple[str, Any | None, dict[str, Any] | None]:
        if runtime_scope == "managed":
            return "", None, self._error_payload(
                error="managed_scope_soft_deleted",
                action=action,
                scope="managed",
                hint="managed 已软下线，请改用 scope=cdp 或 scope=external。",
            )

        if runtime_scope != "cdp":
            if not self._cdp_endpoint:
                return "", None, self._error_payload(error="cdp_endpoint_unconfigured", action=action)
            session, session_error = self._acquire_cdp_session(
                user_id=user_id,
                workspace=workspace,
                profile_id=profile_id,
                action=action,
                allow_restart_confirmation=True,
                confirmed=bool(args.get("confirm")),
                next_args=confirm_retry_args,
            )
            if session_error:
                return "", None, session_error
            runtime_scope = "cdp"
        else:
            session, session_error = self._acquire_cdp_session(
                user_id=user_id,
                workspace=workspace,
                profile_id=profile_id,
                action=action,
                allow_restart_confirmation=True,
                confirmed=bool(args.get("confirm")),
                next_args=confirm_retry_args,
            )
            if session_error:
                return "", None, session_error
        if session is None:
            return "", None, self._error_payload(error="cdp_unavailable:session_missing", action=action)
        return runtime_scope, session, None

    def _execute_use_action(
        self,
        *,
        session: Any,
        action: str,
        args: dict[str, Any],
        url: str,
        target: str,
        value: str,
        timeout_ms: int,
    ) -> tuple[str, bool]:
        strategy = str(args.get("strategy") or "auto").strip().lower()
        role = str(args.get("role") or "").strip().lower()
        external_opened = False
        try:
            with session.lock:
                session.touch()
                page = session.page
                page.set_default_timeout(timeout_ms)

                if action == "navigate":
                    if not re.match(r"^https?://", url, flags=re.I):
                        raise ValueError("invalid_url")
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if self._open_external_on_navigate and (not self._headless):
                        external_opened = self._open_external_url(url)
                    return f"navigated:{url[:120]}", external_opened
                if action == "click":
                    if not target:
                        raise ValueError("missing_target")
                    locator = self._resolve_locator(page=page, target=target, strategy=strategy, role=role)
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.click(timeout=timeout_ms)
                    return f"clicked:{target[:120]}", False
                if action == "type":
                    if not target:
                        raise ValueError("missing_target")
                    locator = self._resolve_locator(page=page, target=target, strategy=strategy, role=role)
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.fill(value, timeout=timeout_ms)
                    if bool(args.get("press_enter")):
                        locator.press("Enter", timeout=timeout_ms)
                    return f"typed:{target[:120]}", False
                if action == "scroll":
                    amount = _clamp_int(args.get("amount"), 720, low=-6000, high=6000)
                    direction = str(args.get("direction") or "").strip().lower()
                    if direction == "up" and amount > 0:
                        amount = -amount
                    if direction == "down" and amount < 0:
                        amount = -amount
                    page.mouse.wheel(0, amount)
                    return f"scrolled:{amount}", False

                wait_ms = _clamp_int(args.get("wait_ms"), 900, low=100, high=20000)
                page.wait_for_timeout(wait_ms)
                return f"waited:{wait_ms}ms", False
        except ValueError:
            raise
        except PlaywrightTimeoutError:
            raise

    def _build_use_success_payload(
        self,
        *,
        action: str,
        runtime_scope: str,
        effect: str,
        external_opened: bool,
        before: dict[str, Any],
        after: dict[str, Any],
        profile: Any,
        fallback_reason: str,
    ) -> dict[str, Any]:
        payload = {
            "ok": True,
            "action": action,
            "scope": runtime_scope,
            "effect_summary": effect,
            "requires_confirmation": False,
            "risk_level": "low",
            "external_opened": bool(external_opened) if action == "navigate" else False,
            "before": {"url": str(before.get("url") or ""), "title": str(before.get("title") or "")},
            "after": {"url": str(after.get("url") or ""), "title": str(after.get("title") or "")},
            "session_id": str(after.get("session_id") or ""),
            "profile_id": profile.profile_id,
            "profile": self._profile_payload(profile),
        }
        if fallback_reason:
            payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
        if runtime_scope == "cdp":
            self._set_preferred_scope(user_id=int(profile.user_id), workspace=profile.workspace, scope="cdp")
        elif runtime_scope == "external" and action == "navigate":
            self._set_preferred_scope(user_id=int(profile.user_id), workspace=profile.workspace, scope="external")
        return payload

    def use(
        self,
        *,
        user_id: int,
        workspace: str,
        action: str,
        args: dict[str, Any],
        profile_id: str = "",
        scope: str = "auto",
    ) -> dict[str, Any]:
        act = str(action or "").strip().lower()
        if act not in {"navigate", "click", "type", "scroll", "wait"}:
            return self._error_payload(error="unsupported_action", action=act)

        target = str(args.get("target") or args.get("selector") or args.get("text") or "").strip()
        value = str(args.get("value") or "").strip()
        url = str(args.get("url") or "").strip()
        profile = self._ensure_profile(user_id=user_id, workspace=workspace, profile_id=profile_id)
        runtime_scope, prefer_existing_cdp, early_payload = self._resolve_use_runtime_scope(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            action=act,
            args=args,
            user_scope=self._normalize_scope(scope),
        )
        if early_payload:
            return early_payload

        runtime_scope, external_payload = self._handle_external_scope(
            action=act,
            args=args,
            runtime_scope=runtime_scope,
            url=url,
            profile=profile,
        )
        if external_payload:
            return external_payload

        guard_payload = self._handle_auth_and_risk_guards(
            user_id=user_id,
            workspace=workspace,
            action=act,
            args=args,
            url=url,
            target=target,
            value=value,
            profile=profile,
            prefer_existing_cdp=prefer_existing_cdp,
        )
        if guard_payload:
            return guard_payload

        timeout_ms = _clamp_int(args.get("timeout_ms"), self._default_timeout_ms, low=500, high=120000)
        fallback_reason = ""
        confirm_retry_args = self._build_confirm_retry_args(args=args, url=url, target=target, value=value)
        runtime_scope, session, session_error = self._acquire_use_session(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            action=act,
            args=args,
            runtime_scope=runtime_scope,
            confirm_retry_args=confirm_retry_args,
        )
        if session_error:
            return session_error

        before = self.state_get(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            scope=runtime_scope,
            include_dom=False,
            include_a11y=False,
            max_targets=1,
        )

        try:
            effect, external_opened = self._execute_use_action(
                session=session,
                action=act,
                args=args,
                url=url,
                target=target,
                value=value,
                timeout_ms=timeout_ms,
            )
        except ValueError as exc:
            return self._error_payload(error=str(exc), action=act)
        except PlaywrightTimeoutError:
            return self._error_payload(error="timeout", action=act)
        except Exception as exc:
            return self._error_payload(error=str(exc)[:180], action=act)

        after = self.state_get(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            scope=runtime_scope,
            include_dom=False,
            include_a11y=False,
            max_targets=1,
        )
        return self._build_use_success_payload(
            action=act,
            runtime_scope=runtime_scope,
            effect=effect,
            external_opened=external_opened,
            before=before,
            after=after,
            profile=profile,
            fallback_reason=fallback_reason,
        )
