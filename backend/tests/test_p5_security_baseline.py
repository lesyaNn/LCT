"""Database-independent P5-13 security baseline checks."""

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging import SensitiveFilter
from app.core.middleware import SecurityHeadersMiddleware
from app.main import app
from app.core.middleware import REQUEST_BODY_LIMIT_BYTES
from app.modules.catalog.repository import like_pattern


client = TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/health", "/ready", "/docs", "/redoc", "/openapi.json", "/missing"])
def test_security_headers_are_present_on_success_and_http_errors(path):
    response = client.get(path)
    assert response.status_code in {200, 404}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "geolocation=(), microphone=(), camera=()"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_security_headers_are_present_on_auth_error():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"]


def test_security_headers_are_present_on_unhandled_500():
    probe = FastAPI()
    register_error_handlers(probe)
    probe.add_middleware(SecurityHeadersMiddleware)

    @probe.get("/boom")
    def boom():
        raise RuntimeError("internal test failure")

    response = TestClient(probe, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"]


def test_cors_allowlist_and_preflight():
    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, X-Request-ID",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Authorization" in allowed.headers["access-control-allow-headers"]
    assert "X-Request-ID" in allowed.headers["access-control-allow-headers"]

    denied = client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_request_content_length_limit_returns_unified_413():
    response = client.post(
        "/health",
        content=b"x",
        headers={"Content-Length": str(REQUEST_BODY_LIMIT_BYTES + 1)},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_sensitive_log_filter_removes_authorization_bearer_token():
    record = logging.LogRecord(
        "security-test", logging.INFO, __file__, 1,
        "Authorization: Bearer eyJ.test.signature password=secret123", (), None,
    )
    assert SensitiveFilter().filter(record)
    message = record.getMessage()
    assert "eyJ.test.signature" not in message
    assert "secret123" not in message
    assert "[REDACTED]" in message


def test_sensitive_log_filter_redacts_exception_traceback():
    try:
        raise RuntimeError("export failed password=hunter2 token: abc123")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "security-test", logging.ERROR, __file__, 1,
        "report worker failed", (), exc_info,
    )
    assert SensitiveFilter().filter(record)
    rendered = logging.Formatter().format(record)
    assert "RuntimeError" in rendered
    assert "hunter2" not in rendered
    assert "abc123" not in rendered
    assert "[REDACTED]" in rendered


def test_production_settings_fail_closed_for_wildcard_and_missing_s3_secret():
    with pytest.raises(ValueError):
        Settings(app_env="production", cors_origins="*")
    with pytest.raises(ValueError):
        Settings(app_env="production", storage_backend="s3", cors_origins="https://crm.example")


def test_dependency_manifest_is_exactly_pinned_and_no_unsafe_fallback():
    root = Path(__file__).resolve().parents[1]
    manifest = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'fastapi==' in manifest
    assert 'sqlalchemy==' in manifest
    assert 'python-jose[cryptography]==' in manifest
    assert 's3_secret_key: str = "minioadmin"' not in (
        root / "app" / "config.py"
    ).read_text(encoding="utf-8")


def test_search_payload_is_bound_as_data_and_not_sql():
    payload = "'; DROP TABLE universities; --"
    pattern = like_pattern(payload)
    assert pattern.startswith("%") and pattern.endswith("%")
    assert "\\%" not in pattern
    assert "\\_" not in pattern
    assert "DROP TABLE" in pattern
