from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import (
    AgentConfig,
    ConnectedAccount,
    Contact,
    FeedAccountConfig,
    ForwardAccountConfig,
    ImapAccountConfig,
    Message,
    OAuthCredentialConfig,
    User,
)
from app.security import get_password_hash, verify_password
from app.services.encryption import decrypt_optional, encrypt_optional


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


def create_connected_account(
    db: Session,
    *,
    user_id: int,
    provider: str,
    identifier: str,
    access_token: str | None,
    refresh_token: str | None,
    imap_host: str | None = None,
    imap_port: int | None = None,
    imap_use_ssl: bool | None = None,
    imap_username: str | None = None,
    imap_password: str | None = None,
    imap_mailbox: str | None = None,
    feed_url: str | None = None,
    feed_homepage_url: str | None = None,
    feed_display_name: str | None = None,
    forward_inbound_secret: str | None = None,
) -> ConnectedAccount:
    provider_norm = provider.lower().strip()
    identifier_norm = identifier.strip()
    if not identifier_norm:
        raise ValueError("identifier is required")
    account = ConnectedAccount(
        user_id=user_id,
        provider=provider_norm,
        identifier=identifier_norm,
        access_token=encrypt_optional(access_token),
        refresh_token=encrypt_optional(refresh_token),
    )
    db.add(account)
    db.flush()

    if provider_norm == "imap":
        if not (imap_host and imap_username and imap_password):
            raise ValueError("IMAP account requires host/username/password")
        config = ImapAccountConfig(
            account_id=account.id,
            host=imap_host,
            port=imap_port or 993,
            use_ssl=True if imap_use_ssl is None else bool(imap_use_ssl),
            username=imap_username,
            password=encrypt_optional(imap_password) or "",
            mailbox=imap_mailbox or "INBOX",
        )
        db.add(config)
    elif provider_norm in {"rss", "bilibili", "x", "douyin", "xiaohongshu", "weibo"}:
        config_feed_url = feed_url.strip() if feed_url else None
        # 抖音、小红书、微博不强制要求 feed_url，使用 identifier 作为 UID
        if provider_norm == "rss" and not config_feed_url:
            raise ValueError(f"{provider_norm} account requires feed_url")
        feed_config = FeedAccountConfig(
            account_id=account.id,
            feed_url=config_feed_url or "",
            homepage_url=feed_homepage_url.strip() if feed_homepage_url else None,
            display_name=feed_display_name.strip() if feed_display_name else None,
        )
        db.add(feed_config)
    elif provider_norm == "forward":
        if not forward_inbound_secret:
            raise ValueError("forward account requires inbound secret")
        db.add(
            ForwardAccountConfig(
                account_id=account.id,
                inbound_secret=forward_inbound_secret.strip(),
            )
        )
    db.commit()
    db.refresh(account)
    return account


def list_accounts(db: Session, *, user_id: int) -> list[ConnectedAccount]:
    return list(db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id == user_id).order_by(ConnectedAccount.id)))


def get_account(db: Session, *, user_id: int, account_id: int) -> ConnectedAccount | None:
    return db.scalar(
        select(ConnectedAccount).where(ConnectedAccount.user_id == user_id, ConnectedAccount.id == account_id)
    )


def get_account_by_provider_identifier(
    db: Session,
    *,
    user_id: int,
    provider: str,
    identifier: str,
) -> ConnectedAccount | None:
    provider_norm = provider.lower().strip()
    identifier_norm = identifier.strip()
    return db.scalar(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider_norm,
            ConnectedAccount.identifier == identifier_norm,
        )
    )


def upsert_oauth_account(
    db: Session,
    *,
    user_id: int,
    provider: str,
    identifier: str,
    access_token: str | None,
    refresh_token: str | None,
) -> ConnectedAccount:
    existing = get_account_by_provider_identifier(
        db,
        user_id=user_id,
        provider=provider,
        identifier=identifier,
    )
    if existing is not None:
        existing.access_token = encrypt_optional(access_token)
        existing.refresh_token = encrypt_optional(refresh_token)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    return create_connected_account(
        db,
        user_id=user_id,
        provider=provider,
        identifier=identifier,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def get_user_oauth_credentials(
    db: Session,
    *,
    user_id: int,
    provider: str,
) -> tuple[str, str] | None:
    provider_norm = provider.lower().strip()
    config = db.scalar(
        select(OAuthCredentialConfig).where(
            OAuthCredentialConfig.user_id == user_id,
            OAuthCredentialConfig.provider == provider_norm,
        )
    )
    if config is None:
        return None
    client_secret = decrypt_optional(config.client_secret) or ""
    if not config.client_id.strip() or not client_secret.strip():
        return None
    return config.client_id.strip(), client_secret.strip()


def upsert_user_oauth_credentials(
    db: Session,
    *,
    user_id: int,
    provider: str,
    client_id: str,
    client_secret: str,
) -> OAuthCredentialConfig:
    provider_norm = provider.lower().strip()
    config = db.scalar(
        select(OAuthCredentialConfig).where(
            OAuthCredentialConfig.user_id == user_id,
            OAuthCredentialConfig.provider == provider_norm,
        )
    )
    if config is None:
        config = OAuthCredentialConfig(
            user_id=user_id,
            provider=provider_norm,
            client_id=client_id.strip(),
            client_secret=encrypt_optional(client_secret.strip()) or "",
        )
        db.add(config)
    else:
        config.client_id = client_id.strip()
        config.client_secret = encrypt_optional(client_secret.strip()) or ""
        db.add(config)
    db.commit()
    db.refresh(config)
    return config


def upsert_contact(db: Session, *, user_id: int, handle: str, display_name: str) -> Contact:
    existing = db.scalar(select(Contact).where(Contact.user_id == user_id, Contact.handle == handle))
    if existing is not None:
        if display_name and existing.display_name != display_name:
            existing.display_name = display_name
        return existing
    contact = Contact(user_id=user_id, handle=handle, display_name=display_name or handle)
    db.add(contact)
    db.flush()
    return contact


def create_message(
    db: Session,
    *,
    user_id: int,
    contact_id: int,
    source: str,
    external_id: str | None,
    sender: str,
    subject: str,
    body: str,
    received_at: datetime,
    summary: str | None,
    skip_external_id_check: bool = False,
) -> Message | None:
    if external_id is not None and not skip_external_id_check:
        existing = db.scalar(
            select(Message).where(Message.user_id == user_id, Message.source == source, Message.external_id == external_id)
        )
        if existing is not None:
            return None
    preview = (body or "").strip().replace("\r\n", "\n").replace("\n", " ")
    preview = preview[:5000]
    msg = Message(
        user_id=user_id,
        contact_id=contact_id,
        source=source,
        external_id=external_id,
        sender=sender,
        subject=subject or "",
        body=body or "",
        body_preview=preview,
        received_at=received_at,
        summary=summary,
        is_read=False,
    )
    db.add(msg)
    return msg


def list_contacts(
    db: Session,
    *,
    user_id: int,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[tuple[Contact, int, str | None, str | None, str | None, datetime | None]]:
    unread_subq = (
        select(
            Message.contact_id.label("contact_id"),
            func.count(Message.id).label("unread_count"),
        )
        .where(Message.user_id == user_id, Message.is_read.is_(False))
        .group_by(Message.contact_id)
        .subquery()
    )

    ranked_subq = (
        select(
            Message.contact_id.label("contact_id"),
            Message.subject.label("subject"),
            Message.summary.label("summary"),
            Message.body_preview.label("body_preview"),
            Message.source.label("source"),
            Message.received_at.label("received_at"),
            func.row_number()
            .over(partition_by=Message.contact_id, order_by=(Message.received_at.desc(), Message.id.desc()))
            .label("rn"),
        )
        .where(Message.user_id == user_id)
        .subquery()
    )

    latest_subq = (
        select(
            ranked_subq.c.contact_id.label("contact_id"),
            ranked_subq.c.subject.label("subject"),
            func.coalesce(ranked_subq.c.summary, ranked_subq.c.body_preview).label("preview"),
            ranked_subq.c.source.label("source"),
            ranked_subq.c.received_at.label("received_at"),
        )
        .where(ranked_subq.c.rn == 1)
        .subquery()
    )

    query = (
        select(
            Contact,
            func.coalesce(unread_subq.c.unread_count, 0).label("unread_count"),
            latest_subq.c.subject.label("latest_subject"),
            latest_subq.c.preview.label("latest_preview"),
            latest_subq.c.source.label("latest_source"),
            latest_subq.c.received_at.label("latest_received_at"),
        )
        .where(Contact.user_id == user_id)
        .outerjoin(unread_subq, unread_subq.c.contact_id == Contact.id)
        .outerjoin(latest_subq, latest_subq.c.contact_id == Contact.id)
    )

    if q:
        q_like = f"%{q.lower()}%"
        query = query.where(
            func.lower(Contact.display_name).like(q_like) | func.lower(Contact.handle).like(q_like)
        )

    query = (
        query.order_by(Contact.last_message_at.desc().nullslast(), Contact.id.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(query).all()
    return [
        (
            row[0],
            int(row.unread_count or 0),
            row.latest_subject,
            row.latest_preview,
            row.latest_source,
            row.latest_received_at,
        )
        for row in rows
    ]


def get_contact_by_id(db: Session, *, user_id: int, contact_id: int) -> Contact | None:
    return db.scalar(select(Contact).where(Contact.user_id == user_id, Contact.id == contact_id))


def list_messages(
    db: Session,
    *,
    user_id: int,
    contact_id: int,
    limit: int = 50,
    before: tuple[datetime, int] | None = None,
) -> list[Message]:
    query = select(Message).where(Message.user_id == user_id, Message.contact_id == contact_id)
    if before is not None:
        before_received_at, before_id = before
        query = query.where(
            (Message.received_at < before_received_at)
            | ((Message.received_at == before_received_at) & (Message.id < before_id))
        )

    return list(
        db.scalars(query.order_by(Message.received_at.desc(), Message.id.desc()).limit(limit))
    )


def get_message(db: Session, *, user_id: int, message_id: int) -> Message | None:
    return db.scalar(select(Message).where(Message.user_id == user_id, Message.id == message_id))


def mark_contact_read(db: Session, *, user_id: int, contact_id: int) -> int:
    result = db.execute(
        update(Message)
        .where(Message.user_id == user_id, Message.contact_id == contact_id, Message.is_read.is_(False))
        .values(is_read=True)
    )
    return int(result.rowcount or 0)


def delete_connected_account(db: Session, *, user_id: int, account_id: int) -> bool:
    account = get_account(db, user_id=user_id, account_id=account_id)
    if account is None:
        return False
    db.delete(account)
    db.commit()
    return True


def update_user(
    db: Session, *, user: User, email: str | None = None, password: str | None = None, avatar_url: str | None = None
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


def decrypt_account_tokens(account: ConnectedAccount) -> tuple[str | None, str | None]:
    return decrypt_optional(account.access_token), decrypt_optional(account.refresh_token)


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
    if api_key is not None:
        config.api_key = encrypt_optional(api_key.strip())
    if web_search_proxy_url is not None:
        clean_proxy = web_search_proxy_url.strip()
        config.web_search_proxy_url = clean_proxy or None

    db.commit()
    db.refresh(config)
    return config


def touch_contact_last_message(db: Session, *, contact: Contact, received_at: datetime) -> None:
    received_utc = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
    current = contact.last_message_at
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if current is None or received_utc > current:
        contact.last_message_at = received_utc


def touch_account_sync(db: Session, *, account: ConnectedAccount) -> None:
    account.last_synced_at = datetime.now(timezone.utc)


def ensure_feed_account_config(
    db: Session,
    *,
    account_id: int,
    feed_url: str | None = None,
    homepage_url: str | None = None,
    display_name: str | None = None,
) -> FeedAccountConfig:
    config = db.get(FeedAccountConfig, account_id)
    if config:
        return config

    config = FeedAccountConfig(
        account_id=account_id,
        feed_url=feed_url or "",
        homepage_url=homepage_url.strip() if homepage_url else None,
        display_name=display_name.strip() if display_name else None,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config
