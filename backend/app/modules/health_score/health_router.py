"""P2-08-01/02: GET /api/v1/universities/{id}/health-score + batch.

Thin routes: params -> auth/RBAC -> cache -> service -> DTO. Без SQL и
бизнес-логики (архитектурное правило API -> Service -> Model).
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.permissions import require_permission
from app.core.policies import apply_university_scope, ensure_university_visible
from app.core.security import CurrentUser
from app.db.session import get_db
from app.infrastructure import redis as redis_infra
from app.models.catalog import University
from app.models.health_score import HealthScoreSnapshot
from app.modules.health_score import cache as health_cache
from app.modules.health_score.attention import get_attention_items
from app.modules.health_score.health_service import calculate_health_score
from app.modules.health_score.schemas import (
    AttentionItemsResponse,
    HealthScoreResponse,
    HealthScoreShort,
)
from app.modules.health_score.snapshot_schemas import (
    HealthScoreSnapshotOut,
    SnapshotTrigger,
)
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/universities", tags=["health-score"])

#: Максимум вузов за один batch-запрос (P2-08-02).
BATCH_MAX_IDS = 50


class HealthScoreBatchResponse(BaseModel):
    """Ответ batch endpoint (P2-08-02): короткие скоры в порядке запроса."""

    items: list[HealthScoreShort] = Field(default_factory=list)

    model_config = {"from_attributes": True}


def _parse_ids(raw: str) -> list[uuid.UUID]:
    """Разобрать CSV UUIDs (422 при пустом/битом вводе — стиль проекта)."""
    try:
        ids = [uuid.UUID(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    if not ids:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    if len(ids) > BATCH_MAX_IDS:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    return ids


@router.get(
    "/health-score",
    response_model=HealthScoreBatchResponse,
    summary="Batch Health Score вузов (для Dashboard и списка)",
    description=(
        "Короткие скоры нескольких вузов одним запросом. Порядок ответов = "
        "порядку `ids`. Несуществующие вузы пропускаются без ошибки. "
        "Расчёт последовательный: один sync Session нельзя делить между "
        "корутинами (отклонение от ТЗ-скетча с asyncio.gather — правило P1-04-06). "
        "ВАЖНО: зарегистрирован раньше `/{id}/health-score`, иначе FastAPI "
        "матчит 'health-score' как university_id."
    ),
    responses={
        422: {"description": "Пустые/битые ids или больше 50 за запрос"},
    },
)
def get_universities_health_score_batch(
    ids: str = Query(
        description="Comma-separated UUIDs, максимум 50",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6,7c9e6679-7425-40de-944b-e07fc1f90ae7"],
    ),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> HealthScoreBatchResponse:
    wanted = _parse_ids(ids)
    existing = set(
        db.execute(
            apply_university_scope(
                select(University.id).where(University.id.in_(wanted)), University.id, user
            )
        ).scalars().all()
    )
    items: list[HealthScoreShort] = []
    for university_id in wanted:
        if university_id not in existing:
            continue
        cached = health_cache.get_cached(university_id)
        if cached is not None:
            items.append(HealthScoreShort.from_full(cached))
            continue
        full = calculate_health_score(db, university_id)
        health_cache.put_cached(full)
        items.append(HealthScoreShort.from_full(full))
    return HealthScoreBatchResponse(items=items)


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
    user: CurrentUser = Depends(require_permission("university.read")),
) -> HealthScoreResponse:
    exists = db.execute(
        select(University.id).where(University.id == university_id)
    ).first()
    if exists is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    ensure_university_visible(university_id, user)
    cached = health_cache.get_cached(university_id)
    if cached is not None:
        return cached
    result = calculate_health_score(db, university_id)
    health_cache.put_cached(result)
    return result




@router.get(
    "/{university_id}/attention-items",
    response_model=AttentionItemsResponse,
    summary="Что требует внимания (детерминированные правила)",
    description=(
        "WOW для демо: просроченные этапы, истекающие лицензии, просроченные "
        "документы, истекающие сертификаты, программы под риском запуска. "
        "Без AI — только правила. Кэш 5 минут. Неизвестный вуз → 404."
    ),
    responses={
        404: {"description": "Вуз не найден"},
    },
)
def get_university_attention_items(
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> AttentionItemsResponse:
    exists = db.execute(
        select(University.id).where(University.id == university_id)
    ).first()
    if exists is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    ensure_university_visible(university_id, user)
    cache_key = f"attention_items:{university_id}"
    raw = redis_infra.cache_get(cache_key)
    if raw:
        try:
            return AttentionItemsResponse.model_validate_json(raw)
        except ValueError:
            pass
    result = AttentionItemsResponse(items=get_attention_items(db, university_id))
    redis_infra.cache_set(cache_key, result.model_dump_json(), 300)
    return result


@router.get(
    "/{university_id}/health-score/history",
    response_model=list[HealthScoreSnapshotOut],
    summary="История Health Score вуза (снапшоты, новые первыми)",
    description=(
        "Снапшоты таблицы health_score_snapshots (миграция 000015): "
        "ежедневный cron (daily_cron) и event-писатели (transition, "
        "document_update). Глубина — ?days= (1–365, по умолчанию 30), "
        "опциональный фильтр ?trigger_event=. Неизвестный вуз → 404."
    ),
    responses={
        404: {"description": "Вуз не найден"},
    },
)
def get_university_health_score_history(
    university_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365, description="Глубина истории в днях"),
    trigger_event: SnapshotTrigger | None = Query(
        default=None, description="Фильтр по триггеру (по умолчанию — все)"
    ),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> list[HealthScoreSnapshotOut]:
    from datetime import datetime, timezone

    exists = db.execute(
        select(University.id).where(University.id == university_id)
    ).first()
    if exists is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    ensure_university_visible(university_id, user)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(HealthScoreSnapshot)
        .where(
            HealthScoreSnapshot.university_id == university_id,
            HealthScoreSnapshot.calculated_at >= cutoff,
        )
        .order_by(HealthScoreSnapshot.calculated_at.desc())
    )
    if trigger_event is not None:
        stmt = stmt.where(HealthScoreSnapshot.trigger_event == trigger_event)
    return list(db.execute(stmt).scalars().all())
