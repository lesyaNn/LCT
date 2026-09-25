"""P5 auth/error contract tests without a database or external Keycloak."""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt

import app.core.security as sec
from app.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import request_log_middleware
from app.core.permissions import require_role
from app.schemas.errors import ERROR_HTTP_STATUS, ErrorCode, ErrorResponse

ROOT = Path(__file__).resolve().parents[2]


def _b64(num: int) -> str:
    return base64.urlsafe_b64encode(num.to_bytes((num.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()


@pytest.fixture()
def auth_fixture(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    pub = key.public_key().public_numbers()
    jwks = {"keys": [{"kid": "old", "kty": "RSA", "alg": "RS256", "use": "sig",
                      "n": _b64(pub.n), "e": _b64(pub.e)}]}
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: jwks)
    sec._jwks_cache.update(keys=[], fetched_at=0.0)
    monkeypatch.setattr(settings, "auth_dev_bypass", False)
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "keycloak_issuer", "http://localhost:8081/realms/rtk")
    monkeypatch.setattr(settings, "keycloak_audience", "rtk-api")

    api = FastAPI()
    register_error_handlers(api)
    api.middleware("http")(request_log_middleware)

    @api.get("/me", response_model=dict, responses={401: {"model": ErrorResponse}})
    def me(user: sec.CurrentUser = Depends(sec.get_current_user)):
        return {"id": user.id, "roles": sorted(user.roles), "email": user.email}

    @api.get("/admin", responses={403: {"model": ErrorResponse}})
    def admin(user: sec.CurrentUser = Depends(require_role("admin"))):
        return {"id": user.id}

    @api.get("/scoped")
    def scoped():
        raise HTTPException(status_code=403, detail="internal university 99")

    with TestClient(api) as client:
        yield client, priv, jwks


def mint(priv, *, roles=("user",), kid="old", iss=None, aud=None, minutes=5,
         exp=True, email=True):
    now = datetime.now(timezone.utc)
    claims = {"sub": "person-1", "preferred_username": "person", "name": "Person",
              "realm_access": {"roles": list(roles) + ["offline_access"]},
              "iss": iss or settings.keycloak_issuer,
              "aud": settings.keycloak_audience if aud is None else aud,
              "iat": now}
    if exp:
        claims["exp"] = now + timedelta(minutes=minutes)
    if email:
        claims["email"] = "person@example.local"
    return jwt.encode(claims, priv, algorithm="RS256", headers={"kid": kid})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == code
    assert body.error.details == {}
    assert str(UUID(response.headers["X-Request-ID"])) == str(body.error.request_id)
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"
    return response.json()


def test_valid_roles_audience_list_and_optional_email(auth_fixture):
    client, priv, _ = auth_fixture
    response = client.get("/me", headers=bearer(mint(priv, roles=("manager", "curator"),
                                                     aud=["other", "rtk-api"], email=False)))
    assert response.status_code == 200, response.text
    assert response.json() == {"id": "person-1", "roles": ["curator", "manager"], "email": None}
    assert client.get("/admin", headers=bearer(mint(priv, roles=("admin",)))).status_code == 200


def test_unknown_roles_are_ignored_and_logged(auth_fixture, caplog):
    client, priv, _ = auth_fixture
    with caplog.at_level("WARNING", logger="rtk.security"):
        response = client.get(
            "/me", headers=bearer(mint(priv, roles=("user", "surprise-role")))
        )
    assert response.status_code == 200
    assert response.json()["roles"] == ["user"]
    assert "surprise-role" in caplog.text


def test_missing_token_and_403_contract(auth_fixture):
    client, priv, _ = auth_fixture
    assert_error(client.get("/me"), 401, ErrorCode.AUTH_REQUIRED)
    response = client.get("/admin", headers=bearer(mint(priv)))
    body = assert_error(response, 403, ErrorCode.FORBIDDEN)
    assert body["error"]["message"] == "У вас нет прав для выполнения этого действия."
    assert "WWW-Authenticate" not in response.headers
    scoped = client.get("/scoped")
    assert_error(scoped, 403, ErrorCode.FORBIDDEN)
    assert "university 99" not in scoped.text


def test_request_id_reuse_and_invalid_incoming_id(auth_fixture):
    client, _, _ = auth_fixture
    request_id = "95d30fb7-64ad-45da-ab3c-675eaeeb66e1"
    response = client.get("/me", headers={"X-Request-ID": request_id})
    assert_error(response, 401, ErrorCode.AUTH_REQUIRED)
    assert response.headers["X-Request-ID"] == request_id
    response = client.get("/me", headers={"X-Request-ID": "not-a-uuid"})
    assert_error(response, 401, ErrorCode.AUTH_REQUIRED)
    assert response.headers["X-Request-ID"] != "not-a-uuid"


@pytest.mark.parametrize("change,code", [
    ({"minutes": -5}, ErrorCode.TOKEN_EXPIRED),
    ({"iss": "http://wrong/realms/rtk"}, ErrorCode.TOKEN_INVALID),
    ({"aud": "wrong"}, ErrorCode.TOKEN_INVALID),
    ({"aud": []}, ErrorCode.TOKEN_INVALID),
    ({"exp": False}, ErrorCode.TOKEN_INVALID),
    ({"kid": "missing"}, ErrorCode.TOKEN_INVALID),
])
def test_invalid_claims_are_sanitized(auth_fixture, change, code):
    client, priv, _ = auth_fixture
    response = client.get("/me", headers=bearer(mint(priv, **change)))
    body = assert_error(response, 401, code)
    assert "wrong" not in json.dumps(body)
    assert "missing" not in json.dumps(body)


def test_bad_signature_malformed_and_unsupported_alg(auth_fixture):
    client, priv, _ = auth_fixture
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_priv = other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
    unknown_header = base64.urlsafe_b64encode(
        b'{"alg":"unknown","kid":"old"}'
    ).rstrip(b"=").decode()
    for token in (mint(other_priv), "garbage", jwt.encode({"sub": "x"}, "secret",
                                                        algorithm="HS256", headers={"kid": "old"}),
                  "eyJhbGciOiJub25lIiwia2lkIjoib2xkIn0.e30.",
                  f"{unknown_header}.e30.signature"):
        assert_error(client.get("/me", headers=bearer(token)), 401, ErrorCode.TOKEN_INVALID)


def test_jwks_cache_ttl_rotation_and_failure(auth_fixture, monkeypatch):
    client, priv, old_doc = auth_fixture
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_priv = new_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()
    new_pub = new_key.public_key().public_numbers()
    new_doc = {"keys": [old_doc["keys"][0], {"kid": "new", "kty": "RSA", "alg": "RS256",
                                            "n": _b64(new_pub.n), "e": _b64(new_pub.e)}]}
    calls = []
    docs = [old_doc, new_doc]

    def fetch():
        calls.append(1)
        return docs.pop(0) if docs else new_doc

    monkeypatch.setattr(sec, "_fetch_jwks", fetch)
    monkeypatch.setattr(sec.time, "time", lambda: 1000.0)
    assert client.get("/me", headers=bearer(mint(priv))).status_code == 200
    assert client.get("/me", headers=bearer(mint(priv))).status_code == 200
    assert len(calls) == 1
    assert client.get("/me", headers=bearer(mint(new_priv, kid="new"))).status_code == 200
    assert len(calls) == 2
    assert len(sec._jwks_cache["keys"]) == 2
    monkeypatch.setattr(sec.time, "time", lambda: 1000.0 + sec.JWKS_TTL_SECONDS + 1)
    assert client.get("/me", headers=bearer(mint(priv))).status_code == 200
    assert len(calls) == 3

    unknown = client.get("/me", headers=bearer(mint(priv, kid="unknown")))
    assert_error(unknown, 401, ErrorCode.TOKEN_INVALID)
    assert len(calls) == 4

    def failed_fetch():
        raise OSError("private jwks host and credentials")

    monkeypatch.setattr(sec, "_fetch_jwks", failed_fetch)
    unavailable = client.get("/me", headers=bearer(mint(priv, kid="unknown")))
    assert_error(unavailable, 503, ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
    assert "private jwks host" not in unavailable.text
    assert len(sec._jwks_cache["keys"]) == 2


def test_malformed_jwks_and_dev_bypass(auth_fixture, monkeypatch):
    client, priv, _ = auth_fixture
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: {"keys": "not a list"})
    assert_error(client.get("/me", headers=bearer(mint(priv))),
                 503, ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
    sec._jwks_cache.update(keys=[], fetched_at=0.0)
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: {"keys": [
        {"kid": "old", "kty": "RSA", "alg": "RS256", "use": "sig"}
    ]})
    assert_error(client.get("/me", headers=bearer(mint(priv))),
                 503, ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
    monkeypatch.setattr(settings, "auth_dev_bypass", True)
    assert client.get("/me").status_code == 200
    monkeypatch.setattr(settings, "app_env", "production")
    assert_error(client.get("/me"), 401, ErrorCode.AUTH_REQUIRED)


def test_registry_matches_frozen_document_and_openapi(auth_fixture):
    client, _, _ = auth_fixture
    document = json.loads((ROOT / "docs/contracts/security-errors.json").read_text(encoding="utf-8"))
    assert document["http_status"] == {code.value: status for code, status in ERROR_HTTP_STATUS.items()}
    spec = client.get("/openapi.json").json()
    assert "ErrorResponse" in spec["components"]["schemas"]
    assert spec["paths"]["/me"]["get"]["security"]


def test_demo_users_and_keycloak_audience_static():
    realm = json.loads((ROOT / "keycloak/realm-export.json").read_text(encoding="utf-8"))
    assert realm["realm"] == "rtk"
    assert realm["defaultSignatureAlgorithm"] == "RS256"
    role_names = {role["name"] for role in realm["roles"]["realm"]}
    users = {user["username"]: user for user in realm["users"]}
    for role in ("admin", "manager", "user"):
        assert role in role_names
        assert users[role]["enabled"] is True
        assert role in users[role]["realmRoles"]
    assert "curator" in role_names
    assert any(client["clientId"] == "rtk-frontend" and client["enabled"]
               for client in realm["clients"])
    audience_mappers = [mapper for scope in realm["clientScopes"]
                        for mapper in scope.get("protocolMappers", [])
                        if mapper.get("protocolMapper") == "oidc-audience-mapper"]
    assert any(mapper["config"].get("included.client.audience") == "rtk-api"
               for mapper in audience_mappers)
