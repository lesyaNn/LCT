"""The integration contract must describe mounted routes and actual role gates."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import TypeAdapter

from app.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.modules.catalog.schemas import UniversityDetail
from app.modules.analytics.report_service import ReportQueuedResponse
from app.modules.service_api.examples import REQUEST_EXAMPLES
from app.modules.service_api.service import api_routes
from app.schemas.errors import ErrorResponse
from tests.test_auth import keypair  # noqa: F401 (shared RSA/JWKS fixture)


@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setattr(settings, "auth_dev_bypass", False)
    previous = app.dependency_overrides.copy()
    actor = {"user": CurrentUser(id="integration-test", roles={"user"})}

    def no_database():
        raise AssertionError("API documentation must not query or mutate CRM data")

    app.dependency_overrides[get_db] = no_database
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    try:
        with TestClient(app) as client:
            yield client, actor
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize("path", ["/api/v1/service-api", "/api/v1/openapi.json"])
def test_authentication_required(context, path):
    client, _ = context
    app.dependency_overrides.pop(get_current_user)
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("role", ["user", "manager", "admin"])
def test_catalog_for_each_role(context, role):
    client, actor = context
    actor["user"] = CurrentUser(id=f"test-{role}", roles={role})
    response = client.get("/api/v1/service-api")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"
    catalog = response.json()
    assert catalog["role"] == role
    assert catalog["version"] == app.version
    assert catalog["operation_count"] == len(catalog["operations"])
    expected = {(method, route.path_format) for route, method in api_routes(app)}
    actual = {(item["method"], item["path"]) for item in catalog["operations"]}
    assert actual == expected
    assert len(actual) == len(catalog["operations"])
    assert all(item["summary"] and item["tags"] for item in catalog["operations"])
    assert not any("tender" in item["path"] for item in catalog["operations"])
    auth = catalog["authentication"]
    assert auth["audience"] == settings.keycloak_audience
    assert auth["issuer"] == settings.keycloak_issuer.rstrip("/")
    assert auth["service_account_setup_required"] is True
    assert "secret" not in json.dumps(auth).lower()


@pytest.mark.parametrize("path", ["/api/v1/service-api", "/api/v1/openapi.json"])
def test_unknown_role_denied(context, path):
    client, actor = context
    actor["user"] = CurrentUser(id="unknown", roles={"curator"})
    response = client.get(path)
    assert response.status_code == 403


def test_role_matrix_matches_current_routes(context):
    client, actor = context
    expected = {
        ("POST", "/api/v1/universities"): {"admin"},
        ("GET", "/api/v1/universities"): {"admin", "manager", "user"},
        ("PATCH", "/api/v1/universities/{university_id}"): {"admin"},
        ("DELETE", "/api/v1/universities/{university_id}"): {"admin"},
        ("GET", "/api/v1/admin/users"): {"admin", "manager"},
        ("POST", "/api/v1/programs"): {"admin"},
        ("POST", "/api/v1/import/upload"): {"admin"},
        ("POST", "/api/v1/universities/{university_id}/programs"): {"admin", "manager"},
        ("POST", "/api/v1/assistant/chat"): {"admin", "manager", "user"},
    }
    for role in ("user", "manager", "admin"):
        actor["user"] = CurrentUser(id="same-user", roles={role})
        operations = client.get("/api/v1/service-api").json()["operations"]
        by_key = {(op["method"], op["path"]): op for op in operations}
        for key, allowed in expected.items():
            assert set(by_key[key]["allowed_roles"]) == allowed, key
            assert by_key[key]["role_allowed"] is (role in allowed), key
        create = by_key[("POST", "/api/v1/universities")]
        assert create["required_permissions"] == ["catalog.manage"]


def test_schema_alias_is_canonical_and_has_no_user_data(context):
    client, actor = context
    first = client.get("/api/v1/openapi.json")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store, max-age=0"
    assert first.json() == client.get("/openapi.json").json()
    actor["user"] = CurrentUser(id="different-admin", roles={"admin"})
    assert client.get("/api/v1/openapi.json").json() == first.json()
    assert "integration-test" not in first.text
    assert "different-admin" not in first.text
    assert all(
        "role_allowed" not in operation
        for item in first.json()["paths"].values()
        for method, operation in item.items()
        if method in {"get", "post", "patch", "put", "delete"}
    )
    operation = first.json()["paths"]["/api/v1/universities"]["post"]
    assert operation["x-required-permissions"] == ["catalog.manage"]
    assert operation["x-allowed-roles"] == ["admin"]


def test_catalog_does_not_leak_previous_callers_access(context):
    client, actor = context
    actor["user"] = CurrentUser(id="admin-test", roles={"admin"})
    admin = client.get("/api/v1/service-api").json()
    actor["user"] = CurrentUser(id="reader-test", roles={"user"})
    reader = client.get("/api/v1/service-api").json()
    assert admin["role"] == "admin" and reader["role"] == "user"
    assert any(
        a["role_allowed"] != b["role_allowed"]
        for a, b in zip(admin["operations"], reader["operations"], strict=True)
    )


def test_public_license_verification_keeps_its_explicit_anonymous_contract(context):
    client, _ = context
    catalog = client.get("/api/v1/service-api").json()
    public_path = "/api/v1/public/licenses/{license_id}/verification"
    public = next(op for op in catalog["operations"] if op["path"] == public_path)
    assert public["authentication_required"] is False
    assert public["role_allowed"] is True
    assert public["allowed_roles"] == []
    assert public["required_permissions"] == []
    schema = client.get("/api/v1/openapi.json").json()
    assert not schema["paths"][public_path]["get"].get("security")
    protected_path = "/api/v1/universities/{university_id}/licenses/{license_id}/passport.pdf"
    protected = schema["paths"][protected_path]["get"]
    assert protected["security"] == [{"HTTPBearer": []}, {"KeycloakLogin": []}]
    assert protected["x-authentication-required"] is True


@pytest.mark.parametrize(
    "audience,roles,expected",
    [
        ("rtk-api", ["manager"], 200),
        ("another-service", ["admin"], 401),
        ("rtk-api", ["unregistered-role"], 403),
    ],
)
def test_signed_service_account_tokens(context, request, monkeypatch, audience, roles, expected):
    import time
    import app.core.security as security

    client, _ = context
    private_key, jwks = request.getfixturevalue("keypair")
    app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(settings, "keycloak_audience", "rtk-api")
    monkeypatch.setattr(security, "_get_jwks", lambda **kwargs: jwks)
    token = jwt.encode(
        {
            "sub": "service-account-test",
            "preferred_username": "service-account-crm-integration",
            "iss": settings.keycloak_issuer,
            "aud": audience,
            "exp": int(time.time()) + 300,
            "realm_access": {"roles": roles},
            "university_ids": ["11111111-1111-4111-8111-111111111111"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": jwks["keys"][0]["kid"]},
    )
    response = client.get("/api/v1/service-api", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.json()["role"] == "manager"
        assert security.validate_token(token).university_ids == (
            "11111111-1111-4111-8111-111111111111",
        )


@pytest.mark.parametrize("key,example", list(REQUEST_EXAMPLES.items()))
def test_request_examples_match_real_route_models(key, example):
    path, method = key
    route = next(
        route for route, verb in api_routes(app) if (route.path_format, verb.lower()) == key
    )
    adapter = TypeAdapter(route.body_field.type_)
    validated = adapter.validate_python(example)
    assert set(example) <= set(type(validated).model_fields)
    body = app.openapi()["paths"][path][method]["requestBody"]["content"]["application/json"]
    assert body["example"] == example


def test_published_guide_examples_and_style():
    guide = Path(__file__).resolve().parents[2] / "frontend/public/docs/api/integration.md"
    text = guide.read_text(encoding="utf-8")
    assert not set("—–«»") & set(text)
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.S)
    routes = {(route.path_format, method.lower()): route for route, method in api_routes(app)}
    models = [UniversityDetail]
    for key in (
        ("/api/v1/programs", "post"),
        ("/api/v1/universities/{university_id}/programs", "post"),
        ("/api/v1/contracts", "post"),
        ("/api/v1/licenses", "post"),
        ("/api/v1/universities/{university_id}/meetings", "post"),
        ("/api/v1/workflow/instances", "post"),
        ("/api/v1/reports", "post"),
    ):
        models.append(routes[key].body_field.type_)
    models += [
        ReportQueuedResponse,
        routes[("/api/v1/integrations/lms/ingest", "post")].body_field.type_,
        routes[("/api/v1/assistant/chat", "post")].body_field.type_,
        ErrorResponse,
    ]
    assert len(blocks) == len(models)
    for block, model in zip(blocks, models, strict=True):
        TypeAdapter(model).validate_json(block)
