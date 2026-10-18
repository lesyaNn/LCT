"""Personal Markdown notes; ownership is the authenticated Keycloak subject."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Note(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_owner_updated", "owner_sub", "updated_at"),
        CheckConstraint("revision >= 0", name="note_revision"),
    )

    owner_sub: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class NoteOnboarding(Base):
    """Remember initialization even when the owner deletes their welcome note."""

    __tablename__ = "note_onboarding"

    owner_sub: Mapped[str] = mapped_column(Text, primary_key=True)
    initialized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
