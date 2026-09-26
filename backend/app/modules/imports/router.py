"""``/api/v1/import`` router (production, mounted): file upload + one-sheet import.

Contract (frozen for the frontend)::

    POST /api/v1/import/upload          -> 201 {file_id, filename, sheets[]}
    POST /api/v1/import/sheets/preview -> 200 {file_id, sheet, headers, preview, row_count}
    POST /api/v1/import/execute        -> 202 {job_id} (async xlsx_import job)
    GET  /api/v1/import/jobs           -> 200 [ImportJobRead] (import jobs only)
    GET  /api/v1/import/jobs/{job_id}  -> 200 ImportJobRead (no filesystem path)
    GET  /api/v1/import/jobs/{job_id}/report -> 200 errors-only xlsx (or 404/409/410)

RBAC: ``import.write`` gates upload + execute, ``import.read`` gates
preview + journal. Execution owns the worker container
(``python -m app.modules.analytics.report_worker``); the API only stages
files and creates jobs — BackgroundTasks are banned.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, SecurityError
from app.core.permissions import require_permission, user_permissions
from app.core.security import CurrentUser
from app.models.report_job import JOB_TYPE_XLSX_IMPORT, ReportJob
from app.modules.analytics import report_jobs as jobs
from app.modules.audit.service import get_audit_db
from app.modules.imports import service
from app.modules.imports.schemas import (
    ImportExecuteRequest,
    ImportExecuteResponse,
    ImportJobRead,
    ImportSheetInfo,
    ImportSheetPreview,
    ImportSummary,
    ImportUploadResponse,
    SheetPreviewRequest,
)
from app.schemas.common import ErrorResponse
from app.schemas.errors import ErrorCode

__all__ = ["router"]

router = APIRouter(prefix="/import", tags=["Import"])

ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
    403: {"model": ErrorResponse, "description": "FORBIDDEN"},
    404: {"model": ErrorResponse, "description": "Job/file not found"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации"},
}

_ERROR_CODES = {code.value for code in ErrorCode}


def _service_error(exc: service.ImportValidationError) -> BusinessException:
    code = ErrorCode(exc.code) if exc.code in _ERROR_CODES else ErrorCode.VALIDATION_ERROR
    return BusinessException(code, message=str(exc) or None)


def _is_admin(user: CurrentUser) -> bool:
    return "*" in user_permissions(user)


def _get_visible_job(db: Session, job_id: str, user: CurrentUser) -> ReportJob:
    job = jobs.get_job(db, job_id)
    if job is None or job.job_type != JOB_TYPE_XLSX_IMPORT:
        raise BusinessException(ErrorCode.NOT_FOUND)
    if not jobs.job_visible_to(job, user, is_admin=_is_admin(user)):
        raise SecurityError(ErrorCode.FORBIDDEN)
    return job


def _read_model(job: ReportJob) -> ImportJobRead:
    payload = job.payload or {}
    result = ImportSummary(**job.result) if isinstance(job.result, dict) else None
    has_errors = bool(result and result.errors_total > 0)
    return ImportJobRead(
        id=job.id,
        type=JOB_TYPE_XLSX_IMPORT,
        status=job.status,
        progress=int(job.progress or 0),
        dry_run=bool(payload.get("dry_run", False)),
        created_at=job.created_at,
        created_by=job.actor_name or job.actor_sub,
        filename=payload.get("filename"),
        sheet=payload.get("sheet"),
        result=result,
        error=job.error_message,
        error_report_url=f"/api/v1/import/jobs/{job.id}/report" if has_errors else None,
    )


@router.post(
    "/upload",
    response_model=ImportUploadResponse,
    status_code=201,
    summary="Загрузить XLSX и прочитать листы",
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403], 422: ERROR_RESPONSES[422]},
)
def upload_file(
    file: UploadFile,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.write")),
) -> ImportUploadResponse:
    _ = db  # audit context for the staging side-effect; no DB writes here.
    _ = user
    try:
        content = file.file.read()
    except Exception as exc:
        raise BusinessException(ErrorCode.IMPORT_FAILED) from exc
    try:
        file_id = service.stage_upload(file.filename or "", content)
        sheets = service.list_sheets(file_id)
    except service.ImportValidationError as exc:
        raise _service_error(exc) from exc
    return ImportUploadResponse(
        file_id=file_id,
        filename=file.filename or "",
        sheets=[ImportSheetInfo(**item) for item in sheets],
    )


@router.post(
    "/sheets/preview",
    response_model=ImportSheetPreview,
    summary="Предпросмотр одного листа",
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403], 404: ERROR_RESPONSES[404]},
)
def preview_sheet(
    request: SheetPreviewRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.read")),
) -> ImportSheetPreview:
    _ = db
    _ = user
    try:
        data = service.preview_sheet(request.file_id, request.sheet)
    except service.ImportValidationError as exc:
        raise _service_error(exc) from exc
    return ImportSheetPreview(**data)


@router.post(
    "/execute",
    response_model=ImportExecuteResponse,
    status_code=202,
    summary="Запустить импорт листа (async)",
    description=(
        "Сохраняет ``xlsx_import``-задачу со статусом queued и возвращает "
        "job_id. Один ``sheet`` — импорт листа, ``sheets`` — пачка листов "
        "в каноническом порядке одной транзакцией (dry-run пачки видит "
        "межлистовые зависимости). Исполнением владеет worker-контейнер; "
        "API только создаёт jobs — BackgroundTasks запрещены."
    ),
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403], 422: ERROR_RESPONSES[422]},
)
def execute_import(
    request: ImportExecuteRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.write")),
) -> ImportExecuteResponse:
    sheets = [s for s in (request.sheets or []) if s and s.strip()]
    if sheets:
        for sheet in sheets:
            try:
                service.resolve_sheet_kind(sheet)
            except service.ImportValidationError as exc:
                raise _service_error(exc) from exc
        payload = {"sheets": sheets, "sheet": "Все листы"}
        columns = list(sheets)
    else:
        if not request.sheet:
            raise BusinessException(ErrorCode.VALIDATION_ERROR)
        try:
            service.resolve_sheet_kind(request.sheet)
            service._staged_path(request.file_id)
        except service.ImportValidationError as exc:
            raise _service_error(exc) from exc
        payload = {"sheet": request.sheet}
        columns = [request.sheet]
    try:
        service._staged_path(request.file_id)
    except service.ImportValidationError as exc:
        raise _service_error(exc) from exc
    try:
        job = jobs.create_job(
            db,
            format="xlsx",
            filters={},
            columns=columns,
            actor_sub=user.id or "",
            actor_name=getattr(user, "name", "") or "",
            actor_roles=sorted(user.roles or []),
            job_type=JOB_TYPE_XLSX_IMPORT,
            payload={
                "file_id": request.file_id,
                **payload,
                "dry_run": request.dry_run,
                "update_existing": request.update_existing,
                "filename": request.filename or "",
            },
        )
    except ValueError as exc:
        raise BusinessException(ErrorCode.VALIDATION_ERROR) from exc
    return ImportExecuteResponse(job_id=job.id)


@router.get(
    "/jobs",
    response_model=list[ImportJobRead],
    summary="Журнал импортов",
)
def list_import_jobs(
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.read")),
) -> list[ImportJobRead]:
    stmt = (
        select(ReportJob)
        .where(ReportJob.job_type == JOB_TYPE_XLSX_IMPORT)
        .order_by(ReportJob.created_at.desc(), ReportJob.id.desc())
        .limit(100)
    )
    if not _is_admin(user) and "manager" not in set(user.roles or ()):
        stmt = stmt.where(ReportJob.actor_sub == (user.id or ""))
    return [_read_model(job) for job in db.scalars(stmt).all()]


@router.get(
    "/jobs/{job_id}",
    response_model=ImportJobRead,
    summary="Статус импорта",
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403], 404: ERROR_RESPONSES[404]},
)
def get_import_job(
    job_id: str,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.read")),
) -> ImportJobRead:
    try:
        uuid.UUID(str(job_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise BusinessException(ErrorCode.NOT_FOUND) from exc
    return _read_model(_get_visible_job(db, job_id, user))


@router.get(
    "/jobs/{job_id}/report",
    summary="Скачать отчёт об ошибках",
    description="XLSX со списком построчных ошибок. 404 — ошибок нет или отчёта нет.",
    responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403], 404: ERROR_RESPONSES[404]},
)
def download_import_report(
    job_id: str,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.read")),
) -> FileResponse:
    try:
        uuid.UUID(str(job_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise BusinessException(ErrorCode.NOT_FOUND) from exc
    job = _get_visible_job(db, job_id, user)
    now = datetime.now(timezone.utc)
    if job.expires_at is not None and now >= job.expires_at:
        raise BusinessException(ErrorCode.GONE)
    if job.status != jobs.STATUS_READY:
        raise BusinessException(ErrorCode.REPORT_NOT_READY)
    result = job.result if isinstance(job.result, dict) else {}
    if not result.get("errors"):
        raise BusinessException(ErrorCode.NOT_FOUND)
    path = jobs.contained_job_path(job.file_path)
    if path is None or not path.is_file():
        raise BusinessException(ErrorCode.FILE_NOT_FOUND)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"import_report_{str(job.id)[:8]}.xlsx",
    )
