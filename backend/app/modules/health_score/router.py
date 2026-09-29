"""Operational university Health Score endpoints backed by the analytics batch loader."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.permissions import require_permission
from app.core.policies import get_data_scope
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.catalog import ITProgram, University
from app.modules.analytics.integration import Selection
from app.modules.analytics.repository import load_data
from app.modules.analytics.service import build_matrix

router = APIRouter(prefix="/universities", tags=["Analytics"])

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
    for cell in matrix.cells:
        factors.extend(cell.health_factors)
    return {
        "university_id": university_id, "score": row.health_score, "level": row.health_level,
        "started_programs": row.started_programs, "total_programs": row.total_programs,
        "factors": [{"label": label} for label in dict.fromkeys(factors)],
        "calculated_at": datetime.now(timezone.utc),
    }

@router.get("/{university_id}/health-score", summary="Текущий Health Score ВУЗа")
def health_score(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)

@router.get("/{university_id}/health", include_in_schema=False)
def health_alias(university_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(require_permission("university.read"))):
    return _health(university_id, db, user)
