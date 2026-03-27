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

    agent_config: Mapped[Optional["AgentConfig"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    remote_commands: Mapped[list["RemoteCommand"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    provider: Mapped[str] = mapped_column(String(50), default="rule_based")
    base_url: Mapped[str] = mapped_column(String(2048), default="https://api.openai.com/v1")
    model: Mapped[str] = mapped_column(String(255), default="gpt-4o-mini")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    web_search_proxy_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_config")


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
    parse_status: Mapped[str] = mapped_column(String(16), default="ready", index=True)
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
