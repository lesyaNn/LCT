"""P4-06-01 report job persistence (repository + service helpers).

Single home for ``report_jobs`` DB access — the router never writes job
persistence inline. Lifecycle (single source of truth, mirrored by the
``000018`` SQL CHECK)::

    queued -> building -> ready | failed

Progress floor (no fake granular callbacks in the exporters)::

    queued = 0, building = 10, ready = 100, failed = current value kept.

Security snapshot: every job stores the actor's effective context
(``actor_sub`` / ``actor_roles`` / ``effective_university_ids``) taken at
creation time, so the background worker re-applies the SAME intersection
instead of running as admin/global. ``effective_university_ids`` mirrors
:class:`CurrentUser` exactly: ``None`` = global (admin / pre-existing
global RBAC), ``[]`` = empty scope (fails closed to zero rows via the
shared security applicator).

Filenames are server-generated (``report_<job_id>.<ext>``) — never taken
from the user — and every download path is containment-checked against
the configured reports root (traversal-safe).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.report_job import (
    REPORT_JOB_STATUSES,
    STATUS_BUILDING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
    ReportJob,
)

logger = logging.getLogger("rtk")

__all__ = [
    "REPORT_EXPIRY_HOURS",
    "REPORT_JOB_STATUSES",
    "STATUS_BUILDING",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_READY",
    "cleanup_expired_report_jobs",
    "contained_job_path",
    "create_job",
    "get_job",
    "job_file_path",
    "job_filename",
    "job_visible_to",
    "list_visible_jobs",
    "mark_building",
    "mark_failed",
    "mark_ready",
    "reports_root",
    "run_cleanup_once",
    "sanitize_error_message",
]

#: Report download window after creation (``expires_at = created + 24h``).
REPORT_EXPIRY_HOURS = 24

#: Allowed download extensions (frozen ``ReportFormat`` values).
_JOB_FILENAME_RE = re.compile(r"report_[0-9a-fA-F-]{36}\.(xlsx|pdf|json)")

#: Secret-looking ``key=value`` fragments are redacted from user errors.
_SECRET_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def reports_root() -> Path:
    """Configured reports storage root (never the public static root).

    ``REPORTS_DIR`` is honored as a legacy alias (existing XLSX/PDF/JSON
    exporters read it); ``REPORTS_ROOT`` (``settings.reports_root``) wins
    when both are set.
    """
    legacy = os.getenv("REPORTS_DIR")
    if legacy:
        return Path(legacy)
    return Path(settings.reports_root or "/app/reports")


def job_filename(job_id: uuid.UUID | str, format: str) -> str:
    """Server-generated filename (never taken from the user)."""
    return f"report_{job_id}.{format}"


def job_file_path(job_id: uuid.UUID | str, format: str) -> Path:
    """Final destination of a job artifact (root created on demand)."""
    root = reports_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / job_filename(job_id, format)


def contained_job_path(raw: str | None) -> Path | None:
    """Validate a stored ``file_path``: inside root + frozen filename shape.

    Returns the resolved path, or ``None`` when the value is missing,
    outside the reports root (traversal / tampered DB row) or not a
    ``report_<uuid>.<ext>`` artifact. Downloads must never trust a raw DB
    path without this check.
    """
    if not raw:
        return None
    try:
        root = reports_root().resolve()
        candidate = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if _JOB_FILENAME_RE.fullmatch(candidate.name) is None:
        return None
    return candidate


def sanitize_error_message(exc: BaseException) -> str:
    """Short user-safe error text (no traceback, no secrets, no tokens)."""
    first_line = str(exc).splitlines()[0] if str(exc).strip() else ""
    text = f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__
    text = _SECRET_RE.sub(r"\1=***", text)
    text = " ".join(text.split())  # single line, no tracebacks
    return text[:500] if len(text) > 500 else text


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------- repository / service


def create_job(
    db: Session,
    *,
    format: str,
    filters: dict[str, Any],
    columns: list[str],
    actor_sub: str,
    actor_name: str = "",
    actor_roles: list[str] | None = None,
    effective_university_ids: list[str] | None = None,
    # Dev-3 import extension (000019): kind + worker params + re-POST dedup.
    # Report callers omit them (job_type='report').
    job_type: str = "report",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> ReportJob:
    """Persist a ``queued`` job snapshot and commit (no worker started).

    Callers pass the already-validated request (resolved/deduped columns);
    the worker later rehydrates ONLY this snapshot.
    """
    if format not in ("xlsx", "pdf", "json"):
        raise ValueError(f"unsupported report format: {format!r}")
    now = _utcnow()
    job = ReportJob(
        job_type=job_type,
        payload=dict(payload or {}),
        idempotency_key=idempotency_key,
        format=format,
        filters=dict(filters),
        columns=list(columns),
        actor_sub=actor_sub,
        actor_name=actor_name or "",
        actor_roles=sorted(actor_roles or []),
        effective_university_ids=(
            list(effective_university_ids)
            if effective_university_ids is not None
            else None
        ),
        status=STATUS_QUEUED,
        progress=0,
        created_at=now,
        expires_at=now + timedelta(hours=REPORT_EXPIRY_HOURS),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("report job created id=%s format=%s actor=%s", job.id, format, actor_sub)
    return job


def get_job(db: Session, job_id: str | uuid.UUID) -> ReportJob | None:
    """Load a job by id (invalid UUID text -> ``None``, never 500)."""
    try:
        key = job_id if isinstance(job_id, uuid.UUID) else uuid.UUID(str(job_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return db.get(ReportJob, key)


def job_visible_to(job: ReportJob, user: Any, *, is_admin: bool = False) -> bool:
    """Ownership check: admins see all jobs, others only their own.

    ``is_admin`` is resolved by the caller from the canonical permission
    system (``*`` in ``user_permissions``); non-admin holders of
    ``reports.read`` (managers) see their own jobs only — never widened.
    """
    if is_admin:
        return True
    return bool(job.actor_sub) and job.actor_sub == getattr(user, "id", None)


def list_visible_jobs(
    db: Session, user: Any, *, is_admin: bool = False, limit: int = 100
) -> list[ReportJob]:
    """Jobs visible to ``user`` (newest first, bounded page)."""
    stmt = select(ReportJob).order_by(ReportJob.created_at.desc()).limit(limit)
    if not is_admin:
        stmt = stmt.where(ReportJob.actor_sub == getattr(user, "id", None))
    return list(db.execute(stmt).scalars().all())


def mark_building(db: Session, job: ReportJob) -> bool:
    """Commit ``queued -> building`` BEFORE generation (poll-visible).

    Idempotency guard: ``ready`` jobs are never regenerated and a second
    worker never restarts a ``building`` job without explicit retry
    semantics — both return ``False``.
    """
    db.refresh(job)
    if job.status == STATUS_READY:
        return False
    if job.status == STATUS_BUILDING:
        return False
    if job.status not in (STATUS_QUEUED, STATUS_FAILED):
        return False
    job.status = STATUS_BUILDING
    job.progress = max(int(job.progress or 0), 10)
    if job.started_at is None:
        job.started_at = _utcnow()
    if not job.file_path:
        job.file_path = str(job_file_path(job.id, job.format))
    job.error_message = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return True


def mark_ready(
    db: Session, job: ReportJob, *, file_path: str | Path, file_size: int
) -> ReportJob:
    """Commit ``building -> ready`` AFTER generation (``progress=100``)."""
    job.status = STATUS_READY
    job.progress = 100
    job.file_path = str(file_path)
    job.file_size = int(file_size)
    job.completed_at = _utcnow()
    job.error_message = None
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("report job ready id=%s size=%s", job.id, job.file_size)
    return job


def mark_failed(db: Session, job: ReportJob, exc: BaseException) -> ReportJob:
    """Commit ``-> failed`` with a sanitized message; partial files removed."""
    stored = job.file_path
    job.status = STATUS_FAILED
    job.completed_at = _utcnow()
    job.error_message = sanitize_error_message(exc)
    if stored:
        victim = contained_job_path(stored)
        if victim is not None and victim.is_file():
            try:
                victim.unlink()
            except OSError:
                logger.warning("report job cleanup failed id=%s", job.id)
        job.file_path = None
        job.file_size = None
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.warning("report job failed id=%s error=%s", job.id, job.error_message)
    return job


# ------------------------------------------------------- expiry / cleanup


def cleanup_expired_report_jobs(db: Session) -> dict[str, int]:
    """Delete artifacts of jobs with ``expires_at < now`` (24h window).

    * ``ready`` jobs: file removed (root-contained only, never foreign paths),
      ``file_path``/``file_size`` cleared, status preserved (downloads stay
      denied via the ``expires_at`` check returning ``410 Gone``);
    * ``queued``/``building`` jobs past expiry: failed closed
      (``mark_failed`` with an expiry error);
    * ``failed`` jobs: metadata kept for audit, files (if any) removed.

    Returns ``{"files_removed": N, "jobs_failed": M, "jobs_cleared": K}``.
    Pure callable over the given session — scheduling (cron/CLI) lives in
    :func:`run_cleanup_once` and the deployment docs.
    """
    now = _utcnow()
    stmt = select(ReportJob).where(ReportJob.expires_at < now)
    expired = list(db.execute(stmt).scalars().all())
    files_removed = 0
    jobs_failed = 0
    jobs_cleared = 0
    for job in expired:
        victim = contained_job_path(job.file_path)
        if victim is not None and victim.is_file():
            try:
                victim.unlink()
                files_removed += 1
            except OSError:
                logger.warning("report expiry unlink failed id=%s", job.id)
        if job.status in (STATUS_QUEUED, STATUS_BUILDING):
            job.status = STATUS_FAILED
            job.completed_at = now
            job.error_message = "Report expired before completion"
            job.file_path = None
            job.file_size = None
            db.add(job)
            jobs_failed += 1
        elif job.status == STATUS_READY:
            if job.file_path is not None or job.file_size is not None:
                job.file_path = None
                job.file_size = None
                db.add(job)
                jobs_cleared += 1
    if expired:
        db.commit()
    return {
        "files_removed": files_removed,
        "jobs_failed": jobs_failed,
        "jobs_cleared": jobs_cleared,
    }


def run_cleanup_once() -> dict[str, int]:
    """Deployment entry point (daily cron/CLI): fresh session + cleanup.

    Opens its own canonical session (never a request-scoped one) so it can
    run from ``python -m`` / cron without HTTP::

        python -c "from app.modules.analytics.report_jobs import
            run_cleanup_once; print(run_cleanup_once())"
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return cleanup_expired_report_jobs(db)
    finally:
        db.close()
