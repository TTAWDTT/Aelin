from __future__ import annotations

import asyncio
from uuid import uuid4

from jose import JWTError, jwt
from sqlalchemy import select

from langgraph_sdk import Auth

from app import crud
from app.db import create_session
from app.models import User
from app.security import ALGORITHM
from app.settings import settings


aelin_auth = Auth()


def _ensure_local_user() -> User:
    db = create_session()
    try:
        user = db.scalar(select(User).order_by(User.id.asc()))
        if user is not None:
            return user
        return crud.create_user(
            db,
            email="local@aelin.local",
            password=f"local-{uuid4().hex}-{uuid4().hex}",
        )
    finally:
        db.close()


def _resolve_token_user(authorization: str | None) -> User:
    fallback_user = _ensure_local_user()
    token = str(authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return fallback_user

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return fallback_user
        user_id = int(sub)
    except (JWTError, ValueError):
        return fallback_user

    db = create_session()
    try:
        user = db.get(User, user_id)
        if user is None:
            return fallback_user
        return user
    finally:
        db.close()


@aelin_auth.authenticate
async def authenticate(authorization: str | None) -> Auth.types.MinimalUserDict:
    user = await asyncio.to_thread(_resolve_token_user, authorization)
    return {
        "identity": str(user.id),
        "permissions": [],
        "user_id": str(user.id),
        "email": str(user.email or ""),
    }


@aelin_auth.on.threads.create
async def allow_thread_create(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.create.value,
):
    metadata = value.setdefault("metadata", {})
    metadata["owner"] = str(ctx.user.identity)


@aelin_auth.on.threads.read
async def allow_thread_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.read.value,
) -> Auth.types.FilterType:
    _ = value
    return {"owner": str(ctx.user.identity)}


@aelin_auth.on.threads.search
async def allow_thread_search(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.search.value,
) -> Auth.types.FilterType:
    _ = value
    return {"owner": str(ctx.user.identity)}


@aelin_auth.on.threads.update
async def allow_thread_update(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.update.value,
) -> Auth.types.FilterType:
    _ = value
    return {"owner": str(ctx.user.identity)}


@aelin_auth.on.threads.delete
async def allow_thread_delete(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.delete.value,
) -> Auth.types.FilterType:
    _ = value
    return {"owner": str(ctx.user.identity)}


@aelin_auth.on.threads.create_run
async def allow_thread_create_run(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.create_run.value,
) -> Auth.types.FilterType:
    _ = value
    return {"owner": str(ctx.user.identity)}


@aelin_auth.on.store
async def scope_store(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.store.value,
):
    namespace = tuple(value["namespace"]) if value.get("namespace") else ()
    identity = str(ctx.user.identity)
    if not namespace or namespace[0] != identity:
        value["namespace"] = (identity, *namespace)
