"""P4-06-01 background report execution (FastAPI ``BackgroundTasks``).

The task receives ONLY ``job_id`` — never a request-scoped DB session —
and opens a FRESH session via the canonical ``SessionLocal`` factory.
The worker rehydrates the persisted snapshot (``UnifiedFilter`` +
resolved columns + the saved actor security context) and dispatches the
already-existing :func:`generate_report_file` (xlsx/pdf/json). It never
re-reads the client request and never runs as admin/global unless the
job snapshot itself carries an explicit global (admin) scope.

Lifecycle commits (poll-visible)::

    queued -> building (committed BEFORE generation)
           -> ready / failed (committed AFTER generation)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.core.security import KNOWN_ROLES, CurrentUser
from app.models.report_job import STATUS_BUILDING, STATUS_READY, ReportJob
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import generate_report_file
from app.schemas.common import ReportFormat

logger = logging.getLogger("rtk")

__all__ = ["build_worker_user", "generate_report_task"]


def build_worker_user(job: ReportJob) -> CurrentUser:
    """Rehydrate the minimal actor the dataset layer expects.

    Security-critical: the scope comes ONLY from the persisted snapshot.
    ``None`` (explicit global/admin snapshot) keeps global behaviour;
    ``[]`` fails closed to zero rows via the shared applicator. Never
    ``user=None`` (which would silently widen a scoped job to global).
    """
    scope = job.effective_university_ids
    return CurrentUser(
        id=job.actor_sub or "",
        username=None,
        email=None,
        name=job.actor_name or None,
        roles=set(job.actor_roles or []) & KNOWN_ROLES,
        university_ids=tuple(str(v) for v in scope) if scope is not None else None,
    )


def _worker_roles(user: CurrentUser) -> list[str]:
    return sorted(user.roles or [])


def generate_report_task(job_id: str | uuid.UUID) -> str:
    """Background entry point: build one persisted job to ``ready|failed``.

    Returns the terminal status (``"ready"`` / ``"failed"``) or the
    idempotency guard outcome (``"already-ready"`` / ``"already-building"``
    / ``"unknown-job"``). Tracebacks go to the logs only; the stored
    ``error_message`` is always sanitized.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = jobs.get_job(db, job_id)
        if job is None:
            logger.warning("report worker: unknown job %s", job_id)
            return "unknown-job"
        if job.status == STATUS_READY:
            return "already-ready"
        if job.status == STATUS_BUILDING:
            return "already-building"
        if not jobs.mark_building(db, job):
            return "already-building"

        worker_user = build_worker_user(job)
        if not worker_user.id:
            raise ValueError("report job has no actor snapshot")
        scoped_roles = _worker_roles(worker_user)
        if not scoped_roles and (job.actor_roles or []):
            # Stored roles unknown to this deployment: fail closed rather
            # than silently upgrading/downgrading the data scope.
            raise ValueError("report job actor roles are not recognized")

        filters = UnifiedFilter.model_validate(job.filters or {})
        request = ReportRequest(
            format=ReportFormat(job.format),
            filters=filters,
            columns=list(job.columns or []),
        )
        output = Path(job.file_path) if job.file_path else jobs.job_file_path(
            job.id, job.format
        )
        try:
            generated = generate_report_file(
                db, request, output, user=worker_user, generated_at=None
            )
        except Exception as exc:
            try:
                victim = jobs.contained_job_path(str(output))
                if victim is not None and victim.is_file():
                    victim.unlink()
            except OSError:
                pass
            jobs.mark_failed(db, job, exc)
            logger.exception("report worker failed id=%s", job.id)
            return "failed"
        jobs.mark_ready(db, job, file_path=generated.path, file_size=generated.size_bytes)
        return "ready"
    finally:
        db.close()
