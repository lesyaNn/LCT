"""Canonical website applications and per-source sync metadata."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ExternalApplication(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "external_applications"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_external_applications_source_id"),
        Index("ix_external_applications_university_program", "university_id", "program_id"),
        Index("ix_external_applications_created_at", "external_created_at"),
        Index("ix_external_applications_workflow_instance_id", "workflow_instance_id"),
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    ingest_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    university_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True)
    program_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("it_programs.id", ondelete="RESTRICT"), nullable=True)
    person_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flow_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workflow_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="SET NULL"), nullable=True
    )


class ExternalSyncState(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "external_sync_states"
    __table_args__ = (UniqueConstraint("university_id", "source", name="uq_external_sync_states_university_source"),)

    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
