from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine

from app.db import get_engine
from app.models import Base
from app.routers import accounts, agent, aelin, auth, contacts, inbound, messages
from app.settings import settings
from app.services.tracking_autonomy import tracking_autonomy_service

_log = logging.getLogger(__name__)


def _add_missing_columns(engine: Engine) -> None:
    """Add columns that exist in the ORM model but not yet in the DB (simple SQLite migration)."""
    inspector = sa_inspect(engine)
    migrations: list[tuple[str, str, str]] = [
        # (table, column, DDL type)
        ("x_api_configs", "auth_cookies", "TEXT"),
    ]
    for table, column, ddl_type in migrations:
        if not inspector.has_table(table):
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            _log.info("Added column %s.%s", table, column)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    # Lightweight column migration for SQLite (add columns that don't exist yet)
    _add_missing_columns(engine)
    tracking_autonomy_service.start()
    try:
        yield
    finally:
        tracking_autonomy_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="MercuryDesk API", version="0.1.0", lifespan=lifespan)

    origins = {o.strip() for o in settings.cors_origins.split(",") if o.strip()}
    # Native shells (Capacitor/Electron) and local dev hosts.
    origins.update(
        {
            "http://localhost",
            "https://localhost",
            "capacitor://localhost",
            "http://127.0.0.1",
            "https://127.0.0.1",
        }
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(accounts.router, prefix="/api/v1")
    app.include_router(contacts.router, prefix="/api/v1")
    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(aelin.router, prefix="/api/v1")
    app.include_router(inbound.router, prefix="/api/v1")

    return app


app = create_app()

