"""P4-03-01 / P4-06-01 ``/api/v1/reports`` router (production, mounted).

Contract (frozen)::

    POST /api/v1/reports              -> 202 {"job_id": "uuid", "status": "queued"}
    GET  /api/v1/reports/{job_id}     -> 200 ReportJobRead (no filesystem path)
    GET  /api/v1/reports/{job_id}/download -> 200 file (ready + fresh + allowed)

RBAC uses the frozen ``reports.read`` permission (``401`` without token,
``403`` without the permission, ``202``/``200`` when allowed). It gates
creation AND reads — access is never widened here. Within allowed users
admins (``*``) see all jobs; everyone else sees only their own jobs
(foreign ids -> ``403``, unknown/malformed ids -> ``404``), mirroring the
workflow ``Forbidden: other university`` convention.

All three frozen formats (``xlsx`` / ``pdf`` / ``json``) share one
creation path; unknown formats are rejected with ``422`` by the
``ReportFormat`` enum before any persistence.

Ordering in ``POST``: validate -> persist -> commit -> schedule the
background worker -> return the persisted id. A persistence failure
raises before any worker is ever started, so no fake job id can leak.

Download errors are controlled (never 500): ``409`` while the job is not
``ready`` (project state-conflict convention), ``410 Gone`` once
``expires_at`` passed or the artifact is gone, ``403``/``404`` for
visibility. Stored paths are containment-checked against the reports
root (traversal-safe); filenames stay server-generated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.core.permissions import require_permission, user_permissions
from app.core.security import CurrentUser
from app.core.errors import BusinessException, SecurityError
from app.schemas.errors import ErrorCode
from app.modules.audit.service import get_audit_db
from app.models.report_job import JOB_TYPE_REPORT, ReportJob
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import (
    REPORTS_READ_PERMISSION,
    ReportQueuedResponse,
    create_report_job,
)
from app.schemas.common import ErrorResponse, PaginatedResponse, ReportFormat

__all__ = ["ReportJobRead", "router"]

router = APIRouter(prefix="/reports", tags=["Reports"])

ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
    403: {"model": ErrorResponse, "description": "FORBIDDEN"},
    404: {"model": ErrorResponse, "description": "Job not found"},
    400: {"model": ErrorResponse, "description": "REPORT_NOT_READY — отчёт ещё формируется"},
    410: {"model": ErrorResponse, "description": "Gone: report expired or file removed"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации ReportRequest"},
}

#: The router accepts exactly the three frozen export formats.
SUPPORTED_FORMATS: frozenset[ReportFormat] = frozenset(
    {ReportFormat.XLSX, ReportFormat.PDF, ReportFormat.JSON}
)

DOWNLOAD_MEDIA_TYPES: dict[str, str] = {
    ReportFormat.XLSX.value: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    ReportFormat.PDF.value: "application/pdf",
    ReportFormat.JSON.value: "application/json",
}


class ReportJobRead(BaseModel):
    """Status view of a report job (never exposes the filesystem path)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID = Field(description="Persistent ReportJob id.")
    format: ReportFormat = Field(description="Report output format.")
    status: str = Field(description="queued | building | ready | failed.")
    progress: int = Field(description="0..100 (queued=0, building=10, ready=100).")
    file_size: int | None = Field(default=None, description="Artifact bytes (ready).")
    created_at: datetime = Field(description="Creation time (tz-aware).")
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    expires_at: datetime = Field(description="Download deadline (created + 24h).")
    error_message: str | None = Field(default=None, description="Sanitized failure.")


def _is_admin(user: CurrentUser) -> bool:
    return "*" in user_permissions(user)


def _get_visible_job(db: Session, job_id: str, user: CurrentUser) -> ReportJob:
    job = jobs.get_job(db, job_id)
    if job is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    if not jobs.job_visible_to(job, user, is_admin=_is_admin(user)):
        raise SecurityError(ErrorCode.FORBIDDEN)
    return job


def _read_model(job: ReportJob) -> ReportJobRead:
    return ReportJobRead(
        id=job.id,
        format=ReportFormat(job.format),
        status=job.status,
        progress=int(job.progress or 0),
        file_size=job.file_size,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        error_message=job.error_message,
    )


@router.post(
    "",
    response_model=ReportQueuedResponse,
    status_code=202,
    summary="Создать отчёт (async, xlsx/pdf/json)",
    description=(
        "Валидирует ReportRequest (format+filters+columns), сохраняет ReportJob "
        "со статусом queued и возвращает реальный persisted job_id. "
        "Исполнением владеет отдельный worker-контейнер "
        "(python -m app.modules.analytics.report_worker); API только создаёт "
        "jobs — BackgroundTasks запрещены ТЗ P4-06-01."
    ),
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403],
               422: ERROR_RESPONSES[422]},
)
def create_report(
    request: ReportRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("reports.create")),
) -> ReportQueuedResponse:
    if request.format not in SUPPORTED_FORMATS:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    try:
        queued = create_report_job(db, request, user)
    except ValueError as exc:
        raise BusinessException(ErrorCode.VALIDATION_ERROR) from exc
    return queued


@router.get(
    "",
    response_model=PaginatedResponse[ReportJobRead],
    summary="Список задач отчётов",
)
def list_report_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission(REPORTS_READ_PERMISSION)),
) -> PaginatedResponse[ReportJobRead]:
    stmt = select(ReportJob).where(ReportJob.job_type == JOB_TYPE_REPORT)
    if not _is_admin(user) and "manager" not in (user.roles or set()):
        stmt = stmt.where(ReportJob.actor_sub == (user.id or ""))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ReportJob.created_at.desc(), ReportJob.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    return PaginatedResponse(
        items=[_read_model(job) for job in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/{job_id}",
    response_model=ReportJobRead,
    summary="Статус отчёта",
    description="Статус/progress/сроки job (без внутреннего пути к файлу).",
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403],
               404: ERROR_RESPONSES[404]},
)
def get_report_job(
    job_id: str,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission(REPORTS_READ_PERMISSION)),
) -> ReportJobRead:
    return _read_model(_get_visible_job(db, job_id, user))


@router.get(
    "/{job_id}/download",
    summary="Скачать готовый отчёт",
    description=(
        "Отдаёт файл только при status=ready, свежем expires_at, "
        "существующем файле внутри reports root и доступе к job."
    ),
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403],
               404: ERROR_RESPONSES[404], 400: ERROR_RESPONSES[400],
               410: ERROR_RESPONSES[410]},
)
def download_report_job(
    job_id: str,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission(REPORTS_READ_PERMISSION)),
) -> FileResponse:
    job = _get_visible_job(db, job_id, user)
    now = datetime.now(timezone.utc)
    if job.expires_at is not None and now >= job.expires_at:
        raise BusinessException(ErrorCode.GONE)
    if job.status != jobs.STATUS_READY:
        raise BusinessException(ErrorCode.REPORT_NOT_READY)
    path = jobs.contained_job_path(job.file_path)
    if path is None or not path.is_file():
        raise BusinessException(ErrorCode.FILE_NOT_FOUND)
    filename = f"report_{job.id}.{job.format}"
    return FileResponse(
        path,
        media_type=DOWNLOAD_MEDIA_TYPES.get(job.format, "application/octet-stream"),
        filename=filename,
    )
