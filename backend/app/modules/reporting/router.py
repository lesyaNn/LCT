"""Reporting (§15): small exports inline, heavy ones via job queue (§3/§18).

LEGACY QUARANTINE (M7) — DO NOT MOUNT in ``app/api/router.py`` (prefix
``/reports`` collides with the canonical async ``analytics/reports_router``;
``app.modules.universities.models`` import below is dangling).
Reactivation requires the checklist in ``docs/DEFERRED_MODULES.md``.
See ``scripts/check_legacy_quarantine.py``.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.db.session import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


class ExportReq(BaseModel):
    format: str = "csv"  # csv | xlsx
    region: str | None = None
    columns: list[str] | None = None


@router.post("/export")
def export(req: ExportReq, db: Session = Depends(get_db),
           _u: CurrentUser = Depends(get_current_user)):
    # H7: legacy demo stub over the removed task_queue — stays importable for
    # the quarantine gate but never serves. Use POST /api/v1/reports (P4-06-01).
    raise BusinessException(ErrorCode.GONE)


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _u: CurrentUser = Depends(get_current_user)):
    # H7: see export() above — canonical status is GET /api/v1/reports/{id}.
    raise BusinessException(ErrorCode.GONE)
