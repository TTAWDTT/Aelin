from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.browser_automation import BrowserSession


def _normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def _clamp_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)
    return max(int(low), min(int(high), out))


class BrowserStateRuntimeMixin:
    def list_sessions(
        self,
        *,
        user_id: int,
        workspace: str,
        scope: str = "all",
        max_items: int = 20,
        pid: int = 0,
    ) -> dict[str, Any]:
        normalized_scope = self._normalize_scope(scope)
        raw_limit = 20 if max_items is None else int(max_items)
        limit = max(0, min(200, raw_limit))
        normalized_workspace = _normalize_workspace(workspace)
        out: dict[str, Any] = {
            "ok": True,
            "scope": normalized_scope,
            "workspace": normalized_workspace,
            "managed_sessions": [],
            "system_processes": [],
            "cdp_enabled": bool(self._cdp_enabled),
            "cdp_endpoint": str(self._cdp_endpoint or ""),
        }
        include_managed = normalized_scope in {"managed", "all", "auto", "cdp"}
        include_system = normalized_scope in {"system", "all", "external"}

        if include_managed:
            self._cleanup_idle_sessions()
            with self._lock:
                for session in self._sessions.values():
                    if int(getattr(session, "user_id", 0) or 0) != int(user_id):
                        continue
                    if str(getattr(session, "workspace", "") or "") != normalized_workspace:
                        continue
                    out["managed_sessions"].append(
                        {
                            "session_id": str(getattr(session, "session_id", "") or ""),
                            "mode": str(getattr(session, "mode", "managed") or "managed"),
                            "profile_id": str(getattr(session, "profile_id", "") or ""),
                            "user_data_dir": str(getattr(session, "user_data_dir", "") or "")[:220],
                            "last_used": float(getattr(session, "last_used", 0.0) or 0.0),
                            "created_at": float(getattr(session, "created_at", 0.0) or 0.0),
                            "owner_thread_id": int(getattr(session, "owner_thread_id", 0) or 0),
                        }
                    )
            managed_sorted = sorted(
                list(out["managed_sessions"]),
                key=lambda it: float(it.get("last_used") or 0.0),
                reverse=True,
            )
            out["managed_sessions"] = managed_sorted[:limit] if limit > 0 else []

        if include_system and limit > 0:
            out["system_processes"] = self._list_system_browser_processes(
                max_items=limit,
                pid=int(pid or 0),
                include_details=False,
            )
        return out

    def _snapshot_page(
        self,
        *,
        page: Any,
        mode: str,
        include_dom: bool,
        include_a11y: bool,
        max_targets: int,
    ) -> dict[str, Any]:
        title = ""
        try:
            title = str(page.title() or "").strip()[:180]
        except Exception:
            title = ""

        url = str(getattr(page, "url", "") or "").strip()[:800]
        ready_state = ""
        try:
            ready_state = str(page.evaluate("() => document.readyState") or "").strip()[:40]
        except Exception:
            ready_state = ""

        interactive_targets: list[dict[str, Any]] = []
        if include_dom:
            script = """
() => {
  const nodes = Array.from(
    document.querySelectorAll(
      'a[href],button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"],[onclick]'
    )
  );
  const out = [];
  for (const node of nodes) {
    if (out.length >= 60) break;
    const style = window.getComputedStyle(node);
    const hidden = style.display === 'none' || style.visibility === 'hidden';
    if (hidden) continue;
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width < 2 || rect.height < 2) continue;
    const tag = String((node.tagName || '').toLowerCase());
    const role = String(node.getAttribute('role') || '').trim().toLowerCase();
    const id = String(node.id || '').trim();
    const name = String(node.getAttribute('name') || '').trim();
    const aria = String(node.getAttribute('aria-label') || '').trim();
    const text = String(
      aria
      || node.innerText
      || node.textContent
      || node.getAttribute('value')
      || node.getAttribute('placeholder')
      || ''
    ).replace(/\\s+/g, ' ').trim();
    let hint = '';
    if (id) hint = `#${id}`;
    else if (name) hint = `${tag}[name="${name}"]`;
    else if (aria) hint = `${tag}[aria-label="${aria}"]`;
    out.push({ tag, role, text, selector_hint: hint, x: Math.round(rect.x), y: Math.round(rect.y) });
  }
  return out;
}
"""
            try:
                raw_targets = page.evaluate(script) or []
            except Exception:
                raw_targets = []
            if isinstance(raw_targets, list):
                for item in raw_targets[:max_targets]:
                    if not isinstance(item, dict):
                        continue
                    interactive_targets.append(
                        {
                            "tag": str(item.get("tag") or "")[:24],
                            "role": str(item.get("role") or "")[:24],
                            "text": str(item.get("text") or "")[:120],
                            "selector_hint": str(item.get("selector_hint") or "")[:120],
                            "x": _clamp_int(item.get("x"), 0, low=-50000, high=50000),
                            "y": _clamp_int(item.get("y"), 0, low=-50000, high=50000),
                        }
                    )

        a11y_nodes: list[dict[str, Any]] = []
        if include_a11y:
            try:
                snapshot = page.accessibility.snapshot(interesting_only=True)
            except Exception:
                snapshot = None
            if isinstance(snapshot, dict):
                queue = [snapshot]
                while queue and len(a11y_nodes) < 40:
                    node = queue.pop(0)
                    if not isinstance(node, dict):
                        continue
                    role = str(node.get("role") or "").strip()
                    name = str(node.get("name") or "").strip()
                    if role or name:
                        a11y_nodes.append({"role": role[:40], "name": name[:120]})
                    children = node.get("children")
                    if isinstance(children, list):
                        queue.extend([child for child in children if isinstance(child, dict)])

        digest = {
            "interactive_count": len(interactive_targets),
            "a11y_count": len(a11y_nodes),
            "ready_state": ready_state,
        }
        is_blank_page = bool(url.lower().startswith("about:blank"))
        mode_tag = str(mode or "managed").strip().lower() or "managed"
        visibility = "headless" if (mode_tag == "managed" and self._headless) else "visible_window"
        if mode_tag == "cdp":
            scope_note = "这是通过 CDP 接入的用户浏览器会话状态。"
        elif is_blank_page:
            scope_note = "这是 Aelin agent 的浏览器会话，不是系统当前前台浏览器标签页。"
        else:
            scope_note = "这是 Aelin agent 的浏览器会话状态。"
        snapshot = self._build_agent_snapshot(
            url=url,
            title=title,
            ready_state=ready_state,
            interactive_targets=interactive_targets,
            a11y_nodes=a11y_nodes,
        )
        return {
            "session_scope": mode_tag,
            "is_blank_page": is_blank_page,
            "visibility": visibility,
            "scope_note": scope_note,
            "url": url,
            "title": title,
            "ready_state": ready_state,
            "summary": str(snapshot.get("summary") or "")[:260],
            "snapshot": snapshot,
            "interactive_targets": interactive_targets,
            "a11y_nodes": a11y_nodes,
            "dom_digest": digest,
        }

    @staticmethod
    def _build_agent_snapshot(
        *,
        url: str,
        title: str,
        ready_state: str,
        interactive_targets: list[dict[str, Any]],
        a11y_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        focus_targets: list[dict[str, Any]] = []
        labels: list[str] = []
        for item in interactive_targets[:8]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("text") or item.get("selector_hint") or item.get("role") or item.get("tag") or "").strip()
            tag = str(item.get("tag") or "").strip()[:24]
            role = str(item.get("role") or "").strip()[:24]
            selector_hint = str(item.get("selector_hint") or "").strip()[:120]
            entry = {
                "label": label[:120],
                "tag": tag,
                "role": role,
                "selector_hint": selector_hint,
            }
            focus_targets.append(entry)
            if label:
                labels.append(label[:40])

        cues: list[str] = []
        for node in a11y_nodes[:6]:
            if not isinstance(node, dict):
                continue
            cue = str(node.get("name") or node.get("role") or "").strip()
            if cue:
                cues.append(cue[:40])

        parts: list[str] = []
        if title:
            parts.append(f"页面标题: {title[:80]}")
        if labels:
            parts.append("可操作元素: " + " / ".join(labels[:4]))
        elif cues:
            parts.append("辅助线索: " + " / ".join(cues[:4]))
        elif url:
            parts.append(f"当前地址: {url[:120]}")
        if ready_state:
            parts.append(f"加载状态: {ready_state[:24]}")

        return {
            "url": url[:240],
            "title": title[:180],
            "ready_state": ready_state[:40],
            "focus_targets": focus_targets,
            "a11y_cues": cues[:4],
            "summary": "；".join(parts)[:260],
        }

    @staticmethod
    def _error_payload(
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

    def state_get(
        self,
        *,
        user_id: int,
        workspace: str,
        profile_id: str = "",
        scope: str = "auto",
        include_dom: bool = True,
        include_a11y: bool = False,
        max_targets: int = 30,
        max_items: int = 20,
        pid: int = 0,
    ) -> dict[str, Any]:
        profile = self._ensure_profile(user_id=user_id, workspace=workspace, profile_id=profile_id)
        user_scope = self._normalize_scope(scope)
        target_limit = _clamp_int(max_targets, 30, low=1, high=60)
        proc_limit = _clamp_int(max_items, 20, low=0, high=200)
        sticky_scope = self._get_preferred_scope(user_id=int(user_id), workspace=workspace)
        if user_scope == "all":
            sessions = self.list_sessions(
                user_id=user_id,
                workspace=workspace,
                scope="all",
                max_items=proc_limit,
                pid=int(pid or 0),
            )
            active_state = self.state_get(
                user_id=user_id,
                workspace=workspace,
                profile_id=profile.profile_id,
                scope="auto",
                include_dom=include_dom,
                include_a11y=include_a11y,
                max_targets=target_limit,
                max_items=proc_limit,
                pid=int(pid or 0),
            )
            return {
                "ok": bool(active_state.get("ok", False)),
                "scope": "all",
                "active_state": active_state,
                "managed_sessions": list(sessions.get("managed_sessions") or []),
                "system_processes": list(sessions.get("system_processes") or []),
                "cdp_enabled": bool(sessions.get("cdp_enabled")),
                "cdp_endpoint": str(sessions.get("cdp_endpoint") or ""),
                "error": str(active_state.get("error") or "")[:180] if not bool(active_state.get("ok", False)) else "",
                "requires_confirmation": bool(active_state.get("requires_confirmation", False)),
                "confirm_kind": str(active_state.get("confirm_kind") or "")[:48],
                "user_prompt": str(active_state.get("user_prompt") or "")[:220],
                "next_call": active_state.get("next_call") if isinstance(active_state.get("next_call"), dict) else {},
                "requires_cdp": bool(active_state.get("requires_cdp", False)),
            }

        runtime_scope, fallback_reason, early_payload = self._resolve_state_runtime_scope(
            user_scope="cdp" if user_scope == "auto" and sticky_scope == "cdp" and self._cdp_enabled else user_scope,
            include_dom=bool(include_dom),
            include_a11y=bool(include_a11y),
            proc_limit=proc_limit,
            pid=int(pid or 0),
        )
        if isinstance(early_payload, dict):
            return early_payload

        if runtime_scope != "cdp":
            return self._error_payload(error=f"unsupported_scope:{runtime_scope or user_scope}", scope=runtime_scope or user_scope)

        session, session_error = self._acquire_cdp_session(
            user_id=user_id,
            workspace=workspace,
            profile_id=profile.profile_id,
            action="state_get",
            allow_restart_confirmation=False,
        )
        if session_error:
            fallback = str((session_error or {}).get("error") or "")[:160]
            normalized_fallback = fallback.split(":", 1)[1].strip() if fallback.startswith("cdp_unavailable:") else fallback
            if bool(include_dom) or bool(include_a11y):
                if (
                    normalized_fallback in {"cdp_requires_browser_restart", "cdp_launch_timeout", "browser_restart_failed_for_cdp"}
                    or "cdp_requires_browser_restart" in normalized_fallback
                ):
                    next_args: dict[str, Any] = {
                        "scope": "cdp",
                        "include_dom": bool(include_dom),
                        "include_a11y": bool(include_a11y),
                        "max_targets": int(target_limit),
                        "max_items": int(proc_limit),
                        "pid": int(pid or 0),
                    }
                    return {
                        "ok": False,
                        "error": "browser_restart_confirmation_required",
                        "requires_confirmation": True,
                        "confirm_kind": "restart_to_cdp",
                        "risk_level": "medium",
                        "action": "state_get",
                        "scope": user_scope,
                        "user_prompt": "读取页面内容需要切换到 CDP 并重启浏览器，是否确认？",
                        "hint": "确认后将自动重启浏览器并继续执行页面读取。",
                        "next_call": {
                            "tool": "browser_state_get",
                            "action": "state_get",
                            "args": next_args,
                        },
                    }
                return {
                    "ok": False,
                    "error": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                    "scope": "cdp",
                    "requires_cdp": True,
                    "hint": "当前无法建立 CDP 会话，暂不支持 DOM/A11y 读取。",
                }
            system_processes = self._list_system_browser_processes(
                max_items=proc_limit,
                pid=int(pid or 0),
                include_details=False,
            )
            if system_processes:
                return {
                    "ok": True,
                    "scope": "external",
                    "system_processes": system_processes,
                    "scope_fallback": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                    "scope_note": "CDP 暂不可用，已退回到系统浏览器进程级状态读取。",
                }
            return {
                "ok": False,
                "error": fallback if fallback.startswith("cdp_unavailable:") else f"cdp_unavailable:{fallback}",
                "scope": "cdp",
                "requires_cdp": True,
            }
        if session is None:
            return self._error_payload(error="cdp_unavailable:session_missing", scope="cdp", requires_cdp=True)

        with session.lock:
            session.touch()
            snap = self._snapshot_page(
                page=session.page,
                mode=str(getattr(session, "mode", runtime_scope) or runtime_scope),
                include_dom=bool(include_dom),
                include_a11y=bool(include_a11y),
                max_targets=target_limit,
            )
            payload: dict[str, Any] = {
                "ok": True,
                "scope": runtime_scope,
                "session_id": session.session_id,
                "profile_id": profile.profile_id,
                "profile": self._profile_payload(profile),
                **snap,
            }
            if fallback_reason:
                payload["scope_fallback"] = f"cdp_unavailable:{fallback_reason}"
            if runtime_scope == "cdp":
                self._set_preferred_scope(user_id=int(user_id), workspace=workspace, scope="cdp")
            return payload
