from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.main as app_main
from app.db import init_engine
from app.models import Base


def test_app_lifespan_shuts_down_pinchtab_launcher(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    init_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    db_module._engine = engine  # type: ignore[attr-defined]
    db_module._SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)  # type: ignore[attr-defined]

    calls: list[str] = []
    monkeypatch.setattr(app_main, "shutdown_pinchtab_launcher", lambda: calls.append("shutdown") or {"ok": True})
    monkeypatch.setattr(app_main.feishu_bot_service, "stop", lambda: None)
    monkeypatch.setattr(app_main.qq_bot_service, "stop", lambda: None)

    app = app_main.create_app()

    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    assert calls == ["shutdown"]
