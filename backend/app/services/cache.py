"""Backend cache (P5-12-01): Redis каталоги на коротком TTL + инвалидация.

Поверх ``app.infrastructure.redis`` (уже с in-memory fallback): единый
``CACHE_TTL``, ``cache_key``, ``@cached`` декоратор и инвалидаторы для
каталогов / health-score / аналитики. Писатели вызывают инвалидаторы после
CREATE/UPDATE/DELETE.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from functools import wraps

from app.infrastructure import redis as redis_infra

logger = logging.getLogger("rtk")

CACHE_TTL = {
    "catalogs": 300,  # 5 минут: directions, programs, products, vendors
    "health_score": 300,  # 5 минут
    "analytics": 60,  # 1 минута: overview
    "university_list": 60,  # 1 минута
}


def cache_key(prefix: str, *args, **kwargs) -> str:
    key_data = f"{prefix}:{args}:{sorted(kwargs.items(), key=lambda kv: kv[0])}"
    return f"{prefix}:{hashlib.md5(key_data.encode()).hexdigest()[:32]}"


def cached(ttl_key: str, prefix: str):
    """Декоратор кэширования JSON-сериализуемого результата."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = cache_key(prefix, *args, **kwargs)
            try:
                hit = redis_infra.cache_get(key)
            except Exception:
                hit = None
            if hit:
                try:
                    return json.loads(hit)
                except ValueError:
                    pass
            result = await func(*args, **kwargs)
            try:
                redis_infra.cache_set(
                    key, json.dumps(result, default=str), CACHE_TTL[ttl_key]
                )
            except Exception:
                logger.warning("cache write failed for %s", key)
            return result

        return wrapper

    return decorator


def _delete_pattern(pattern: str) -> None:
    # H6: удаление — через публичный хелпер инфраструктуры (не бросает).
    redis_infra.cache_delete_pattern(pattern)


async def invalidate_catalogs() -> None:
    _delete_pattern("catalogs:")


async def invalidate_health_score(university_id: uuid.UUID | None = None) -> None:
    if university_id is not None:
        redis_infra.cache_delete(f"health_score:{university_id}")
        _delete_pattern("health_score:batch:")
        return
    _delete_pattern("health_score:")


async def invalidate_analytics() -> None:
    _delete_pattern("analytics:")


__all__ = [
    "CACHE_TTL",
    "cache_key",
    "cached",
    "invalidate_analytics",
    "invalidate_catalogs",
    "invalidate_health_score",
]
