"""P2-08-01: кэш Health Score (Redis с in-memory fallback, TTL 5 минут).

Писатели (переходы workflow, документы, сертификаты, задачи) инвалидируют
ключ через :func:`invalidate_health_score` — background/event-хуки
подключаются отдельными задачами, ключ contract зафиксирован здесь.
"""

from __future__ import annotations

import uuid

from app.infrastructure import redis as redis_infra
from app.modules.health_score.schemas import HealthScoreResponse

#: TTL кэша Health Score в секундах (P2-08-01: 5 минут).
HEALTH_SCORE_TTL = 300


def cache_key(university_id: uuid.UUID) -> str:
    """Ключ кэша одного вуза (контракт инвалидации для писателей)."""
    return f"health_score:{university_id}"


def get_cached(university_id: uuid.UUID) -> HealthScoreResponse | None:
    """Прочитать кэш; ``None`` — промах (или битый JSON, тогда игнорируем)."""
    raw = redis_infra.cache_get(cache_key(university_id))
    if not raw:
        return None
    try:
        return HealthScoreResponse.model_validate_json(raw)
    except ValueError:
        return None


def put_cached(response: HealthScoreResponse) -> None:
    """Положить ответ в кэш на ``HEALTH_SCORE_TTL``."""
    redis_infra.cache_set(
        cache_key(response.university_id), response.model_dump_json(), HEALTH_SCORE_TTL
    )


def invalidate_health_score(university_id: uuid.UUID) -> None:
    """Инвалидировать кэш вуза (вызывают писатели после изменений).

    H6: удаление — через публичный ``cache_delete`` инфраструктуры (Redis или
    fallback), без доступа к приватным полям и без незащищённого ``delete``.
    Никогда не бросает исключение в вызывающий поток.
    """
    redis_infra.cache_delete(cache_key(university_id))


__all__ = [
    "HEALTH_SCORE_TTL",
    "cache_key",
    "get_cached",
    "invalidate_health_score",
    "put_cached",
]
