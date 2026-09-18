"""XLSX import endpoints (P4-10-01).

``POST /import/preview`` stages the workbook and returns headers + first
rows; ``POST /import/execute`` runs the import synchronously in the MVP
and returns a ``job_id`` via the ``task_queue`` stub (shape-compatible
with the P4-06-01 background worker); ``GET /import/jobs/{id}`` reports
status + summary.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.infrastructure import task_queue
from app.modules.imports import service
from app.modules.imports.schemas import (
    ImportExecuteRequest,
    ImportExecuteResponse,
    ImportJobStatus,
    ImportPreview,
)
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/import", tags=["Import"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Ошибка валидации файла/маппинга"},
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
    422: {"model": ErrorResponse, "description": "Ошибка валидации запроса"},
}


@router.post(
    "/preview",
    response_model=ImportPreview,
    summary="Загрузка XLSX и предпросмотр",
    description=(
        "Принимает .xlsx (multipart/form-data), сохраняет его под file_id "
        "и возвращает заголовки, первые 10 строк и число строк. "
        "file_id используется в POST /import/execute."
    ),
    responses=ERROR_RESPONSES,
)
def import_preview(
    file: UploadFile = File(..., description="XLSX файл каталогов (до 10 МБ)"),
    _u: CurrentUser = Depends(get_current_user),
):
    try:
        content = file.file.read()
        file_id = service.stage_upload(file.filename or "", content)
        parsed = service.parse_preview(file_id)
    except service.ImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    summary="Запуск импорта по маппингу",
    description=(
        "Применяет mapping (колонка файла → поле БД) к сохранённому файлу. "
        "Плохие строки пропускаются с ошибками (не роняют импорт). "
        "Возвращает job_id; итог — в GET /import/jobs/{job_id}."
    ),
    responses=ERROR_RESPONSES,
)
def import_execute(
    req: ImportExecuteRequest,
    db: Session = Depends(get_db),
    _u: CurrentUser = Depends(get_current_user),
):
    try:
        job_id = task_queue.enqueue("xlsx_import", {"file_id": req.file_id})
        summary = service.execute_import(
            db,
            req.file_id,
            req.mapping,
            update_existing=req.options.update_existing,
            dry_run=req.options.dry_run,
        )
    except service.ImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    task_queue.job_done(job_id, summary)
    return ImportExecuteResponse(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=ImportJobStatus,
    summary="Статус import job",
    description="Возвращает статус задачи и summary импорта (inserted/updated/skipped/errors).",
    responses={
        401: ERROR_RESPONSES[401],
        404: {"model": ErrorResponse, "description": "Job не найден"},
        422: ERROR_RESPONSES[422],
    },
)
def import_job_status(
    job_id: str,
    _u: CurrentUser = Depends(get_current_user),
):
    job = task_queue.job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ImportJobStatus(
        id=job["id"], type=job["type"], status=job["status"],
        result=job.get("result"),
    )
