"""Private documentation conversations. One persisted turn is a complete Q/A pair."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class AssistantConversation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'manager', 'admin')", name="assistant_role"),
        CheckConstraint("revision >= 0", name="assistant_revision"),
        Index("ix_assistant_conversations_owner_updated", "owner_sub", "updated_at"),
    )

    owner_sub: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssistantTurn(UUIDPKMixin, Base):
    __tablename__ = "assistant_turns"
    __table_args__ = (
        Index("uq_assistant_turns_position", "conversation_id", "position", unique=True),
        CheckConstraint("position > 0", name="assistant_turn_position"),
        CheckConstraint(
            "basis IN ('documentation', 'inference', 'insufficient')", name="assistant_basis"
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    basis: Mapped[str] = mapped_column(String(24), nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False)
    knowledge_version: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
