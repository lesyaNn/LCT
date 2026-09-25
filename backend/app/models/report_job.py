"""P4-06-01: canonical ``ReportJob`` ORM model (async report execution).

Table ``report_jobs`` is owned by SQL migrations ``000018_report_jobs`` +
``000019_import_jobs`` (the sole schema source); this model only maps it. The security snapshot
is canonical multi-scope (``actor_sub`` / ``actor_roles`` /
``effective_university_ids``) — a single legacy ``university_id`` column
would lose the multi-university intersection, so it is deliberately
absent. ``effective_university_ids`` mirrors :class:`CurrentUser` exactly:
``None`` = global (admin / pre-existing global RBAC), ``[]`` = empty
scope (fails closed to zero rows via the shared security applicator).

Dev-3 (000019) shares the ledger for XLSX import jobs (``job_type`` /
``payload`` / ``result`` / ``idempotency_key``); report rows keep
``job_type='report'``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid as SAUuid

from app.db.base import Base
from app.models.mixins import UUIDPKMixin

#: Single source of truth for the job lifecycle (mirrored by the SQL CHECK).
REPORT_JOB_STATUSES: tuple[str, ...] = ("queued", "building", "ready", "failed")

STATUS_QUEUED = "queued"
STATUS_BUILDING = "building"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


#: Job kinds sharing this ledger (000019; reports predate the column).
JOB_TYPE_REPORT = "report"
JOB_TYPE_XLSX_IMPORT = "xlsx_import"


class ReportJob(UUIDPKMixin, Base):
    """One async analytics report (``queued -> building -> ready|failed``)."""

    __tablename__ = "report_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(native_uuid=True), primary_key=True, default=uuid.uuid4
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False
    )
    columns: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False
    )
    actor_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    actor_roles: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    effective_university_ids: Mapped[list[str] | None] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(nullable=False, default=0)
    # P4-06-01 retries (000020): incremented on every atomic claim; a failed
    # attempt with attempts < MAX_JOB_ATTEMPTS is requeued, else failed.
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    # Dev-3 import extension (000019): job kind, worker params, terminal
    # summary and re-POST dedup key. Report rows keep job_type='report'.
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_TYPE_REPORT)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False, default=dict
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=True, default=None
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = [
    "JOB_TYPE_REPORT",
    "JOB_TYPE_XLSX_IMPORT",
    "STATUS_BUILDING",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_READY",
    "REPORT_JOB_STATUSES",
    "ReportJob",
]
