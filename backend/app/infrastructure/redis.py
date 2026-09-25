"""Redis client: cache / jobs / rate-limit. Falls back to in-memory dict.

H6: no network I/O on import (lazy connect with reconnect on failure), no
mutable globals outside this module (use :func:`cache_delete` /
:func:`cache_delete_pattern` instead of touching ``_memory``), and every
Redis call is guarded — a Redis outage degrades to the node-local fallback
instead of breaking the caller.
"""
import logging
import threading
import time

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

from app.config import settings

logger = logging.getLogger("rtk")

_memory: dict = {}
_client = None
_client_broken_until: float = 0.0
_lock = threading.Lock()

#: Cooldown between reconnect attempts after a failure (seconds).
_RECONNECT_COOLDOWN = 5.0


def _connect():
    global _client, _client_broken_until
    if redis is None:
        return None
    now = time.time()
    with _lock:
        if _client is not None:
            return _client
        if now < _client_broken_until:
            return None
        try:
            client = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
        except Exception:
            _client_broken_until = now + _RECONNECT_COOLDOWN
            logger.warning(
                "redis unavailable at %s — using in-memory fallback "
                "(jobs/cache are node-local)",
                settings.redis_url,
            )
            return None
        _client = client
        return _client


def _mark_broken():
    global _client, _client_broken_until
    with _lock:
        try:
            if _client is not None:
                _client.close()
        except Exception:
            pass
        _client = None
        _client_broken_until = time.time() + _RECONNECT_COOLDOWN


def get_client():
    """Lazily connected raw redis client or None (fallback mode).

    Kept for compatibility; prefer the ``cache_*`` helpers which degrade
    gracefully on their own.
    """
    return _connect()


def cache_get(key: str):
    client = _connect()
    if client is not None:
        try:
            val = client.get(key)
            return val.decode() if isinstance(val, bytes) else val
        except Exception:
            logger.warning("redis GET failed for %s — fallback to memory", key)
            _mark_broken()
    entry = _memory.get(key)
    if not entry:
        return None
    value, exp = entry
    if exp and exp < time.time():
        _memory.pop(key, None)
        return None
    return value


def cache_set(key: str, value: str, ttl: int = 300):
    client = _connect()
    if client is not None:
        try:
            client.setex(key, ttl, value)
            return
        except Exception:
            logger.warning("redis SET failed for %s — fallback to memory", key)
            _mark_broken()
    _memory[key] = (value, time.time() + ttl if ttl else None)


def cache_delete(key: str) -> None:
    """Delete one key from Redis or the memory fallback (never raises)."""
    client = _connect()
    if client is not None:
        try:
            client.delete(key)
            return
        except Exception:
            logger.warning("redis DEL failed for %s — fallback to memory", key)
            _mark_broken()
    _memory.pop(key, None)


def cache_delete_pattern(prefix: str) -> None:
    """Delete all keys starting with ``prefix`` (never raises)."""
    client = _connect()
    if client is not None:
        try:
            keys = list(client.scan_iter(match=f"{prefix}*"))
            if keys:
                client.delete(*keys)
            return
        except Exception:
            logger.warning(
                "redis pattern DEL failed for %s — fallback to memory", prefix
            )
            _mark_broken()
    for key in [k for k in list(_memory) if k.startswith(prefix)]:
        _memory.pop(key, None)
