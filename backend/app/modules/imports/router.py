"""XLSX/XLS import endpoints (P4-10-01).

``POST /import/preview`` stages the workbook and returns headers + first
rows; ``POST /import/execute`` runs the import synchronously in the MVP
(job lifecycle is still recorded: queued -> running -> done | failed, so
``GET /import/jobs/{id}`` never hangs on "queued"); ``GET /import/jobs/{id}``
reports status + summary. Repeated POSTs with the same file + mapping +
options return the existing job (idempotency_key) instead of a duplicate
insert. The payload shape is worker-compatible: ``workers`` can dequeue
and run the same ``execute_import`` out-of-band (see run_imports_once).
"""

import hashlib
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
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


def _idempotency_key(file_id: str, mapping: dict, update_existing: bool, dry_run: bool) -> str:
    raw = json.dumps(
        {"f": file_id, "m": mapping, "u": update_existing, "d": dry_run},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    _u: CurrentUser = Depends(require_permission("import.write")),
):
    key = _idempotency_key(
        req.file_id, req.mapping,
        req.options.update_existing, req.options.dry_run,
    )
    job_id = task_queue.enqueue("xlsx_import", {
        "file_id": req.file_id,
        "mapping": req.mapping,
        "update_existing": req.options.update_existing,
        "dry_run": req.options.dry_run,
        "idempotency_key": key,
    })
    if (task_queue.job_status(job_id) or {}).get("status") == "done":
        return ImportExecuteResponse(job_id=job_id)
    task_queue.job_running(job_id)
    try:
        summary = service.execute_import(
            db,
            req.file_id,
            req.mapping,
            update_existing=req.options.update_existing,
            dry_run=req.options.dry_run,
        )
    except service.ImportValidationError as exc:
        task_queue.job_failed(job_id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        task_queue.job_failed(job_id, f"{type(exc).__name__}: {exc}")
        raise
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
    _u: CurrentUser = Depends(require_permission("import.read")),
):
    job = task_queue.job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ImportJobStatus(
        id=job["id"], type=job["type"], status=job["status"],
        result=job.get("result"),
    )
