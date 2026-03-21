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
    remote_commands: Mapped[list["RemoteCommand"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    message_topic_tags: Mapped[list["MessageTopicTag"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    followed_tags: Mapped[list["UserFollowedTag"]] = relationship(
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
    web_search_proxy_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

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


class RemoteCommand(Base):
    __tablename__ = "remote_commands"
    __table_args__ = (
        Index("ix_remote_commands_user_workspace_created", "user_id", "workspace", "created_at"),
        Index("ix_remote_commands_status_updated", "status", "updated_at"),
        Index("ix_remote_commands_source_message", "source", "source_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace: Mapped[str] = mapped_column(String(64), default="default", index=True)

    source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    source_open_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    source_chat_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    source_user_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    command_type: Mapped[str] = mapped_column(String(64), default="help", index=True)
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="remote_commands")



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
    topic_tags: Mapped[list["MessageTopicTag"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MessageTopicTag(Base):
    __tablename__ = "message_topic_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", "tag", name="uq_message_topic_tag"),
        Index("ix_message_topic_tags_user_message", "user_id", "message_id"),
        Index("ix_message_topic_tags_user_tag", "user_id", "tag"),
        Index("ix_message_topic_tags_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    method: Mapped[str] = mapped_column(String(16), default="rule")  # rule | llm | hybrid
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="message_topic_tags")
    message: Mapped["Message"] = relationship(back_populates="topic_tags")


class UserFollowedTag(Base):
    __tablename__ = "user_followed_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "tag", name="uq_user_followed_tag"),
        Index("ix_user_followed_tags_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="followed_tags")


class AttachmentDocument(Base):
    __tablename__ = "attachment_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace", "sha256", name="uq_attachment_user_workspace_sha256"),
        Index("ix_attachment_documents_user_workspace_created", "user_id", "workspace", "created_at"),
        Index("ix_attachment_documents_user_session_created", "user_id", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace: Mapped[str] = mapped_column(String(64), default="default", index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_ext: Mapped[str] = mapped_column(String(16), default="")
    mime_type: Mapped[str] = mapped_column(String(160), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    storage_path: Mapped[str] = mapped_column(String(1024), default="")
    parse_status: Mapped[str] = mapped_column(String(16), default="ready", index=True)  # ready | failed
    parse_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chunks: Mapped[list["AttachmentChunk"]] = relationship(
        back_populates="attachment",
        cascade="all, delete-orphan",
    )


class AttachmentChunk(Base):
    __tablename__ = "attachment_chunks"
    __table_args__ = (
        UniqueConstraint("attachment_id", "chunk_index", name="uq_attachment_chunk_index"),
        Index("ix_attachment_chunks_attachment_created", "attachment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachment_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    keyword_vector_json: Mapped[str] = mapped_column(Text, default="{}")
    loc_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attachment: Mapped["AttachmentDocument"] = relationship(back_populates="chunks")
