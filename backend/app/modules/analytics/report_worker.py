"""P4-06-01 background report execution (dedicated worker container).

The worker loop (:func:`run_worker_once` / :func:`main`, command
``python -m app.modules.analytics.report_worker`` in the ``worker``
compose service)
owns execution: it atomically claims the oldest queued job
(``SELECT ... FOR UPDATE SKIP LOCKED`` on PostgreSQL) and runs it to
``ready``; a failed attempt with attempts left is requeued (max 3
attempts per the spec), otherwise the job goes ``failed``. The API only
creates jobs (``202``) and never executes them — ``BackgroundTasks`` are
banned for reports/imports by the spec (they die with the API process,
block the loop and have no retries).

:meth:`generate_report_task` stays callable standalone (tests, one-off
retries): it claims the job itself first. Every entry receives ONLY
``job_id`` — never a request-scoped DB session — and opens a FRESH
session via the canonical ``SessionLocal`` factory. The worker rehydrates
the persisted snapshot (``UnifiedFilter`` + resolved columns + the saved
actor security context) and dispatches the already-existing
:func:`generate_report_file` (xlsx/pdf/json), or the XLSX import pipeline
for ``xlsx_import`` jobs. It never re-reads the client request and never
runs as admin/global unless the job snapshot itself carries an explicit
global (admin) scope.

Lifecycle commits (poll-visible)::

    queued -> building (committed BEFORE generation)
            -> ready / failed (committed AFTER generation)
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.security import KNOWN_ROLES, CurrentUser
from app.models.report_job import (
    JOB_TYPE_REPORT,
    JOB_TYPE_XLSX_IMPORT,
    STATUS_BUILDING,
    STATUS_READY,
    ReportJob,
)
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import generate_report_file
from app.schemas.common import ReportFormat

logger = logging.getLogger("rtk")

__all__ = [
    "build_worker_user",
    "generate_report_task",
    "main",
    "run_import_job",
    "run_worker_once",
]


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
    """Standalone entry point: claim + build one job to a terminal state.

    Returns ``"ready"`` / ``"requeued"`` / ``"failed"`` or the idempotency
    guard outcome (``"already-ready"`` / ``"already-building"`` /
    ``"unknown-job"``). Tracebacks go to the logs only; the stored
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
        claimed = jobs.claim_job(db, job.id)
        if claimed is None:
            return "already-building"
        return _run_claimed_job(db, claimed)
    finally:
        db.close()


def run_import_job(db: Session, job: ReportJob) -> str:
    """Execute a claimed ``xlsx_import`` job (Dev-3 payload).

    Same steps as ``POST /import/execute`` after the claim: run
    ``execute_import`` over the stored file_id/mapping/options, write the
    XLSX error report to the job artifact path, store the summary in
    ``result``. On failure the attempt is requeued (attempts left) or the
    job goes failed — never half-committed.
    """
    from app.modules.imports import service as import_service

    payload = job.payload or {}
    try:
        summary = import_service.execute_import(
            db,
            payload["file_id"],
            payload.get("mapping", {}),
            update_existing=payload.get("update_existing", True),
            dry_run=payload.get("dry_run", False),
        )
    except Exception as exc:
        return jobs.requeue_or_fail(db, job, exc)
    artifact = job.file_path or str(jobs.job_file_path(job.id, "xlsx"))
    size = import_service.write_error_report(summary, artifact)
    job.result = summary
    db.add(job)
    jobs.mark_ready(db, job, file_path=artifact, file_size=size)
    return "ready"


def _run_claimed_job(db: Session, job: ReportJob) -> str:
    """Dispatch a job that this worker already claimed (building)."""
    if job.job_type == JOB_TYPE_XLSX_IMPORT:
        return run_import_job(db, job)

    worker_user = build_worker_user(job)
    if not worker_user.id:
        return jobs.requeue_or_fail(db, job, ValueError("report job has no actor snapshot"))
    scoped_roles = _worker_roles(worker_user)
    if not scoped_roles and (job.actor_roles or []):
        # Stored roles unknown to this deployment: fail closed rather
        # than silently upgrading/downgrading the data scope.
        return jobs.requeue_or_fail(
            db, job, ValueError("report job actor roles are not recognized")
        )

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
        outcome = jobs.requeue_or_fail(db, job, exc)
        logger.exception("report worker failed id=%s", job.id)
        return outcome
    jobs.mark_ready(db, job, file_path=generated.path, file_size=generated.size_bytes)
    return "ready"


def run_worker_once() -> str | None:
    """Claim the oldest queued job (any supported type) and run it.

    Returns the terminal outcome (``"ready"`` / ``"requeued"`` /
    ``"failed"``) or ``None`` when the queue is empty. One iteration only —
    the container loops over this. Unsupported ``job_type`` rows are marked
    failed (loudly, never silently skipped).
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = jobs.claim_next_job(db)
        if job is None:
            return None
        if job.job_type not in (JOB_TYPE_REPORT, JOB_TYPE_XLSX_IMPORT):
            jobs.mark_failed(db, job, ValueError(f"unsupported job_type: {job.job_type!r}"))
            return "failed"
        return _run_claimed_job(db, job)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    """Worker container entry point.

    ``python -m app.modules.analytics.report_worker [--once]``.
    ``--once`` drains a single job (cron/CI); otherwise loops with a short
    idle sleep. Shares the backend image; needs ``DATABASE_URL``,
    ``REPORTS_ROOT`` and the import staging volume.
    """
    parser = argparse.ArgumentParser(description="P4-06-01 report/import worker")
    parser.add_argument("--once", action="store_true", help="handle one job and exit")
    parser.add_argument(
        "--idle-sleep", type=float, default=2.0, help="idle sleep seconds"
    )
    args = parser.parse_args(argv)
    last_daily_day = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.hour == 0 and now.minute < 5 and last_daily_day != now.date():
                from app.db.session import SessionLocal
                from app.modules.health_score.materialization import run_daily_snapshot_once
                snapshot_db = SessionLocal()
                try:
                    run_daily_snapshot_once(snapshot_db, day=now.date())
                finally:
                    snapshot_db.close()
                last_daily_day = now.date()
            outcome = run_worker_once()
        except Exception:
            logger.exception("report worker iteration failed")
            outcome = "failed"
        if args.once:
            return 0
        time.sleep(0 if outcome else args.idle_sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
