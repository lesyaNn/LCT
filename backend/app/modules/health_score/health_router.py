"""P2-08-01: GET /api/v1/universities/{id}/health-score.

Thin route: params -> auth/RBAC -> cache -> service -> DTO. Без SQL и
бизнес-логики (архитектурное правило API -> Service -> Model).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.catalog import University
from app.modules.health_score import cache as health_cache
from app.modules.health_score.health_service import calculate_health_score
from app.modules.health_score.schemas import HealthScoreResponse

router = APIRouter(prefix="/universities", tags=["health-score"])


@router.get(
    "/{university_id}/health-score",
    response_model=HealthScoreResponse,
    summary="Health Score вуза (взвешенный, с breakdown и reasons)",
    description=(
        "Формула §12 ТЗ: T*0.25 + D*0.20 + S*0.20 + E*0.20 + L*0.15. "
        "Кэш 5 минут (ключ `health_score:{id}`), инвалидируется писателями. "
        "Неизвестный вуз → 404."
    ),
    responses={
        404: {"description": "Вуз не найден"},
    },
)
def get_university_health_score(
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> HealthScoreResponse:
    exists = db.execute(
        select(University.id).where(University.id == university_id)
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="University not found")
    cached = health_cache.get_cached(university_id)
    if cached is not None:
        return cached
    result = calculate_health_score(db, university_id)
    health_cache.put_cached(result)
    return result
