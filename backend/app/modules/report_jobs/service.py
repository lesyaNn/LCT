"""Durable job lifecycle. Worker threads NEVER share request DB sessions.

Dev-1 plugs in a renderer, Dev-3 can reuse submit/read/download with the same
contract. Import parsing and report content generation are deliberately absent.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.db.session import SessionLocal
from app.models.report_job import ReportJob
from app.modules.analytics.integration import (
    FilterProvider,
    Selection,
    data_scope,
    get_filter_provider,
    load_object,
    restrict_selection,
)
from app.modules.report_jobs.schemas import JobRead, ReportRequest

logger = logging.getLogger(__name__)
MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "json": "application/json",
}


class Renderer(Protocol):
    def validate(self, request: ReportRequest) -> None:
        """Check supported format/columns BEFORE a job is persisted."""
        ...

    def render(
        self, db: Session, request: ReportRequest, selection: Selection, destination: Path
    ) -> None:
        """Write the Dev-1 export to destination; obey authorized selection."""
        ...


def get_renderer() -> Renderer:
    renderer = load_object("P4_REPORT_RENDERER")
    if renderer is None:
        raise HTTPException(
            503,
            {
                "code": "REPORT_RENDERER_NOT_CONFIGURED",
                "message": "Connect Dev-1 exporters via P4_REPORT_RENDERER",
            },
        )
    return renderer


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def storage_root() -> Path:
    root = Path(os.getenv("P4_REPORT_DIRECTORY", "var/reports")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_path(job: ReportJob, *, temporary: bool = False) -> Path:
    if job.format not in MEDIA_TYPES:
        raise ValueError("Invalid stored format")
    root = storage_root()
    path = root / f"{UUID(str(job.id))}.{job.format}{'.part' if temporary else ''}"
    # Reject symlinks instead of following them for write/download/cleanup.
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("Unsafe report artifact path")
    return path


def submit(
    db: Session,
    request: ReportRequest,
    user: CurrentUser,
    provider: FilterProvider,
    renderer: Renderer,
) -> ReportJob:
    allowed = data_scope(user)
    try:
        filters = provider.normalize(request.filters)
    except ValidationError:
        raise HTTPException(422, "Invalid UnifiedFilter") from None
    validated = request.model_copy(update={"filters": filters})
    renderer.validate(validated)
    now = utcnow()
    job = ReportJob(
        id=uuid4(),
        user_id=user.id,
        user_name=user.name or user.username or user.id,
        university_id=allowed[0] if allowed and len(allowed) == 1 else None,
        scope_ids=None if allowed is None else [str(value) for value in allowed],
        format=request.format,
        filters=filters,
        columns=request.columns,
        status="queued",
        progress=0,
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID, user: CurrentUser) -> ReportJob:
    allowed = data_scope(user)
    job = db.get(ReportJob, job_id)
    # 404 hides existence of someone else's job. Check scope even for owner:
    # a user's scope may have narrowed since job creation.
    privileged = bool(user.roles.intersection({"admin", "manager"}))
    if job is None or (job.user_id != user.id and not privileged):
        raise HTTPException(404, "Report job not found")
    if allowed is not None and (
        job.scope_ids is None or not set(job.scope_ids).issubset({str(x) for x in allowed})
    ):
        raise HTTPException(404, "Report job not found")
    if aware(job.expires_at) <= utcnow():
        raise HTTPException(410, "Report job expired")
    return job


def describe(job: ReportJob) -> JobRead:
    return JobRead(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        file_size=job.file_size,
        error_message=job.error_message,
        download_url=f"/api/v1/reports/{job.id}/download" if job.status == "ready" else None,
    )


def downloadable(job: ReportJob) -> Path:
    if job.status != "ready":
        raise HTTPException(409, "Report is not ready")
    try:
        path = artifact_path(job)
    except ValueError:
        raise HTTPException(410, "Report artifact unavailable") from None
    if not path.is_file() or path.stat().st_size != job.file_size:
        raise HTTPException(410, "Report artifact unavailable")
    return path


def run_job(
    job_id: UUID,
    *,
    session_factory=SessionLocal,
    provider: FilterProvider | None = None,
    renderer: Renderer | None = None,
) -> bool:
    """Atomic claim makes duplicate deliveries harmless across API/workers."""
    with session_factory() as db:
        now = utcnow()
        claimed = db.execute(
            update(ReportJob)
            .where(
                ReportJob.id == job_id,
                ReportJob.status == "queued",
                ReportJob.expires_at > now,
            )
            .values(status="building", progress=5, started_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:
            return False
        job = db.get(ReportJob, job_id)
        try:
            provider = provider or get_filter_provider()
            renderer = renderer or get_renderer()
            request = ReportRequest(format=job.format, filters=job.filters, columns=job.columns)
            filters = provider.normalize(request.filters)
            request = request.model_copy(update={"filters": filters})
            scope = None if job.scope_ids is None else tuple(UUID(x) for x in job.scope_ids)
            selection = restrict_selection(provider.select(db, filters), scope)
            temporary = artifact_path(job, temporary=True)
            destination = artifact_path(job)
            renderer.render(db, request, selection, temporary)
            # Revalidate after renderer: never serve a replaced symlink.
            temporary = artifact_path(job, temporary=True)
            size = temporary.stat().st_size
            if size <= 0:
                raise ValueError("Empty report")
            # End the renderer's read transaction, then lock/refetch current job
            # state. A timeout/cleanup may already have failed it in another worker.
            db.rollback()
            job = db.scalar(
                select(ReportJob)
                .where(ReportJob.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if job.status != "building":
                temporary.unlink(missing_ok=True)
                return False
            if aware(job.expires_at) <= utcnow():
                raise ValueError("Report expired while building")
            temporary.replace(destination)
            job.file_path = str(destination)
            job.file_size = size
            job.status = "ready"
            job.progress = 100
            job.completed_at = utcnow()
            # Downloads available for a full 24h after completion.
            job.expires_at = job.completed_at + timedelta(hours=24)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Report build failed: %s", job_id)
            db.execute(
                update(ReportJob)
                .where(
                    ReportJob.id == job_id,
                    ReportJob.status == "building",
                )
                .values(
                    status="failed",
                    completed_at=utcnow(),
                    error_message="Report generation failed. Retry or contact an administrator.",
                )
            )
            db.commit()
            job = db.get(ReportJob, job_id)
            for temporary in (True, False):
                try:
                    artifact_path(job, temporary=temporary).unlink(missing_ok=True)
                except (OSError, ValueError):
                    logger.warning("Cannot clean report artifact for %s", job_id)
    return True


def cleanup_expired(*, session_factory=SessionLocal) -> int:
    """Daily worker maintenance. Delete only exact UUID artifacts, keep job history."""
    count = 0
    with session_factory() as db:
        for job in db.scalars(
            select(ReportJob)
            .where(ReportJob.expires_at <= utcnow())
            .with_for_update(skip_locked=True)
        ):
            for temporary in (True, False):
                try:
                    artifact_path(job, temporary=temporary).unlink(missing_ok=True)
                except (OSError, ValueError):
                    logger.warning("Cannot clean expired report %s", job.id)
            job.file_path = None
            job.file_size = None
            if job.status in {"queued", "building"}:
                job.status = "failed"
                job.error_message = "Report job expired. Submit a new request."
                job.completed_at = utcnow()
            count += 1
        db.commit()
    return count
