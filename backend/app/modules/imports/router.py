"""XLSX/XLS import endpoints (P4-10-01) on the shared job ledger (P4-06-01).

``POST /import/preview`` stages the workbook and returns headers + first
rows (no DB writes). ``POST /import/execute`` persists an ``xlsx_import``
row in ``report_jobs`` (migration 000019) and answers ``202 + {job_id}``;
the frontend polls ``GET /import/jobs/{id}`` until ``ready | failed``
(P4-06-02 contract) and downloads the XLSX error report via
``GET /import/jobs/{id}/report`` (P4-10-02). Repeated POSTs with the same
file + mapping + options reuse the live job (``idempotency_key``).

MVP note: the import still runs inside the request (lifecycle
``queued -> building -> ready | failed`` is committed to the DB, so polling
never hangs on "queued"). Moving execution to the dedicated ``worker``
container is TODO(P4-06-01); ``BackgroundTasks`` are banned by the spec.
"""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, user_permissions
from app.core.security import CurrentUser
from app.core.errors import BusinessException, SecurityError
from app.schemas.errors import ErrorCode
from app.modules.audit.service import get_audit_db
from app.models.report_job import (
    JOB_TYPE_XLSX_IMPORT,
    STATUS_BUILDING,
    STATUS_READY,
    ReportJob,
)
from app.modules.analytics import report_jobs as ledger
from app.modules.imports import service
from app.modules.imports.schemas import (
    ImportExecuteRequest,
    ImportExecuteResponse,
    ImportJobStatus,
    ImportPreview,
)
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/import", tags=["Import"])

#: Re-POST with the same key reuses a job in one of these states (a
#: ``failed`` job is resurrected by ``mark_building`` into a fresh attempt).
REUSABLE_STATUSES = ("queued", "building", "ready")


def _idempotency_key(file_id: str, mapping: dict, update_existing: bool, dry_run: bool) -> str:
    raw = json.dumps(
        {"f": file_id, "m": mapping, "u": update_existing, "d": dry_run},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_admin(user: CurrentUser) -> bool:
    return "*" in user_permissions(user)


def _get_visible_job(db: Session, job_id: str, user: CurrentUser) -> ReportJob:
    job = ledger.get_job(db, job_id)
    if job is None or job.job_type != JOB_TYPE_XLSX_IMPORT:
        raise BusinessException(ErrorCode.NOT_FOUND)
    if not ledger.job_visible_to(job, user, is_admin=_is_admin(user)):
        raise SecurityError(ErrorCode.FORBIDDEN)
    return job


def _get_or_create_job(
    db: Session, req: ImportExecuteRequest, user: CurrentUser, key: str
) -> ReportJob:
    """Idempotent submit: reuse a live job for the key, else persist one."""
    existing = db.execute(
        select(ReportJob)
        .where(
            ReportJob.job_type == JOB_TYPE_XLSX_IMPORT,
            ReportJob.idempotency_key == key,
            ReportJob.status.in_(REUSABLE_STATUSES),
        )
        .order_by(ReportJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None and ledger.job_visible_to(
        existing, user, is_admin=_is_admin(user)
    ):
        return existing
    return ledger.create_job(
        db,
        format="xlsx",  # the job artifact (error report) is an XLSX file
        filters={},
        columns=[],
        actor_sub=user.id or "",
        actor_name=user.name or user.username or "",
        actor_roles=sorted(user.roles or set()),
        job_type=JOB_TYPE_XLSX_IMPORT,
        payload={
            "file_id": req.file_id,
            "mapping": req.mapping,
            "update_existing": req.options.update_existing,
            "dry_run": req.options.dry_run,
        },
        idempotency_key=key,
    )


ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Ошибка валидации файла/маппинга"},
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации запроса"},
}


@router.post(
    "/preview",
    response_model=ImportPreview,
    summary="Загрузка XLSX/XLS и предпросмотр",
    description=(
        "Принимает .xlsx/.xls (multipart/form-data), сохраняет его под file_id "
        "и возвращает заголовки, первые 10 строк и число строк. "
        "file_id используется в POST /import/execute."
    ),
    responses=ERROR_RESPONSES,
)
def import_preview(
    file: UploadFile = File(..., description="XLSX/XLS файл каталогов (до 10 МБ)"),
    _u: CurrentUser = Depends(require_permission("import.write")),
):
    try:
        content = file.file.read()
        file_id = service.stage_upload(file.filename or "", content)
        parsed = service.parse_preview(file_id)
    except service.ImportValidationError as exc:
        raise BusinessException(ErrorCode.IMPORT_VALIDATION_FAILED) from exc
    return ImportPreview(
        file_id=file_id,
        filename=file.filename or "",
        headers=parsed["headers"],
        preview=parsed["preview"],
        row_count=parsed["row_count"],
        detected_sheet=parsed["detected_sheet"],
    )


@router.post(
    "/execute",
    response_model=ImportExecuteResponse,
    status_code=202,
    summary="Запуск импорта по маппингу",
    description=(
        "Создаёт job в report_jobs (P4-06-01) и возвращает job_id (202). "
        "Применяет mapping (колонка файла → поле БД) к сохранённому файлу; "
        "плохие строки пропускаются с ошибками (не роняют импорт). "
        "Итог — polling GET /import/jobs/{job_id} до ready | failed (P4-06-02), "
        "детали — в XLSX-отчёте GET /import/jobs/{job_id}/report (P4-10-02)."
    ),
    responses={
        **ERROR_RESPONSES,
        202: {"description": "Job создан/переиспользован, импорт выполняется"},
    },
)
def import_execute(
    req: ImportExecuteRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("import.write")),
):
    key = _idempotency_key(
        req.file_id, req.mapping,
        req.options.update_existing, req.options.dry_run,
    )
    job = _get_or_create_job(db, req, user, key)
    if job.status == STATUS_READY:
        return ImportExecuteResponse(job_id=str(job.id))
    if job.status == STATUS_BUILDING:
        # Another runner owns it — the client just polls.
        return ImportExecuteResponse(job_id=str(job.id))
    if not ledger.mark_building(db, job):
        # Lost the claim race — whoever won will finish it; poll it.
        return ImportExecuteResponse(job_id=str(job.id))
    try:
        summary = service.execute_import(
            db,
            req.file_id,
            req.mapping,
            update_existing=req.options.update_existing,
            dry_run=req.options.dry_run,
        )
    except service.ImportValidationError as exc:
        ledger.mark_failed(db, job, exc)
        raise BusinessException(ErrorCode.IMPORT_VALIDATION_FAILED) from exc
    except Exception as exc:
        ledger.mark_failed(db, job, exc)
        raise
    # P4-10-02: файловый артефакт job — XLSX-отчёт (Итог + Ошибки).
    artifact = job.file_path or str(ledger.job_file_path(job.id, "xlsx"))
    size = service.write_error_report(summary, artifact)
    job.result = summary
    db.add(job)
    ledger.mark_ready(db, job, file_path=artifact, file_size=size)
    return ImportExecuteResponse(job_id=str(job.id))


@router.get(
    "/jobs/{job_id}",
    response_model=ImportJobStatus,
    summary="Статус import job",
    description=(
        "Polling-эндпоинт (P4-06-02): статусы queued → building → "
        "ready | failed из общей таблицы report_jobs. "
        "Готовый результат — в result (inserted/updated/skipped/errors), "
        "причина неуспеха — в error. Видимость: свои jobs; admin — все."
    ),
    responses={
        401: ERROR_RESPONSES[401],
        403: {"model": ErrorResponse, "description": "Чужой job"},
        404: {"model": ErrorResponse, "description": "Job не найден"},
        422: ERROR_RESPONSES[422],
    },
)
def import_job_status(
    job_id: str,
    user: CurrentUser = Depends(require_permission("import.read")),
    db: Session = Depends(get_audit_db),
):
    job = _get_visible_job(db, job_id, user)
    return ImportJobStatus(
        id=str(job.id), type=job.job_type, status=job.status,
        progress=int(job.progress or 0), result=job.result,
        error=job.error_message,
    )


@router.get(
    "/jobs/{job_id}/report",
    summary="Скачать XLSX-отчёт об ошибках импорта",
    description=(
        "P4-10-02: файловый артефакт job (листы «Итог» и «Ошибки»). "
        "410 — срок скачивания истёк (24 часа)."
    ),
    responses={
        401: ERROR_RESPONSES[401],
        403: {"model": ErrorResponse, "description": "Чужой job"},
        400: {"model": ErrorResponse, "description": "REPORT_NOT_READY — отчёт ещё формируется"},
        404: {"model": ErrorResponse, "description": "Файл отчёта не найден"},
        410: {"model": ErrorResponse, "description": "Срок скачивания истёк"},
        422: ERROR_RESPONSES[422],
    },
)
def import_job_report(
    job_id: str,
    user: CurrentUser = Depends(require_permission("import.read")),
    db: Session = Depends(get_audit_db),
):
    job = _get_visible_job(db, job_id, user)
    if job.status != STATUS_READY or not job.file_path:
        raise BusinessException(ErrorCode.REPORT_NOT_READY)
    expires_at = job.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:  # sqlite-тесты отдают naive
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise BusinessException(ErrorCode.GONE)
    path = ledger.contained_job_path(job.file_path)
    if path is None or not path.is_file():
        raise BusinessException(ErrorCode.FILE_NOT_FOUND)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"import_report_{str(job.id)[:8]}.xlsx",
    )
