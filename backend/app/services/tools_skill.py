from __future__ import annotations

from typing import Any


def tool_skill(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Skill tool implementation extracted from AelinToolHub._tool_skill.

    This helper keeps behaviour identical to the original inlined method and
    delegates to the shared skill_loader helpers.
    """

    # Lazy imports to avoid circular dependency and to keep tests that
    # monkeypatch aelin_tools working as before.
    from app.services.aelin_tools import _result_error, _result_ok
    from app.services.skill_loader import (
        get_skill_prompt_by_slug,
        list_skill_catalog_for_query_and_tools,
    )

    action = str(args.get("action") or "").strip().lower()
    if action == "catalog":
        tool_names = [
            str((row.get("function") or {}).get("name") or "").strip()
            for row in hub.tool_definitions()
            if isinstance(row, dict) and isinstance(row.get("function"), dict)
        ]
        items = list_skill_catalog_for_query_and_tools(
            str(args.get("query") or "").strip(),
            tool_names,
        )
        return _result_ok(items=items, total=len(items))

    if action == "read":
        slug = str(args.get("slug") or "").strip().lower()
        if not slug:
            return _result_error("missing slug")
        prompt = get_skill_prompt_by_slug(slug)
        if not prompt:
            return _result_error("unknown_skill_slug")
        return _result_ok(slug=slug, prompt=prompt, summary=prompt.split("\n", 4)[-1][:260])

    return _result_error("unsupported skill action")

