"""Redis client: cache / jobs / rate-limit. Falls back to in-memory dict."""
import logging
import time

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

from app.config import settings

logger = logging.getLogger("rtk")

_memory: dict = {}
_client = None

if redis is not None:
    try:
        _client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        _client.ping()
    except Exception:
        logger.warning(
            "redis unavailable at %s — using in-memory fallback (jobs/cache are node-local)",
            settings.redis_url,
        )
        _client = None


def get_client():
    """Raw redis client or None (callers must handle the fallback)."""
    return _client


def cache_get(key: str):
    if _client:
        val = _client.get(key)
        return val.decode() if isinstance(val, bytes) else val
    entry = _memory.get(key)
    if not entry:
        return None
    value, exp = entry
    if exp and exp < time.time():
        _memory.pop(key, None)
        return None
    return value


def cache_set(key: str, value: str, ttl: int = 300):
    if _client:
        _client.setex(key, ttl, value)
        return
    _memory[key] = (value, time.time() + ttl if ttl else None)
