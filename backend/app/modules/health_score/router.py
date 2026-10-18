"""Operational university Health Score endpoints backed by the analytics batch loader."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.permissions import require_permission
from app.core.policies import get_data_scope
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.catalog import ITProgram, University
from app.models.health_score_observation import HealthScoreObservation
from app.modules.analytics.integration import Selection
from app.modules.analytics.repository import load_data
from app.modules.analytics.service import build_matrix
from app.modules.health_score.history import record_observation
from app.modules.health_score.schemas import UniversityHealthScore

router = APIRouter(prefix="/universities", tags=["Analytics"])
logger = logging.getLogger(__name__)

def _history(db: Session, university_id: UUID, score: int | None, level: str, now: datetime):
    """Record a real score when it changes, then return recent backend observations."""
    try:
        record_observation(db, university_id, score, level, now)
        observations = db.scalars(
            select(HealthScoreObservation)
            .where(
                HealthScoreObservation.university_id == university_id,
                HealthScoreObservation.calculated_at >= now - timedelta(days=731),
            )
            .order_by(HealthScoreObservation.calculated_at.desc())
        ).all()
        return [
            {"date": item.calculated_at.isoformat(), "score": item.score, "level": item.level}
            for item in reversed(observations)
        ]
    except SQLAlchemyError:
        logger.exception("Failed to persist or load Health Score history for university %s", university_id)
        db.rollback()
        return [{"date": now.isoformat(), "score": score, "level": level}] if score is not None else []

def _health(university_id: UUID, db: Session, user: CurrentUser):
    if db.scalar(select(University.id).where(University.id == university_id)) is None:
        raise HTTPException(status_code=404, detail="University not found")
    scope = get_data_scope(user)
    if not scope.is_all and university_id not in scope.university_ids:
        raise HTTPException(status_code=403, detail="Forbidden")
    programs = list(db.scalars(select(ITProgram.id)))
    data = load_data(db, Selection(university_ids=[university_id], program_ids=programs), today=datetime.now(timezone.utc).date())
    matrix = build_matrix(data, today=datetime.now(timezone.utc).date())
    row = matrix.rows[0] if matrix.rows else None
    if row is None:
        raise HTTPException(status_code=404, detail="University not found")
    factors = []
    columns = {column.id: column.name for column in matrix.columns}
    programs = []
    for cell in matrix.cells:
        if cell.health_state == "NOT_LINKED":
            continue
        factors.extend(cell.health_factors)
        programs.append({
            "program_id": cell.program_id, "program_name": columns[cell.program_id],
            "state": cell.health_state, "score": cell.health_score,
            "workflow_instance_id": cell.workflow_instance_id,
            "current_stage": cell.next_milestone, "factors": cell.health_factors,
            "workflow_progress": cell.workflow_progress, "stages_completed": cell.stages_completed,
            "stages_total": cell.stages_total, "deadline": cell.deadline, "overdue_days": cell.overdue_days,
        })
    attention_count = sum(item["state"] == "ATTENTION" for item in programs)
    critical_count = sum(item["state"] == "CRITICAL" for item in programs)
    started = [item for item in programs if item["state"] in {"HEALTHY", "ATTENTION", "CRITICAL", "COMPLETED"}]
    missing_responsible = any("ответственный" in factor.lower() for factor in factors)
    positive = []
    if row.active_workflows:
        positive.append("Есть активный Workflow")
    if not critical_count:
        positive.append("Нет критических просрочек")
    if started and not missing_responsible:
        positive.append("Ответственные назначены")
    now = datetime.now(timezone.utc)
    history = _history(db, university_id, row.health_score, row.health_level, now)
    return {
        "university_id": university_id, "score": row.health_score, "level": row.health_level,
        "started_programs": row.started_programs, "active_workflows": row.active_workflows,
        "total_programs": row.total_programs, "attention_count": attention_count, "critical_count": critical_count,
        "factors": [{"label": label} for label in dict.fromkeys(factors)],
        "positive_factors": [{"label": label} for label in dict.fromkeys(positive)],
        "history": history,
        "programs": programs,
        "calculated_at": now,
    }

@router.get("/{university_id}/health-score", response_model=UniversityHealthScore,
            summary="Текущий Health Score ВУЗа")
def health_score(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)

@router.get("/{university_id}/health", include_in_schema=False)
def health_alias(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)
