"""P2-08-03: GET /api/v1/health-score/ranking (опционально, P1).

Рейтинг вузов по Health Score для Dashboard (top/worst). Вузов мало (<100),
поэтому расчёт последовательный + сортировка в памяти; рейтинг кэшируется
на 10 минут. Если времени нет — Dashboard использует batch (P2-08-02).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.policies import apply_university_scope, get_data_scope
from app.core.security import CurrentUser
from app.db.session import get_db
from app.infrastructure import redis as redis_infra
from app.models.catalog import University
from app.modules.health_score import cache as health_cache
from app.modules.health_score.health_service import calculate_health_score
from app.modules.health_score.schemas import HealthScoreRankItem, HealthScoreShort
from app.schemas.common import HealthScoreStatus

router = APIRouter(prefix="/health-score", tags=["health-score"])

#: TTL кэша рейтинга в секундах (редко меняется — 10 минут).
RANKING_TTL = 600


class HealthScoreRankingResponse(BaseModel):
    """Ответ рейтинга (P2-08-03)."""

    items: list[HealthScoreRankItem] = Field(default_factory=list)
    total: int = Field(ge=0, description="Всего вузов после фильтра статуса", examples=[10])

    model_config = {"from_attributes": True}


def _ranking_key(status: HealthScoreStatus | None, limit: int, offset: int) -> str:
    return f"health_score:ranking:{status or 'all'}:{limit}:{offset}"


@router.get(
    "/ranking",
    response_model=HealthScoreRankingResponse,
    summary="Рейтинг вузов по Health Score (опционально)",
    description=(
        "Сортировка по score DESC, rank 1-based по полному отфильтрованному "
        "списку, затем пагинация. Кэш 10 минут."
    ),
)
def get_health_score_ranking(
    limit: int = Query(default=20, ge=1, le=100, description="Сколько строк вернуть"),
    offset: int = Query(default=0, ge=0, description="Сдвиг для пагинации"),
    status: HealthScoreStatus | None = Query(default=None, description="Фильтр статуса"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> HealthScoreRankingResponse:
    global_scope = get_data_scope(user).is_all
    key = _ranking_key(status, limit, offset)
    raw = redis_infra.cache_get(key) if global_scope else None
    if raw:
        try:
            return HealthScoreRankingResponse.model_validate_json(raw)
        except ValueError:
            pass
    universities = list(
        db.execute(apply_university_scope(
            select(University.id, University.name).order_by(University.name),
            University.id, user,
        )).all()
    )
    scored: list[tuple[uuid.UUID, str, HealthScoreShort]] = []
    for university_id, name in universities:
        cached = health_cache.get_cached(university_id)
        full = cached if cached is not None else calculate_health_score(db, university_id)
        if cached is None:
            health_cache.put_cached(full)
        short = HealthScoreShort.from_full(full)
        if status is not None and short.status != status:
            continue
        scored.append((university_id, name, short))
    scored.sort(key=lambda row: row[2].score, reverse=True)
    total = len(scored)
    items = [
        HealthScoreRankItem(
            university_id=university_id, score=short.score, status=short.status,
            breakdown=short.breakdown, rank=index, university_name=name,
        )
        for index, (university_id, name, short) in enumerate(
            scored[offset:offset + limit], start=offset + 1
        )
    ]
    result = HealthScoreRankingResponse(items=items, total=total)
    if global_scope:
        redis_infra.cache_set(key, result.model_dump_json(), RANKING_TTL)
    return result
