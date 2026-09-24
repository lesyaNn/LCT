"""P2-08-03: GET /api/v1/health-score/ranking (опционально, P1).

Рейтинг вузов по Health Score для Dashboard (top/worst). Вузов мало (<100),
поэтому расчёт последовательный + сортировка в памяти; рейтинг кэшируется
на 10 минут. Если времени нет — Dashboard использует batch (P2-08-02).
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.policies import apply_university_scope, get_data_scope
from app.core.security import CurrentUser
from app.db.session import get_db
from app.infrastructure import redis as redis_infra
from app.models.catalog import University
from app.models.health_score import HealthScoreCurrent
from app.modules.health_score.schemas import HealthScoreRankItem
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
    base = select(
        University.id.label("university_id"), University.name.label("university_name"),
        HealthScoreCurrent.score, HealthScoreCurrent.status, HealthScoreCurrent.breakdown,
    ).join(HealthScoreCurrent, HealthScoreCurrent.university_id == University.id)
    base = apply_university_scope(base, University.id, user)
    if status is not None:
        base = base.where(HealthScoreCurrent.status == status)
    # Keep the window in the scoped/filtered subquery; no hidden universities
    # influence the public rank. SQL applies offset/limit before response build.
    scoped = base.subquery("scoped")
    ranked = select(
        scoped,
        func.row_number().over(order_by=(scoped.c.score.desc(), scoped.c.university_id.asc())).label("rank"),
    ).subquery("ranked")
    rows = list(db.execute(select(ranked).where(
        ranked.c.rank > offset, ranked.c.rank <= offset + limit
    ).order_by(ranked.c.rank)).all())
    total = int(db.execute(select(func.count()).select_from(scoped)).scalar() or 0)
    items = [
        HealthScoreRankItem(
            university_id=row.university_id, score=row.score, status=row.status,
            breakdown=row.breakdown, rank=int(row.rank), university_name=row.university_name,
        )
        for row in rows
    ]
    result = HealthScoreRankingResponse(items=items, total=total)
    if global_scope:
        redis_infra.cache_set(key, result.model_dump_json(), RANKING_TTL)
    return result
