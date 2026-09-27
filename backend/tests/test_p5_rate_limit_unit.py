"""M10: rate limiter contract (pure-unit, no database)."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.middleware import RATE_LIMITED_PATHS, RateLimitMiddleware
from app.core.rate_limit import check_rate_limit, reset_local_buckets


def test_check_rate_limit_allows_then_denies():
    reset_local_buckets()
    key = "rl:test:unit"
    assert check_rate_limit(key, 2, 60) == (True, 0)
    assert check_rate_limit(key, 2, 60) == (True, 0)
    allowed, retry = check_rate_limit(key, 2, 60)
    assert allowed is False and retry >= 0


def test_check_rate_limit_never_raises_without_redis(monkeypatch):
    reset_local_buckets()
    import app.infrastructure.keydb as redis_infra

    monkeypatch.setattr(redis_infra, "redis", None)
    # Drop any live client the earlier tests may have cached.
    monkeypatch.setattr(redis_infra, "_client", None)
    assert check_rate_limit("rl:test:fallback", 1, 60) == (True, 0)


def _stub_app(limit: int) -> TestClient:
    stub = FastAPI()

    @stub.get("/api/v1/analytics/matrix")
    def heavy():
        return JSONResponse({"ok": True})

    @stub.get("/health")
    def health():
        return JSONResponse({"ok": True})

    stub.add_middleware(RateLimitMiddleware, limit_per_minute=limit)
    return TestClient(stub, raise_server_exceptions=False)


def test_middleware_429_on_heavy_path_with_contract_body():
    reset_local_buckets()
    client = _stub_app(limit=1)
    assert client.get("/api/v1/analytics/matrix").status_code == 200
    r = client.get("/api/v1/analytics/matrix")
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in r.headers
    assert r.headers["X-Request-ID"]


def test_middleware_leaves_cheap_paths_alone():
    reset_local_buckets()
    client = _stub_app(limit=1)
    for _ in range(3):
        assert client.get("/health").status_code == 200


def test_rate_limited_paths_cover_heavy_endpoints():
    assert "/api/v1/catalog/overview" in RATE_LIMITED_PATHS
    assert "/api/v1/analytics/matrix" in RATE_LIMITED_PATHS
