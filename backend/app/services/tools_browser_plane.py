from __future__ import annotations

from typing import Any


def tool_plane(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Browser plane tool implementation extracted from AelinToolHub._tool_plane.

    Behaviour is kept identical; this helper simply delegates to the existing
    plane registry and runtime helpers while using the hub for context.
    """

    # Lazy imports to avoid circular dependencies and to reuse shared helpers.
    from app.services.aelin_tools import (
        _result_error,
        _result_ok,
        _should_reuse_active_plane_task,
        _should_restart_plane_task_after_reuse_failure,
        _build_plane_adapter_for_entry,
    )
    from app.services.aelin_planes import (
        close_plane_task,
        get_active_plane_task,
        plane_catalog_entries,
    )
    from app.services.plane_runtime import get_plane_registry_entry

    action = str(args.get("action") or "").strip().lower()
    plane = str(args.get("plane") or "browser").strip().lower() or "browser"
    goal = str(args.get("goal") or "").strip()
    task_id = " ".join(str(args.get("task_id") or "").strip().split())[:96]
    force_new = bool(args.get("force_new"))

    if action == "catalog":
        planes = plane_catalog_entries()
        return _result_ok(planes=planes, total=len(planes))

    entry = get_plane_registry_entry(plane)
    if entry is None:
        return _result_error("unsupported_plane")

    adapter = _build_plane_adapter_for_entry(entry, tool_hub=hub)

    if action == "delegate":
        if not goal:
            return _result_error("missing goal")
        if not force_new:
            active_task = get_active_plane_task(
                hub.user_id,
                hub.workspace,
                plane=entry.metadata.slug,
                db=hub.db,
            )
            active_task_id = " ".join(str((active_task or {}).get("task_id") or "").strip().split())[:96]
            active_state = str((active_task or {}).get("state") or "").strip().lower()
            if active_task_id and _should_reuse_active_plane_task(active_task, goal=goal):
                if active_state == "waiting_user":
                    resumed = adapter.continue_task(task_id=active_task_id, goal=goal[:800])
                    if bool(resumed.get("ok")) and not bool(resumed.get("stale_backing_task")):
                        resumed["reused_existing_task"] = True
                        resumed["reused_action"] = "continue"
                        return resumed
                    if bool(resumed.get("stale_backing_task")):
                        restarted = adapter.delegate(goal=goal[:800])
                        if bool(restarted.get("ok")):
                            restarted["restarted_after_stale_task"] = True
                            restarted["previous_task_id"] = active_task_id
                        return restarted
                    if _should_restart_plane_task_after_reuse_failure(resumed):
                        close_plane_task(
                            active_task_id,
                            user_id=hub.user_id,
                            workspace=hub.workspace,
                            plane=entry.metadata.slug,
                            db=hub.db,
                        )
                        restarted = adapter.delegate(goal=goal[:800])
                        if bool(restarted.get("ok")):
                            restarted["restarted_after_stale_task"] = True
                            restarted["previous_task_id"] = active_task_id
                        return restarted
                    return resumed
                continued = adapter.continue_task(task_id=active_task_id, goal=goal[:800])
                if bool(continued.get("ok")) and not bool(continued.get("stale_backing_task")):
                    continued["reused_existing_task"] = True
                    continued["reused_action"] = "continue"
                    return continued
                if bool(continued.get("stale_backing_task")):
                    restarted = adapter.delegate(goal=goal[:800])
                    if bool(restarted.get("ok")):
                        restarted["restarted_after_stale_task"] = True
                        restarted["previous_task_id"] = active_task_id
                    return restarted
                if _should_restart_plane_task_after_reuse_failure(continued):
                    close_plane_task(
                        active_task_id,
                        user_id=hub.user_id,
                        workspace=hub.workspace,
                        plane=entry.metadata.slug,
                        db=hub.db,
                    )
                    restarted = adapter.delegate(goal=goal[:800])
                    if bool(restarted.get("ok")):
                        restarted["restarted_after_stale_task"] = True
                        restarted["previous_task_id"] = active_task_id
                    return restarted
                return continued
        return adapter.delegate(goal=goal[:800])

    if action not in {"status", "continue", "close"}:
        # Keep the error explicit so the agent learns which actions are valid.
        return _result_error(
            "unsupported plane action: allowed actions are 'delegate', 'status', 'continue', 'close', 'catalog'"
        )
    if not task_id:
        return _result_error("missing task_id: you must pass the 'task_id' from a previous plane call")

    if action == "status":
        return adapter.status(task_id=task_id)

    if action == "continue":
        return adapter.continue_task(task_id=task_id, goal=goal[:800])

    return adapter.close(task_id=task_id)


def tool_pinchtab(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Thin wrapper around the original AelinToolHub._tool_pinchtab implementation.

    Kept separate for clarity and to align with other domain modules while
    preserving the existing tests and monkeypatch points.
    """

    return hub._tool_pinchtab(args)


def tool_pinchtab_agent(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Thin wrapper around the original AelinToolHub._tool_pinchtab_agent.
    """

    return hub._tool_pinchtab_agent(args)


def tool_pinchtab_session(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Thin wrapper around the module-level _tool_pinchtab_session helper
    implemented in aelin_tools.
    """

    from app.services.aelin_tools import _tool_pinchtab_session

    return _tool_pinchtab_session(hub, args)
