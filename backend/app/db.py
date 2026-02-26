from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_SQLITE_CONNECT_TIMEOUT_SECONDS = 30.0
_SQLITE_BUSY_TIMEOUT_MS = 30_000


def _is_sqlite_url(url: str) -> bool:
    return str(url or "").startswith("sqlite")


def _resolve_connect_args(url: str, connect_args: dict | None) -> dict:
    if not _is_sqlite_url(url):
        return connect_args or {}
    merged = {
        "check_same_thread": False,
        "timeout": _SQLITE_CONNECT_TIMEOUT_SECONDS,
    }
    if connect_args:
        merged.update(connect_args)
    return merged


def _configure_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _apply_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            # Keep startup resilient on environments where specific PRAGMA values are unsupported.
            pass
        finally:
            cursor.close()


def init_engine(database_url: str | None = None, *, connect_args: dict | None = None) -> Engine:
    global _engine, _SessionLocal

    url = database_url or settings.database_url
    connect_args = _resolve_connect_args(url, connect_args)

    _engine = create_engine(url, future=True, connect_args=connect_args)
    if _is_sqlite_url(url):
        _configure_sqlite_pragmas(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def create_session() -> Session:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_session() -> Generator[Session, None, None]:
    db = create_session()
    try:
        yield db
    finally:
        db.close()
