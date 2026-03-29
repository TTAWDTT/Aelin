from __future__ import annotations

"""
Run full Aelin chat pipeline for a given DB user (no HTTP/jwt), mainly for
DeepAgents end-to-end verification.

Usage:
    cd backend
    python scripts/debug_run_aelin_for_user.py
"""

from datetime import timezone

from sqlalchemy import text

from app.db import create_session
from app.models import User
from app.schemas import ChatRequest
from app.services.device.remote_control_chat_adapter import run_chat_request
from app.settings import settings


def run_for_user(user_id: int, name: str, query: str) -> None:
    db = create_session()
    try:
        user = db.get(User, user_id)
        if user is None:
            print(f"[user {user_id}] not found")
            return
        print(f"\n=== [{name}] Aelin chat for user {user.id} {user.email!r} ===")
        payload = ChatRequest(
        query=query,
        workspace="default",
        use_memory=True,
        images=[],
        history=[],
        )

        def _event_cb(kind: str, payload: dict) -> None:
            if kind == "trace":
                step = payload.get("step") or {}
                print("TRACE:", step.get("stage"), step.get("status"), "-", step.get("detail"))

        resp = run_chat_request(payload, db, user, event_cb=_event_cb, cancel_token=None)
        print("ANSWER:", repr(resp.answer))
        print("ACTIONS:", [action.kind for action in resp.actions])
        print("GENERATED_AT:", resp.generated_at.astimezone(timezone.utc))
    finally:
        db.close()


def main() -> None:
    print("DB URL:", settings.database_url)
    db = create_session()
    # For quick sanity check, show all users.
    rows = db.execute(text("SELECT id, email FROM users ORDER BY id ASC")).fetchall()
    print("USERS:", [(r[0], r[1]) for r in rows])

    # User 1 is currently the DeepSeek-configured agent in this DB.
    tests = [
        (
            "T1_simple_intro",
            "你好，请用三段话介绍一下你自己，并说明你现在是在一个叫 Aelin 的应用中作为代理运行的。",
        ),
        (
            "T2_web_search_news",
            "请先使用你可用的网络搜索工具了解一下最近 3 天的国际要闻，然后用 3-5 条要点总结给我，每条要注明大致来源网站名称。",
        ),
        (
            "T3_browser_baidu_home",
            "请在浏览器中打开 https://www.baidu.com ，大致浏览首页内容，然后列出 3 个你认为最重要的栏目，并推测这些栏目里通常会包含什么类型的信息。",
        ),
        (
            "T4_reasoning_plan_only",
            "假设我打算写一篇题为《DeepAgents 在 Aelin 中的架构设计》的技术文档。请先为我设计一个详细的大纲（至少包含 3 级小节），然后再用一段话说明在工具权限允许的情况下，你会如何调用 device 和 web_search 工具来辅助完成这篇文档的写作。请不要真的调用工具，只用自然语言回答。",
        ),
    ]

    for name, q in tests:
        run_for_user(1, name, q)


if __name__ == "__main__":
    main()
