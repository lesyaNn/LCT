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
            assert op.get("description"), (method, path)
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
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "SwaggerUIBundle" in docs.text
    assert "cdn.jsdelivr.net" in docs.text
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    redoc = client.get("/redoc")
    assert redoc.status_code == 200
    assert "redoc.standalone.js" in redoc.text


def test_all_business_operations_are_documented_and_secure():
    spec = _spec()
    ids = []
    business = 0
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            ids.append(operation["operationId"])
            if path in {"/health", "/ready"}:
                assert not operation.get("security")
                continue
            assert path.startswith("/api/v1/"), (method, path)
            business += 1
            assert operation["summary"].strip()
            assert operation["description"].strip()
            assert operation["tags"]
            assert {"BearerAuth": []} in operation.get("security", [])
            for code in ("401", "403", "422"):
                response = operation["responses"][code]
                assert response["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ErrorResponse"
                }
    assert business == 85
    assert len(ids) == len(set(ids))


def test_all_openapi_refs_resolve():
    spec = _spec()

    def walk(value):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref:
                assert ref.startswith("#/"), ref
                target = spec
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                assert target
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spec)
    assert "ErrorResponse" in spec["components"]["schemas"]
    assert "BearerAuth" in spec["components"]["securitySchemes"]


def test_representative_examples():
    spec = _spec()
    for path, method in (
        ("/api/v1/universities", "post"),
        ("/api/v1/universities/{university_id}", "patch"),
        ("/api/v1/workflow/instances/{instance_id}/transition", "post"),
    ):
        body = spec["paths"][path][method]["requestBody"]["content"]["application/json"]
        assert body["example"]
    assert spec["components"]["schemas"]["ReportRequest"].get("example")
    assert spec["components"]["schemas"]["ErrorResponse"].get("examples")
