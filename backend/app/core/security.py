"""Auth: real Keycloak JWT validation (RS256 via JWKS).

Flow: React -> Keycloak -> JWT -> FastAPI verifies signature/exp/iss/aud.

Fail closed: if Keycloak/JWKS is unreachable, requests fail —
we NEVER fall back to trusting the payload. The only exception is the
explicit opt-in AUTH_DEV_BYPASS (used by unit tests, never in compose).
"""
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False, description="Keycloak JWT (rtk-frontend)")

JWKS_TTL_SECONDS = 600

# Realm roles of the rtk realm (§8). Technical roles (offline_access,
# uma_authorization, ...) are ignored so /auth/me matches the spec.
KNOWN_ROLES = {"admin", "manager", "curator", "user"}

_jwks_cache: dict[str, Any] = {"keys": [], "fetched_at": 0.0}


@dataclass
class CurrentUser:
    """Internal user model. `id` is the Keycloak `sub`.

    When PostgreSQL arrives, this `sub` maps to users.external_id
    (users.keycloak_id) — auth code will not need a rewrite.

    ``university_ids`` is an OPTIONAL additive scope claim (``university_ids``
    list or single ``university_id`` string in the JWT). P2-05 workflow file
    storage enforces it when present (cross-university isolation); tokens
    without it keep the pre-existing global RBAC behaviour. ``None`` = all.
    """

    id: str = ""
    username: str | None = None
    email: str | None = None
    name: str | None = None
    roles: set[str] = field(default_factory=set)
    university_ids: tuple[str, ...] | None = None


def _fetch_jwks() -> dict:
    """Network fetch of the JWKS document (indirection point for tests)."""
    req = urllib.request.Request(settings.keycloak_jwks_url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_jwks(force_refresh: bool = False) -> dict:
    now = time.time()
    if (not force_refresh and _jwks_cache["keys"]
            and now - _jwks_cache["fetched_at"] < JWKS_TTL_SECONDS):
        return {"keys": _jwks_cache["keys"]}
    try:
        doc = _fetch_jwks()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"JWKS unavailable: {exc}")
    _jwks_cache["keys"] = doc.get("keys", [])
    _jwks_cache["fetched_at"] = now
    return doc


def _key_for_kid(kid: str) -> dict:
    doc = _get_jwks()
    for key in doc.get("keys", []):
        if key.get("kid") == kid:
            return key
    # Unknown kid: keys may have rotated — refresh once, then fail closed.
    doc = _get_jwks(force_refresh=True)
    for key in doc.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(status_code=401, detail="Unknown token key (kid)")


def validate_token(token: str) -> CurrentUser:
    """Full validation: signature (kid/JWKS) + exp + iss + aud. Never skips."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Malformed token")
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token has no kid")
    key = _key_for_kid(kid)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTClaimsError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid claims: {exc}")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid signature")
    # python-jose skips audience validation when the claim is absent —
    # require it explicitly (fail closed).
    aud = claims.get("aud")
    auds = [aud] if isinstance(aud, str) else list(aud or [])
    if settings.keycloak_audience not in auds:
        raise HTTPException(status_code=401, detail="Invalid audience")
    roles = set((claims.get("realm_access") or {}).get("roles", [])) & KNOWN_ROLES
    scope: tuple[str, ...] | None = None
    raw_scope = claims.get("university_ids", claims.get("university_id"))
    if isinstance(raw_scope, str) and raw_scope:
        scope = (raw_scope,)
    elif isinstance(raw_scope, (list, tuple)):
        scope = tuple(str(v) for v in raw_scope if str(v)) or None
    return CurrentUser(
        id=claims.get("sub", ""),
        username=claims.get("preferred_username"),
        email=claims.get("email"),
        name=claims.get("name"),
        roles=roles,
        university_ids=scope,
    )


def _dev_user() -> CurrentUser:
    return CurrentUser(id="dev-admin", username="admin",
                       email="admin@example.local", name="Demo Admin",
                       roles={"admin"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        if settings.auth_dev_bypass:
            return _dev_user()
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return validate_token(credentials.credentials)


require_user = Depends(get_current_user)
