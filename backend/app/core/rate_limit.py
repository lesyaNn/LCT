"""M10: fixed-window rate limiting for heavy endpoints (429 + contract code).

Abuse mitigation, not billing: approximate counters backed by Redis with a
node-local fallback. Never raises — on any backend error the request is
allowed (fail-open: a cache outage must not become an API outage).
"""
from __future__ import annotations

import hashlib
import threading
import time

_local: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()


def bucket_key(route: str, client_id: str) -> str:
    """Stable bucket name; the client id is already hashed by the caller."""
    return f"rl:{route}:{client_id}"


def hash_client_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds) for one hit (M10).

    Redis path uses GET/SET/INCR with the window as TTL; any failure (or no
    Redis) degrades to the guarded in-memory fallback.
    """
    from app.infrastructure import redis as redis_infra

    now = time.time()
    client = redis_infra.get_client()
    if client is not None:
        try:
            raw = client.get(key)
            if raw is None:
                client.setex(key, window_seconds, 1)
                return True, 0
            count = int(raw)
            if count >= limit:
                ttl = client.ttl(key)
                return False, max(int(ttl), 0) if ttl and ttl > 0 else window_seconds
            client.incr(key)
            return True, 0
        except Exception:
            pass  # fail-open to the local fallback below
    with _lock:
        count, reset = _local.get(key, (0, now + window_seconds))
        if now >= reset:
            count, reset = 0, now + window_seconds
        if count >= limit:
            return False, max(int(reset - now), 0)
        _local[key] = (count + 1, reset)
        return True, 0


def reset_local_buckets() -> None:
    """Test-only helper: clear the in-memory fallback."""
    with _lock:
        _local.clear()
