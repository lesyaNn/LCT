import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class AuditOutbox(Base):
    __tablename__ = "audit_outbox"
    __table_args__ = (Index("ix_audit_outbox_claim", "status", "available_at", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
