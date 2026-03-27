from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentConfig, User
from app.security import get_password_hash, verify_password
from app.services.foundation.encryption import decrypt_optional, encrypt_optional


def create_user(db: Session, *, email: str, password: str) -> User:
    user = User(email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def update_user(
    db: Session,
    *,
    user: User,
    email: str | None = None,
    password: str | None = None,
    avatar_url: str | None = None,
) -> User:
    if email is not None:
        user.email = email
    if password is not None:
        user.hashed_password = get_password_hash(password)
    if avatar_url is not None:
        user.avatar_url = avatar_url
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_agent_config(db: Session, *, user_id: int) -> AgentConfig | None:
    return db.get(AgentConfig, user_id)


def upsert_agent_config(
    db: Session,
    *,
    user_id: int,
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    verify_ssl: bool | None = None,
    api_key: str | None = None,
    web_search_proxy_url: str | None = None,
) -> AgentConfig:
    config = db.get(AgentConfig, user_id)
    if config is None:
        config = AgentConfig(user_id=user_id)
        db.add(config)

    if provider is not None:
        config.provider = provider.lower().strip()
    if base_url is not None:
        config.base_url = base_url.strip()
    if model is not None:
        config.model = model.strip()
    if temperature is not None:
        config.temperature = float(temperature)
    if verify_ssl is not None:
        config.verify_ssl = bool(verify_ssl)
    if api_key is not None:
        config.api_key = encrypt_optional(api_key.strip())
    if web_search_proxy_url is not None:
        clean_proxy = web_search_proxy_url.strip()
        config.web_search_proxy_url = clean_proxy or None

    db.commit()
    db.refresh(config)
    return config


def get_agent_api_key(db: Session, *, user_id: int) -> str | None:
    config = get_agent_config(db, user_id=user_id)
    if config is None:
        return None
    return decrypt_optional(config.api_key)

