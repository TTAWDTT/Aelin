from __future__ import annotations

import asyncio
from types import SimpleNamespace

from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud
from app.db import create_session, init_engine
from app.models import Base, User
from app.security import ALGORITHM
from app.settings import settings


def _init_test_db() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    init_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    import app.db as db_module

    db_module._engine = engine  # type: ignore[attr-defined]
    db_module._SessionLocal = sessionmaker(  # type: ignore[attr-defined]
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )


def test_agent_server_authenticate_falls_back_to_local_user():
    import agent_server.auth as auth_module

    _init_test_db()

    user = asyncio.run(auth_module.authenticate(None))

    assert user["identity"] == user["user_id"]
    assert int(user["identity"]) > 0

    db = create_session()
    try:
        stored = db.scalar(select(User).where(User.id == int(user["identity"])))
        assert stored is not None
        assert stored.email == "local@aelin.local"
    finally:
        db.close()


def test_agent_server_authenticate_resolves_bearer_user():
    import agent_server.auth as auth_module

    _init_test_db()

    db = create_session()
    try:
        user = crud.create_user(db, email="agent@example.com", password="password123")
        token = jwt.encode({"sub": str(user.id)}, settings.secret_key, algorithm=ALGORITHM)
    finally:
        db.close()

    resolved = asyncio.run(auth_module.authenticate(f"Bearer {token}"))

    assert resolved["identity"] == str(user.id)
    assert resolved["user_id"] == str(user.id)
    assert resolved["email"] == "agent@example.com"


def test_agent_server_thread_and_store_hooks_scope_to_current_user():
    import agent_server.auth as auth_module

    ctx = SimpleNamespace(user=SimpleNamespace(identity="42"))
    create_value: dict[str, object] = {}
    store_value = {"namespace": ("workspace", "notes")}

    asyncio.run(auth_module.allow_thread_create(ctx, create_value))
    read_filter = asyncio.run(auth_module.allow_thread_read(ctx, {}))
    asyncio.run(auth_module.scope_store(ctx, store_value))

    assert create_value == {"metadata": {"owner": "42"}}
    assert read_filter == {"owner": "42"}
    assert store_value["namespace"] == ("42", "workspace", "notes")
