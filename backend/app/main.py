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
from app.routers import (
    agent,
    aelin,
    aelin_chat,
    aelin_context,
    aelin_device,
    aelin_remote_control,
    auth,
    deepagents_chat,
)
from app.settings import settings
from app.services.bots.feishu_bot import feishu_bot_service
from app.services.bots.qq_bot import qq_bot_service

_log = logging.getLogger(__name__)


def _configure_logging() -> None:
    level_raw = str(getattr(settings, "backend_log_level", "INFO") or "INFO").strip().upper()
    level = getattr(logging, level_raw, logging.INFO)
    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=log_format)
    else:
        root.setLevel(level)
        for handler in root.handlers:
            try:
                handler.setLevel(level)
                handler.setFormatter(logging.Formatter(log_format))
            except Exception:
                continue
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
    _log.info("logging configured level=%s", level_raw)


def _add_missing_columns(engine: Engine) -> None:
    """Add columns that exist in the ORM model but not yet in the DB (simple SQLite migration)."""
    inspector = sa_inspect(engine)
    migrations: list[tuple[str, str, str]] = [
        # (table, column, DDL type)
        ("agent_configs", "web_search_proxy_url", "TEXT"),
        ("agent_configs", "verify_ssl", "BOOLEAN DEFAULT 1"),
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
    if settings.feishu_bot_enabled:
        feishu_bot_service.start()
        _log.info("feishu bot enabled")
    else:
        _log.info("feishu bot disabled")
    if settings.qq_bot_enabled:
        qq_bot_service.start()
        _log.info("qq bot enabled")
    else:
        _log.info("qq bot disabled")
    try:
        yield
    finally:
        feishu_bot_service.stop()
        qq_bot_service.stop()


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(title="Aelin API", version="0.1.0", lifespan=lifespan)

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
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(aelin.router, prefix="/api/v1")
    app.include_router(aelin_chat.router, prefix="/api/v1")
    app.include_router(deepagents_chat.router, prefix="/api/v1")
    app.include_router(aelin_context.router, prefix="/api/v1")
    app.include_router(aelin_device.router, prefix="/api/v1")
    app.include_router(aelin_remote_control.router, prefix="/api/v1")

    return app


app = create_app()

