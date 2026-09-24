"""Reporting (§15): small exports inline, heavy ones via job queue (§3/§18)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.db.session import get_db
from app.infrastructure import task_queue
from app.modules.universities.models import University

router = APIRouter(prefix="/reports", tags=["reports"])


class ExportReq(BaseModel):
    format: str = "csv"  # csv | xlsx
    region: str | None = None
    columns: list[str] | None = None


@router.post("/export")
def export(req: ExportReq, db: Session = Depends(get_db),
           _u: CurrentUser = Depends(get_current_user)):
    q = db.query(University)
    if req.region:
        q = q.filter(University.region == req.region)
    rows = [{"id": u.id, "name": u.name, "region": u.region, "city": u.city,
             "status": u.status} for u in q.limit(5000).all()]
    if len(rows) > 1000:
        job_id = task_queue.enqueue("export_xlsx", {"format": req.format, "rows": rows[:5000]})
        return {"status": "accepted", "job_id": job_id}
    if req.format == "xlsx":
        job_id = task_queue.enqueue("export_xlsx", {"format": "xlsx", "rows": rows})
        task_queue.job_done(job_id, {"rows": len(rows), "format": "xlsx"})
        return {"status": "done", "job_id": job_id, "rows": len(rows)}
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["id", "name", "region", "city", "status"])
    w.writeheader()
    w.writerows(rows)
    return {"status": "done", "format": "csv", "rows": len(rows), "csv": buf.getvalue()[:20000]}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _u: CurrentUser = Depends(get_current_user)):
    job = task_queue.job_status(job_id)
    if not job:
        raise BusinessException(ErrorCode.NOT_FOUND)
    return job
