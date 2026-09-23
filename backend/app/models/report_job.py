"""ORM mirror of 000018_report_jobs; SQL migrations own DDL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class ReportJob(UUIDPKMixin, Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','building','ready','failed')", name="ck_report_jobs_status"
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_report_jobs_progress"),
        CheckConstraint("format IN ('xlsx','pdf','json')", name="ck_report_jobs_format"),
        Index("ix_report_jobs_user", "user_id"),
        Index("ix_report_jobs_status_created", "status", "created_at"),
        Index("ix_report_jobs_expires", "expires_at"),
    )

    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    university_id: Mapped[UUID | None] = mapped_column(nullable=True)
    # NULL = global manager/admin; [] = empty scope, NEVER global.
    scope_ids: Mapped[list[str] | None] = mapped_column(JSONB().with_variant(JSON, "sqlite"))
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    columns: Mapped[list[str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
