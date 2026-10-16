"""Operational university Health Score endpoints backed by the analytics batch loader."""
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
from app.modules.health_score.operational import BASE_SCORE, PENALTIES, TASK_PENALTY_CAP, UNIVERSITY_SCORE_CAPS

router = APIRouter(prefix="/universities", tags=["Analytics"])

def _history(db: Session, university_id: UUID, score: int | None, level: str, now: datetime):
    """Record a real score when it changes, then return recent backend observations."""
    try:
        latest = db.scalar(
            select(HealthScoreObservation)
            .where(HealthScoreObservation.university_id == university_id)
            .order_by(HealthScoreObservation.calculated_at.desc())
            .limit(1)
        )
        if score is not None and (
            latest is None
            or latest.score != score
            or latest.level != level
            or latest.calculated_at < now - timedelta(days=731)
        ):
            db.add(HealthScoreObservation(
                university_id=university_id, score=score, level=level, calculated_at=now
            ))
            db.commit()
        observations = db.scalars(
            select(HealthScoreObservation)
            .where(
                HealthScoreObservation.university_id == university_id,
                HealthScoreObservation.calculated_at >= now - timedelta(days=731),
            )
            .order_by(HealthScoreObservation.calculated_at.desc())
        ).all()
        history = []
        for item in reversed(observations):
            if not history or (item.score, item.level) != (history[-1]["score"], history[-1]["level"]):
                history.append({"date": item.calculated_at.isoformat(), "score": item.score, "level": item.level})
        return history
    except SQLAlchemyError:
        # Installations that have not applied the new migration can still show
        # the current real backend score. No historical values are fabricated.
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
        "calculation": {
            "base_score": BASE_SCORE,
            "penalties": [
                {"label": "Просрочен текущий этап", "points": PENALTIES["workflow_overdue"]},
                {"label": "Не назначен ответственный на текущий этап", "points": PENALTIES["responsible_missing"]},
                {"label": "Просроченная задача", "points": PENALTIES["overdue_task"], "maximum": TASK_PENALTY_CAP},
                {"label": "Просрочена лицензия", "points": PENALTIES["expired_license"]},
                {"label": "Лицензия скоро истекает", "points": PENALTIES["license_expires_soon"]},
            ],
            "critical_cap": UNIVERSITY_SCORE_CAPS["critical"],
            "attention_cap": UNIVERSITY_SCORE_CAPS["attention"],
        },
        "programs": programs,
        "calculated_at": now,
    }

@router.get("/{university_id}/health-score", summary="Текущий Health Score ВУЗа")
def health_score(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)

@router.get("/{university_id}/health", include_in_schema=False)
def health_alias(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)
