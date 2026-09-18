"""P5-11-01: Swagger/OpenAPI contract checks.

Locks: professional title/version, BearerAuth scheme (contract name),
per-operation summaries + tags, documented error responses, valid
/api/v1 versioning, and that /docs is served.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _spec() -> dict:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


def test_title_and_version():
    spec = _spec()
    assert spec["info"]["title"] == "CRM ИТ-Школа Ростелеком API"
    assert spec["info"]["version"] == "1.0.0"
    assert spec["info"]["description"]


def test_bearer_auth_scheme():
    spec = _spec()
    schemes = spec["components"]["securitySchemes"]
    assert "BearerAuth" in schemes, schemes
    assert "HTTPBearer" not in schemes
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schemes["BearerAuth"]["bearerFormat"] == "JWT"


def test_all_operations_have_summary_and_tags():
    spec = _spec()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            assert op.get("summary"), (method, path)
            assert op.get("tags"), (method, path)


def test_protected_operations_reference_bearer_auth():
    spec = _spec()
    protected = ["/api/v1/import/preview", "/api/v1/import/execute",
                 "/api/v1/auth/me"]
    for path in protected:
        ops = spec["paths"][path]
        op = next(iter(ops.values()))
        assert {"BearerAuth": []} in op.get("security", []), path


def test_error_responses_documented():
    spec = _spec()
    preview = spec["paths"]["/api/v1/import/preview"]["post"]["responses"]
    assert {"200", "400", "401", "422"} <= set(preview), preview
    assert "ErrorResponse" in spec["components"]["schemas"], (
        sorted(spec["components"]["schemas"])
    )


def test_versioned_prefix_everywhere():
    spec = _spec()
    api_paths = [p for p in spec["paths"] if not p.startswith("/health")
                 and p != "/ready"]
    assert api_paths
    assert all(p.startswith("/api/v1/") for p in api_paths), api_paths


def test_docs_and_redoc_served():
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
