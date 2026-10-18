"""Private Markdown notes, owned by a Keycloak subject."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class NoteFolder(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "note_folders"
    __table_args__ = (UniqueConstraint("owner_sub", "name", name="uq_note_folders_owner_name"),)

    owner_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class PersonalNote(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "personal_notes"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_personal_notes_revision"),
        Index("ix_personal_notes_owner_updated", "owner_sub", "updated_at"),
        Index("ix_personal_notes_owner_folder", "owner_sub", "folder_id"),
        Index("ix_personal_notes_owner_deleted", "owner_sub", "deleted_at"),
        Index("ix_personal_notes_search_trgm", "search_text", postgresql_using="gin",
              postgresql_ops={"search_text": "gin_trgm_ops"}),
    )

    owner_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="Без названия")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    folder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("note_folders.id", ondelete="SET NULL"), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
