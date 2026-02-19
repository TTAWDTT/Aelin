from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list["ConnectedAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_credentials: Mapped[list["OAuthCredentialConfig"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[list["Contact"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    agent_config: Mapped[Optional["AgentConfig"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    x_api_config: Mapped[Optional["XApiConfig"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    agent_memory: Mapped[Optional["AgentConversationMemory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    agent_memory_notes: Mapped[list["AgentMemoryNote"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tracking_targets: Mapped[list["TrackingTarget"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider", "identifier", name="uq_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    provider: Mapped[str] = mapped_column(String(50), index=True)  # e.g. imap, gmail, github, mock
    identifier: Mapped[str] = mapped_column(String(255), index=True)  # email / username

    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="accounts")
    imap_config: Mapped[Optional["ImapAccountConfig"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    feed_config: Mapped[Optional["FeedAccountConfig"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    forward_config: Mapped[Optional["ForwardAccountConfig"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ImapAccountConfig(Base):
    __tablename__ = "imap_account_configs"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=993)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    username: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(Text)  # stored encrypted if FERNET_KEY is configured
    mailbox: Mapped[str] = mapped_column(String(255), default="INBOX")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["ConnectedAccount"] = relationship(back_populates="imap_config")


class FeedAccountConfig(Base):
    __tablename__ = "feed_account_configs"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    feed_url: Mapped[str] = mapped_column(String(2048))
    homepage_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["ConnectedAccount"] = relationship(back_populates="feed_config")


class ForwardAccountConfig(Base):
    __tablename__ = "forward_account_configs"
    __table_args__ = (UniqueConstraint("inbound_secret", name="uq_forward_inbound_secret"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    inbound_secret: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["ConnectedAccount"] = relationship(back_populates="forward_config")


class OAuthCredentialConfig(Base):
    __tablename__ = "oauth_credential_configs"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_oauth_credential_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    client_id: Mapped[str] = mapped_column(String(512))
    client_secret: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="oauth_credentials")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    provider: Mapped[str] = mapped_column(String(50), default="rule_based")  # rule_based/openai
    base_url: Mapped[str] = mapped_column(String(2048), default="https://api.openai.com/v1")
    model: Mapped[str] = mapped_column(String(255), default="gpt-4o-mini")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # stored encrypted if FERNET_KEY is configured

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_config")


class XApiConfig(Base):
    """Stores X (Twitter) API configuration per user"""
    __tablename__ = "x_api_configs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    bearer_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_cookies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: {"auth_token": "...", "ct0": "..."}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="x_api_config")


class AgentConversationMemory(Base):
    __tablename__ = "agent_conversation_memories"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_memory")


class AgentMemoryNote(Base):
    __tablename__ = "agent_memory_notes"
    __table_args__ = (
        Index("ix_agent_memory_notes_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="note")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_memory_notes")




class TrackingTarget(Base):
    __tablename__ = "tracking_targets"
    __table_args__ = (
        Index("ix_tracking_targets_user_workspace_status_next", "user_id", "workspace", "status", "next_run_at"),
        Index("ix_tracking_targets_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    workspace: Mapped[str] = mapped_column(String(64), default="default", index=True)
    track_type: Mapped[str] = mapped_column(String(16), default="term", index=True)  # term | url
    source_type: Mapped[str] = mapped_column(String(32), default="web", index=True)
    source_key: Mapped[str] = mapped_column(String(1024), default="", index=True)  # normalized term/url key
    display_name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")

    track_mode: Mapped[str] = mapped_column(String(16), default="poll")  # poll | webhook | hybrid
    interval_seconds: Mapped[int] = mapped_column(Integer, default=120)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active | paused | error | deleted
    config_ready: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notify_level: Mapped[str] = mapped_column(String(16), default="all")  # all | important | critical
    mute_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    quiet_hours_json: Mapped[str] = mapped_column(Text, default='{"enabled":false}')

    is_temporary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_change_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="tracking_targets")
    snapshots: Mapped[list["TrackingSnapshot"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
    )
    changes: Mapped[list["TrackingChange"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
    )


class TrackingSnapshot(Base):
    __tablename__ = "tracking_snapshots"
    __table_args__ = (
        Index("ix_tracking_snapshots_target_version", "target_id", "version_no"),
        Index("ix_tracking_snapshots_target_fetched", "target_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("tracking_targets.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)

    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    normalized_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    fetch_status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | partial | failed
    fetch_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    target: Mapped["TrackingTarget"] = relationship(back_populates="snapshots")


class TrackingChange(Base):
    __tablename__ = "tracking_changes"
    __table_args__ = (
        Index("ix_tracking_changes_target_created", "target_id", "created_at"),
        Index("ix_tracking_changes_target_ack", "target_id", "acked", "created_at"),
        Index("ix_tracking_changes_target_notified", "target_id", "notified", "created_at"),
        Index("ix_tracking_changes_dedupe", "dedupe_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("tracking_targets.id", ondelete="CASCADE"), index=True)
    from_snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tracking_snapshots.id", ondelete="SET NULL"), nullable=True)
    to_snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tracking_snapshots.id", ondelete="SET NULL"), nullable=True)

    change_type: Mapped[str] = mapped_column(String(32), default="updated_item", index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    dedupe_key: Mapped[str] = mapped_column(String(180), default="", index=True)

    notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    target: Mapped["TrackingTarget"] = relationship(back_populates="changes")
class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "handle", name="uq_contact_handle"),
        Index("ix_contacts_user_last_message_at", "user_id", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    display_name: Mapped[str] = mapped_column(String(255))
    handle: Mapped[str] = mapped_column(String(255), index=True)  # email or github handle
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="contacts")
    messages: Mapped[list["Message"]] = relationship(back_populates="contact", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_id", name="uq_message_external"),
        Index("ix_messages_user_contact_received", "user_id", "contact_id", "received_at", "id"),
        Index("ix_messages_user_contact_is_read", "user_id", "contact_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)

    source: Mapped[str] = mapped_column(String(50), index=True)  # email/github/news/mock
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    sender: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(998), default="")
    body_preview: Mapped[str] = mapped_column(String(5000), default="")
    body: Mapped[str] = mapped_column(Text, default="")

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="messages")
    contact: Mapped["Contact"] = relationship(back_populates="messages")

