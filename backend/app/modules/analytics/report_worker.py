"""P4-06-01 background report execution (dedicated worker container).

The worker loop (:func:`run_worker_once` / :func:`main`, command
``python -m app.modules.analytics.report_worker`` in the ``worker``
compose service)
owns execution: it atomically claims the oldest queued job
(``SELECT ... FOR UPDATE SKIP LOCKED`` on PostgreSQL) and runs it to
``ready``; a failed attempt with attempts left is requeued (max 3
attempts per the spec), otherwise the job goes ``failed``. The API only
creates jobs (``202``) and never executes them — ``BackgroundTasks`` are
banned for reports by the spec (they die with the API process,
block the loop and have no retries).

:meth:`generate_report_task` stays callable standalone (tests, one-off
retries): it claims the job itself first. Every entry receives ONLY
``job_id`` — never a request-scoped DB session — and opens a FRESH
session via the canonical ``SessionLocal`` factory. The worker rehydrates
the persisted snapshot (``UnifiedFilter`` + resolved columns + the saved
actor security context) and dispatches the already-existing
:func:`generate_report_file` (xlsx/pdf/json), or the single-sheet import
pipeline for ``xlsx_import`` jobs. It never re-reads the client request and never
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
    "run_audit_relay_once",
    "run_import_job",
    "run_worker_once",
]


def run_audit_relay_once() -> int:
    """Deliver pending workflow audit intents using a separate transaction."""
    from app.db.session import SessionLocal
    from app.modules.audit.relay import relay_audit_events

    db = SessionLocal()
    try:
        return relay_audit_events(db)
    finally:
        db.close()


def run_notification_scan_once() -> int:
    """Project due dates into the same durable in-app inbox."""
    from app.db.session import SessionLocal
    from app.modules.notifications.service import scan_due_notifications

    db = SessionLocal()
    try:
        return scan_due_notifications(db)
    finally:
        db.close()


def run_email_delivery_once() -> bool:
    """Deliver one due notification through the existing worker process."""
    from app.db.session import SessionLocal
    from app.modules.notifications.email import run_email_delivery_once as deliver

    with SessionLocal() as db:
        return deliver(db)


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
    """Execute a claimed ``xlsx_import`` job (single sheet or a pack).

    Same steps as ``POST /import/execute`` after the claim: run
    ``execute_sheet``/``execute_sheets`` over the stored file_id/sheet(s)
    and options, write the XLSX error report to the job artifact path,
    store the summary in ``result``. On failure the attempt is requeued
    (attempts left) or the job goes failed — never half-committed.
    """
    from app.modules.imports import service as import_service

    payload = job.payload or {}
    try:
        if payload.get("sheets"):
            summary = import_service.execute_sheets(
                db,
                payload["file_id"],
                list(payload["sheets"]),
                dry_run=payload.get("dry_run", False),
                update_existing=payload.get("update_existing", True),
            )
        else:
            summary = import_service.execute_sheet(
                db,
                payload["file_id"],
                payload["sheet"],
                dry_run=payload.get("dry_run", False),
                update_existing=payload.get("update_existing", True),
            )
    except Exception as exc:
        # Import files may contain personal data and database exceptions may
        # include cell values. Keep the public job error deliberately generic.
        logger.error("import worker failed id=%s type=%s", job.id, type(exc).__name__)
        outcome = jobs.requeue_or_fail(
            db, job, RuntimeError("Не удалось обработать импорт; проверьте файл и лист"),
        )
        if outcome == "failed":
            from app.modules.notifications.service import notify_import_result

            notify_import_result(db, job, failed=True)
            db.commit()
        return outcome
    artifact = Path(jobs.job_file_path(job.id, "xlsx"))
    size = import_service.write_error_report(summary, artifact)
    job.result = summary
    db.add(job)
    from app.modules.notifications.service import notify_import_result

    notify_import_result(db, job)
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
    # Columns=None means "all mandatory" (never [] which would 422-loop).
    stored_columns = list(job.columns or [])
    request = ReportRequest(
        format=ReportFormat(job.format),
        filters=filters,
        columns=stored_columns or None,
    )
    output = Path(job.file_path) if job.file_path else jobs.job_file_path(
        job.id, job.format
    )
    # Cache hit (ТЗ §7): an identical fresh ready job of the same actor —
    # copy its artifact instead of regenerating.
    try:
        reusable = jobs.find_ready_reusable(
            db,
            format=job.format,
            filters=UnifiedFilter.model_validate(job.filters or {}).model_dump(mode="json"),
            columns=request.resolved_columns,
            actor_sub=job.actor_sub or "",
            exclude_id=job.id,
        )
    except Exception:
        reusable = None
    if reusable is not None:
        import shutil

        try:
            source = jobs.contained_job_path(reusable.file_path)
            assert source is not None and source.is_file()
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            job.result = {"cache_version": jobs.REPORT_CACHE_VERSION}
            jobs.mark_ready(
                db, job, file_path=output, file_size=output.stat().st_size
            )
            return "ready"
        except Exception:
            logger.warning("report worker cache copy failed id=%s", job.id)
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
    job.result = {"cache_version": jobs.REPORT_CACHE_VERSION}
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
    next_notification_scan = 0.0
    while True:
        try:
            run_audit_relay_once()
        except Exception:
            logger.exception("audit outbox relay iteration failed")
        if time.monotonic() >= next_notification_scan:
            try:
                run_notification_scan_once()
                next_notification_scan = time.monotonic() + 3600
            except Exception:
                logger.exception("notification deadline scan failed")
                next_notification_scan = time.monotonic() + 60
        try:
            run_email_delivery_once()
        except Exception:
            logger.exception("email delivery iteration failed")
        try:
            # Only report/import job execution here. The daily health-score
            # snapshot that used to run in this block was removed together
            # with the health_score entity (migration 000029); its import
            # raised ModuleNotFoundError and, because it sat in front of
            # run_worker_once(), it silently skipped a whole iteration of
            # report processing.
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
