from __future__ import annotations

"""
Quick inspector for DeepAgents-related agent_configs rows for a few users.

Usage (from backend/):
    python debug_agent_configs.py

This is a local debugging script only; it is not imported by runtime code.
"""

from sqlalchemy import text

from app.db import create_session


def main() -> None:
    db = create_session()
    for uid in (1, 2, 4, 40):
        row = db.execute(
            text(
                "SELECT provider, base_url, model, temperature "
                "FROM agent_configs WHERE user_id = :uid"
            ),
            {"uid": uid},
        ).first()
        print("user", uid, "config:", row)


if __name__ == "__main__":
    main()
