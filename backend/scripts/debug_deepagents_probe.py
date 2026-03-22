from __future__ import annotations

"""
Small debug probe to inspect DeepAgents loop behavior for a given user.

Run with:
    cd backend
    python scripts/debug_deepagents_probe.py
"""

from sqlalchemy import text

from app.db import create_session
from app.models import User
from app.services.aelin_runtime import resolve_llm_service
from app.services.web_search import WebSearchService
from app.services.aelin_tools import AelinToolHub
from app.services.aelin_tool_policy import AelinToolPolicy
from app.services.deepagents_loop import run_deepagents_loop
from app.settings import settings


def probe_user(db, uid: int) -> None:
    user = db.get(User, uid)
    if user is None:
        print(f"[user {uid}] not found")
        return
    print("\n=== Probing user", uid, user.email, "===")

    service, provider = resolve_llm_service(db, user)
    print("Provider:", provider, "configured:", service.is_configured())
    print("Model:", getattr(service.config, "model", None), "base_url:", getattr(service.config, "base_url", None))

    web_search_service = WebSearchService()

    hub = AelinToolHub(
        db=db,
        user_id=user.id,
        workspace="default",
        web_search_service=web_search_service,
        available_attachment_ids=[],
        llm_service=service,
    )
    policy = AelinToolPolicy(max_tool_calls=4, max_write_calls=1, allow_write_tools=True)

    res = run_deepagents_loop(
        service=service,
        provider=provider,
        tool_hub=hub,
        policy=policy,
        query="你好，简单介绍一下你自己",
        memory_summary="",
        history_turns=[],
    )

    print("Result ok:", res.ok, "stop_reason:", res.stop_reason)
    print("Answer repr:", repr(res.answer))
    print("Trace_steps:", [(t.stage, t.status, t.detail) for t in res.trace_steps])
    print("Tool_runs:", [(r.name, r.status, r.error) for r in res.tool_runs])


def main() -> None:
    print("DB URL:", settings.database_url)
    db = create_session()
    # Probe a few likely users, including deepseek / ark / deepagents test.
    for uid in (1, 2, 4, 40):
        probe_user(db, uid)


if __name__ == "__main__":
    main()
