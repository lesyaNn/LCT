"""Dashboard (minimal, without teachers/health)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.catalog import University
from app.models.interactions import Meeting

router = APIRouter(prefix="/dashboard", tags=["Analytics"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    universities_total = db.scalar(select(func.count(University.id))) or 0
    meetings_total = db.scalar(select(func.count(Meeting.id))) or 0
    return {"universities_total": universities_total, "meetings_total": meetings_total}
