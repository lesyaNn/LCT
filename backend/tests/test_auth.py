"""Auth tests — no real Keycloak required.

A local RSA key pair stands in for Keycloak: the public part is served
through a monkeypatched JWKS fetch, tokens are minted locally.
"""
import base64
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jose import jwt

import app.core.security as sec
from app.config import settings
from app.main import app

KID = "test-key-1"


def _b64url(num: int) -> str:
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_numbers()
    jwks = {"keys": [{"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256",
                      "n": _b64url(pub.n), "e": _b64url(pub.e)}]}
    return priv, jwks


@pytest.fixture()
def client(keypair, monkeypatch):
    priv, jwks = keypair
    settings.auth_dev_bypass = False
    settings.keycloak_issuer = "http://localhost:8081/realms/rtk"
    settings.keycloak_audience = "rtk-api"
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: jwks)
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
    with TestClient(app) as c:
        c._priv = priv
        yield c


def mint(client, roles=("user",), minutes=5, iss=None, aud=None, kid=KID, key=None):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "preferred_username": roles[0],
        "email": f"{roles[0]}@example.local",
        "name": f"Demo {roles[0].title()}",
        "realm_access": {"roles": list(roles)},
        "iss": iss or settings.keycloak_issuer,
        "aud": aud or settings.keycloak_audience,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, key or client._priv, algorithm="RS256",
                      headers={"kid": kid})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_me_without_token_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_valid_admin(client):
    r = client.get("/api/v1/auth/me", headers=auth(mint(client, ("admin",))))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "admin"
    assert body["email"] == "admin@example.local"
    assert body["roles"] == ["admin"]
    assert body["permissions"] == ["*"]
    assert body["id"]


def test_me_curator_permissions(client):
    r = client.get("/api/v1/auth/me", headers=auth(mint(client, ("curator",))))
    assert r.status_code == 200
    assert r.json()["permissions"] == [
        "university.edit", "university.read", "workflow.change_status", "workflow.read",
    ]


def test_expired_is_401(client):
    assert client.get("/api/v1/auth/me",
                      headers=auth(mint(client, minutes=-5))).status_code == 401


def test_wrong_issuer_is_401(client):
    t = mint(client, iss="http://evil/realms/rtk")
    assert client.get("/api/v1/auth/me", headers=auth(t)).status_code == 401


def test_wrong_audience_is_401(client):
    t = mint(client, aud="someone-else")
    assert client.get("/api/v1/auth/me", headers=auth(t)).status_code == 401


def test_missing_audience_is_401(client):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "preferred_username": "user",
        "realm_access": {"roles": ["user"]},
        "iss": settings.keycloak_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    t = jwt.encode(claims, client._priv, algorithm="RS256", headers={"kid": KID})
    assert client.get("/api/v1/auth/me", headers=auth(t)).status_code == 401


def test_bad_signature_is_401(client, keypair):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_priv = other.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()
    t = mint(client, key=other_priv)  # signed by unknown key, same kid
    assert client.get("/api/v1/auth/me", headers=auth(t)).status_code == 401


def test_unknown_kid_is_401(client):
    t = mint(client, kid="no-such-key")
    assert client.get("/api/v1/auth/me", headers=auth(t)).status_code == 401


def test_authenticated_endpoint(client):
    assert client.get("/api/v1/auth/test/authenticated").status_code == 401
    r = client.get("/api/v1/auth/test/authenticated",
                   headers=auth(mint(client, ("user",))))
    assert r.status_code == 200


def test_admin_endpoint_rbac(client):
    assert client.get("/api/v1/auth/test/admin",
                      headers=auth(mint(client, ("user",)))).status_code == 403
    assert client.get("/api/v1/auth/test/admin",
                      headers=auth(mint(client, ("manager",)))).status_code == 403
    assert client.get("/api/v1/auth/test/admin",
                      headers=auth(mint(client, ("admin",)))).status_code == 200


def test_workflow_change_permission(client):
    ok = client.get("/api/v1/auth/test/workflow-change",
                    headers=auth(mint(client, ("curator",))))
    assert ok.status_code == 200
    denied = client.get("/api/v1/auth/test/workflow-change",
                        headers=auth(mint(client, ("user",))))
    assert denied.status_code == 403
    denied_mgr = client.get("/api/v1/auth/test/workflow-change",
                            headers=auth(mint(client, ("manager",))))
    assert denied_mgr.status_code == 403
