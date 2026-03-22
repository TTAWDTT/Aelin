from __future__ import annotations

"""
Lightweight CLI helper to inspect users in the current Aelin DB.

Usage (from backend/):
    python scripts/debug_list_users.py

This script is intended for local debugging only and is not imported
anywhere in the runtime code.
"""

from sqlalchemy import text

from app.db import create_session


def main() -> None:
    db = create_session()
    rows = db.execute(text("SELECT id, email FROM users ORDER BY id ASC")).fetchall()
    print("USERS:")
    for r in rows:
        print(r[0], r[1])


if __name__ == "__main__":
    main()
