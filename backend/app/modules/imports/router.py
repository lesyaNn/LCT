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

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview", response_model=ImportPreview)
def import_preview(
    file: UploadFile = File(...),
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


@router.post("/execute", response_model=ImportExecuteResponse)
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


@router.get("/jobs/{job_id}", response_model=ImportJobStatus)
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
