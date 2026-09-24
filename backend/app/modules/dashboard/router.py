"""Dashboard (§16): read-only aggregations for manager's main panel.

LEGACY QUARANTINE (M7) — DO NOT MOUNT in ``app/api/router.py`` (direct
``db.query`` aggregations in the handler; superseded by
``analytics/overview``). Reactivation requires the checklist in
``docs/AUDIT.md`` (§0). See ``scripts/check_legacy_quarantine.py``.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.health_score.models import HealthScoreHistory
from app.modules.programs.models import Program
from app.modules.teachers.models import Teacher
from app.modules.universities.models import University
from app.modules.workflow.models import Task

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _u: CurrentUser = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    overdue = db.query(func.count(Task.id)).filter(
        Task.status != "done", Task.deadline.is_not(None), Task.deadline < now).scalar() or 0
    avg_health = db.query(func.avg(HealthScoreHistory.score)).scalar()
    by_region = db.query(University.region, func.count(University.id)).group_by(University.region).all()
    return {
        "universities_total": db.query(func.count(University.id)).scalar() or 0,
        "programs_active": db.query(func.count(Program.id)).filter(Program.status == "active").scalar() or 0,
        "programs_launching": db.query(func.count(Program.id)).filter(Program.status == "launching").scalar() or 0,
        "tasks_overdue": overdue,
        "teachers_total": db.query(func.count(Teacher.id)).scalar() or 0,
        "avg_health_score": round(float(avg_health), 1) if avg_health else None,
        "by_region": [{"region": r or "", "count": c} for r, c in by_region],
    }
