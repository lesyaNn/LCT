"""Durable delivery state for a notification's email channel."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class NotificationDelivery(UUIDPKMixin, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_notification_deliveries_channel"),
        Index("ix_notification_deliveries_due", "status", "next_attempt_at"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(native_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
