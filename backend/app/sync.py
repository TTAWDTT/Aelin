from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
import urllib.parse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import IncomingMessage
from app.connectors.feed import FeedConnector
from app.connectors.gmail import GmailConnector
from app.connectors.github import GitHubNotificationsConnector
from app.connectors.imap import ImapConnector
from app.connectors.mock import MockConnector
from app.connectors.outlook import OutlookConnector
from app.connectors.bilibili import BilibiliConnector
from app.connectors.x import XConnector
from app.connectors.douyin import DouyinConnector, _extract_sec_uid as extract_douyin_uid
from app.connectors.xiaohongshu import XiaohongshuConnector, _extract_user_id as extract_xhs_uid
from app.connectors.weibo import WeiboConnector, _extract_uid as extract_weibo_uid
from app.crud import (
    create_message,
    decrypt_account_tokens,
    get_user_oauth_credentials,
    touch_account_sync,
    touch_contact_last_message,
    get_agent_config,
)
from app.models import ConnectedAccount, Contact, FeedAccountConfig, ImapAccountConfig, Message, XApiConfig
from app.services.encryption import decrypt_optional, encrypt_optional
from app.services.feed_urls import normalize_feed_url
from app.services.llm import LLMService
from app.services.oauth_clients import refresh_access_token
from app.services.summarizer import RuleBasedSummarizer
from app.services.avatar import gravatar_url_for_email, normalize_http_avatar_url
from app.services import content_tagging
from app.schemas import AgentConfigOut
from app.settings import settings

_X_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{1,15}")


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _connector_for(db: Session, account: ConnectedAccount):
    access_token, _refresh = decrypt_account_tokens(account)
    provider = account.provider.lower()

    if provider == "mock":
        return MockConnector()
    if provider == "forward":
        class _NoopConnector:
            def fetch_new_messages(self, *, since):
                return []

        return _NoopConnector()
    if provider == "github":
        if not access_token:
            raise ValueError("GitHub account requires access_token")
        return GitHubNotificationsConnector(access_token)
    if provider == "gmail":
        if not access_token:
            raise ValueError("Gmail account requires access_token")
        return GmailConnector(access_token=access_token)
    if provider == "outlook":
        if not access_token:
            raise ValueError("Outlook account requires access_token")
        return OutlookConnector(access_token=access_token)
    if provider == "imap":
        config = db.get(ImapAccountConfig, account.id)
        if config is None:
            raise ValueError("IMAP account requires configuration")

        password = decrypt_optional(config.password)
        if not password:
            raise ValueError("IMAP account requires password")

        return ImapConnector(
            host=config.host,
            port=int(config.port),
            use_ssl=bool(config.use_ssl),
            username=config.username,
            password=password,
            mailbox=config.mailbox or "INBOX",
            external_id_prefix=f"imap:{account.id}",
        )
    if provider == "x":
        config = db.get(FeedAccountConfig, account.id)
        if config is None:
            raise ValueError("x account requires feed configuration")
        normalized_feed_url = normalize_feed_url(config.feed_url) if config.feed_url else None
        if normalized_feed_url and normalized_feed_url != config.feed_url:
            config.feed_url = normalized_feed_url
            db.add(config)
            db.flush()
        username_hint = (
            account.identifier
            or (config.homepage_url or "")
            or (config.feed_url or "")
        )
        # 从数据库读取用户配置的 X API Bearer Token 和 Cookie
        x_api_config = db.query(XApiConfig).filter(XApiConfig.user_id == account.user_id).first()
        bearer_token = decrypt_optional(x_api_config.bearer_token) if x_api_config else None
        auth_cookies = None
        if x_api_config and x_api_config.auth_cookies:
            import json as _json
            try:
                cookies_payload = decrypt_optional(x_api_config.auth_cookies) or ""
                auth_cookies = _json.loads(cookies_payload) if cookies_payload else None
            except Exception:
                auth_cookies = None
        return XConnector(
            username=username_hint,
            fallback_feed_url=normalized_feed_url,
            default_sender=(config.display_name or account.identifier or "x"),
            bearer_token=bearer_token,
            auth_cookies=auth_cookies,
        )
    if provider == "bilibili":
        config = db.get(FeedAccountConfig, account.id)
        if config is None:
            raise ValueError("bilibili account requires feed configuration")
        normalized_feed_url = normalize_feed_url(config.feed_url) if config.feed_url else None
        if normalized_feed_url and normalized_feed_url != config.feed_url:
            config.feed_url = normalized_feed_url
            db.add(config)
            db.flush()
        uid_hint = account.identifier
        if not uid_hint and config.homepage_url:
            uid_hint = config.homepage_url
        if not uid_hint and config.feed_url:
            uid_hint = config.feed_url
        return BilibiliConnector(
            uid=uid_hint or "",
            fallback_feed_url=normalized_feed_url,
            default_sender=(config.display_name or account.identifier or "Bilibili"),
        )
    if provider == "douyin":
        config = db.get(FeedAccountConfig, account.id)
        if config is None:
            raise ValueError("douyin account requires feed configuration")

        # 自动升级为 RSSHub 模式（仅作为 fallback）
        if not config.feed_url:
            sec_uid = extract_douyin_uid(account.identifier)
            if sec_uid:
                config.feed_url = f"{settings.rsshub_base_url.rstrip('/')}/douyin/user/{sec_uid}"
                db.add(config)
                db.flush()

        sec_uid_hint = account.identifier
        if not sec_uid_hint and config.homepage_url:
            sec_uid_hint = config.homepage_url
        return DouyinConnector(
            sec_uid=sec_uid_hint or "",
            fallback_feed_url=normalize_feed_url(config.feed_url) if config.feed_url else None,
            default_sender=(config.display_name or account.identifier or "抖音用户"),
            timeout_seconds=60,
        )
    if provider == "xiaohongshu":
        config = db.get(FeedAccountConfig, account.id)
        if config is None:
            raise ValueError("xiaohongshu account requires feed configuration")

        # 自动升级为 RSSHub 模式（仅作为 fallback）
        if not config.feed_url:
            user_id = extract_xhs_uid(account.identifier)
            if user_id:
                config.feed_url = f"{settings.rsshub_base_url.rstrip('/')}/xiaohongshu/user/{user_id}"
                db.add(config)
                db.flush()

        user_id_hint = account.identifier
        if not user_id_hint and config.homepage_url:
            user_id_hint = config.homepage_url
        return XiaohongshuConnector(
            user_id=user_id_hint or "",
            fallback_feed_url=normalize_feed_url(config.feed_url) if config.feed_url else None,
            default_sender=(config.display_name or account.identifier or "小红书用户"),
            timeout_seconds=60,
        )
    if provider == "weibo":
        config = db.get(FeedAccountConfig, account.id)
        if config is None:
            raise ValueError("weibo account requires feed configuration")

        # 自动升级为 RSSHub 模式（仅作为 fallback）
        if not config.feed_url:
            uid = extract_weibo_uid(account.identifier)
            if uid:
                config.feed_url = f"{settings.rsshub_base_url.rstrip('/')}/weibo/user/{uid}"
                db.add(config)
                db.flush()

        uid_hint = account.identifier
        if not uid_hint and config.homepage_url:
            uid_hint = config.homepage_url
        return WeiboConnector(
            uid=uid_hint or "",
            fallback_feed_url=normalize_feed_url(config.feed_url) if config.feed_url else None,
            default_sender=(config.display_name or account.identifier or "微博用户"),
            timeout_seconds=60,
        )
    if provider == "rss":
        config = db.get(FeedAccountConfig, account.id)
        if config is None or not config.feed_url:
            raise ValueError(f"{provider} account requires feed configuration")
        normalized_feed_url = normalize_feed_url(config.feed_url)
        if normalized_feed_url != config.feed_url:
            config.feed_url = normalized_feed_url
            if provider == "rss" and (config.homepage_url or "").strip() in {"", "https://www.anthropic.com/news"}:
                config.homepage_url = "https://claude.com/blog/"
            db.add(config)
            db.flush()
        return FeedConnector(
            feed_url=normalized_feed_url,
            source=provider,
            default_sender=(config.display_name or account.identifier or provider),
        )
    raise ValueError(f"Unknown provider: {account.provider}")


def _try_refresh_oauth_token(db: Session, *, account: ConnectedAccount) -> bool:
    provider = account.provider.lower().strip()
    if provider not in {"gmail", "outlook"}:
        return False
    _access_token, refresh_token = decrypt_account_tokens(account)
    if not refresh_token:
        return False
    credentials = get_user_oauth_credentials(
        db,
        user_id=account.user_id,
        provider=provider,
    )
    client_id, client_secret = credentials if credentials else (None, None)
    try:
        next_access, next_refresh = refresh_access_token(
            provider=provider,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    except Exception:
        return False
    account.access_token = encrypt_optional(next_access)
    if next_refresh:
        account.refresh_token = encrypt_optional(next_refresh)
    db.add(account)
    db.flush()
    return True


def _refresh_contact_avatars(
    db: Session,
    *,
    user_id: int,
    incoming_messages: list[IncomingMessage],
) -> None:
    handles = {message.sender for message in incoming_messages if message.sender and message.sender_avatar_url}
    if not handles:
        return

    contacts = list(db.scalars(select(Contact).where(Contact.user_id == user_id, Contact.handle.in_(handles))))
    contacts_by_handle = {contact.handle: contact for contact in contacts}
    for message in incoming_messages:
        if not message.sender_avatar_url:
            continue
        contact = contacts_by_handle.get(message.sender)
        if contact is None:
            continue
        normalized_avatar = normalize_http_avatar_url(message.sender_avatar_url) or message.sender_avatar_url.strip()
        if normalized_avatar and contact.avatar_url != normalized_avatar:
            contact.avatar_url = normalized_avatar
            db.add(contact)


def _x_sender_hint(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if candidate.lower().startswith("x:"):
        candidate = candidate[2:]
    if "://" in candidate or "x.com/" in candidate.lower() or "twitter.com/" in candidate.lower():
        parsed = urllib.parse.urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = (parsed.netloc or "").lower().strip()
        parts = [part for part in (parsed.path or "").split("/") if part]
        if host.endswith("x.com") or host.endswith("twitter.com"):
            candidate = parts[0] if parts else candidate
    candidate = candidate.lstrip("@").strip()
    matched = _X_USERNAME_RE.search(candidate)
    if not matched:
        return None
    return f"@{matched.group(0).lower()}"


def _needs_source_backfill(db: Session, *, account: ConnectedAccount) -> bool:
    provider = account.provider.lower().strip()
    if provider == "x":
        sender_hint = _x_sender_hint(account.identifier)
        if not sender_hint:
            return True
        exists = db.scalar(
            select(Message.id).where(
                Message.user_id == account.user_id,
                Message.source == "x",
                func.lower(Message.sender) == sender_hint,
            ).limit(1)
        )
        return exists is None
    if provider == "bilibili":
        exists = db.scalar(
            select(Message.id).where(
                Message.user_id == account.user_id,
                Message.source == "bilibili",
            ).limit(1)
        )
        return exists is None
    return False


def sync_account(db: Session, *, account: ConnectedAccount, force_full: bool = False) -> int:
    connector = _connector_for(db, account)
    rule_summarizer = RuleBasedSummarizer()

    # Initialize LLM Service if configured
    llm_service: LLMService | None = None
    agent_config = get_agent_config(db, user_id=account.user_id)
    if agent_config and agent_config.provider != "rule_based":
        api_key = decrypt_optional(agent_config.api_key)
        if api_key and agent_config.base_url:
            try:
                config_out = AgentConfigOut(
                    provider=agent_config.provider,
                    base_url=agent_config.base_url,
                    model=agent_config.model,
                    temperature=agent_config.temperature,
                    has_api_key=True
                )
                llm_service = LLMService(config_out, api_key)
            except Exception:
                pass  # Fallback to rule-based

    since = None if force_full else _normalize_utc(account.last_synced_at)
    provider = account.provider.lower().strip()
    recent_messages: list[IncomingMessage] = []

    try:
        incoming_messages = connector.fetch_new_messages(since=since)
    except ValueError as error:
        if _try_refresh_oauth_token(db, account=account):
            connector = _connector_for(db, account)
            incoming_messages = connector.fetch_new_messages(since=since)
        else:
            raise error
    if (
        not incoming_messages
        and since is not None
        and provider in {"x", "bilibili"}
        and _needs_source_backfill(db, account=account)
    ):
        try:
            recent_messages = connector.fetch_new_messages(since=None)
        except Exception:
            recent_messages = []
        if recent_messages:
            incoming_messages = recent_messages
    if not incoming_messages:
        if provider in {"x", "bilibili", "rss"}:
            if not recent_messages:
                try:
                    recent_messages = connector.fetch_new_messages(since=None)
                except Exception:
                    recent_messages = []
            _refresh_contact_avatars(
                db,
                user_id=account.user_id,
                incoming_messages=recent_messages,
            )
        touch_account_sync(db, account=account)
        db.commit()
        return 0

    handles = {m.sender for m in incoming_messages}
    existing_contacts = list(
        db.scalars(select(Contact).where(Contact.user_id == account.user_id, Contact.handle.in_(handles)))
    )
    contacts_by_handle: dict[str, Contact] = {c.handle: c for c in existing_contacts}

    for handle in handles - set(contacts_by_handle):
        contact = Contact(user_id=account.user_id, handle=handle, display_name=handle)
        db.add(contact)
        contacts_by_handle[handle] = contact
    db.flush()

    # Deduplicate by external_id in bulk (per source) to avoid per-message queries.
    external_ids_by_source: dict[str, list[str]] = defaultdict(list)
    for m in incoming_messages:
        if m.external_id:
            external_ids_by_source[m.source].append(m.external_id)

    existing_external_ids: dict[str, set[str]] = {}
    for source, ids in external_ids_by_source.items():
        if not ids:
            existing_external_ids[source] = set()
            continue
        existing_external_ids[source] = set(
            db.scalars(
                select(Message.external_id).where(
                    Message.user_id == account.user_id,
                    Message.source == source,
                    Message.external_id.in_(ids),
                )
            )
        )

    inserted = 0
    inserted_message_ids: list[int] = []
    for incoming in incoming_messages:
        contact = contacts_by_handle[incoming.sender]
        if incoming.sender_avatar_url:
            normalized_avatar = normalize_http_avatar_url(incoming.sender_avatar_url) or incoming.sender_avatar_url.strip()
            if normalized_avatar and contact.avatar_url != normalized_avatar:
                contact.avatar_url = normalized_avatar
                db.add(contact)
        elif not contact.avatar_url:
            # 没有来源头像也没有已存头像时，尝试用 Gravatar 作为兜底
            gravatar = gravatar_url_for_email(incoming.sender)
            if gravatar:
                contact.avatar_url = gravatar
                db.add(contact)

        if incoming.external_id and incoming.external_id in existing_external_ids.get(incoming.source, set()):
            continue

        received_at = _normalize_utc(incoming.received_at) or datetime.now(timezone.utc)

        summary = None
        # Skip summary for feeds unless explicitly requested (future feature)
        # For now, we only summarize personal messages (email, etc) or if needed
        if incoming.source not in {"rss", "bilibili", "x"}:
            if llm_service and llm_service.is_configured():
                try:
                    # Synchronous summary generation
                    summary = str(llm_service.summarize(incoming.body, stream=False))
                except Exception:
                    summary = rule_summarizer.summarize(incoming.body)
            else:
                summary = rule_summarizer.summarize(incoming.body)

        msg = create_message(
            db,
            user_id=account.user_id,
            contact_id=contact.id,
            source=incoming.source,
            external_id=incoming.external_id,
            sender=incoming.sender,
            subject=incoming.subject,
            body=incoming.body,
            received_at=received_at,
            summary=summary,
            skip_external_id_check=True,
        )
        if msg is None:
            continue
        if getattr(msg, "id", None) is None:
            db.flush()
        inserted += 1
        inserted_message_ids.append(int(msg.id))
        touch_contact_last_message(db, contact=contact, received_at=received_at)

    touch_account_sync(db, account=account)
    db.commit()
    if inserted_message_ids:
        content_tagging.enqueue_tagging_job(
            user_id=account.user_id,
            message_ids=inserted_message_ids,
            allow_llm=True,
        )
    return inserted
