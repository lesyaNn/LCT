"""Auth: real Keycloak JWT validation (RS256 via JWKS).

Flow: React -> Keycloak -> JWT -> FastAPI verifies signature/exp/iss/aud.

Fail closed: if Keycloak/JWKS is unreachable, requests fail —
we NEVER fall back to trusting the payload. The only exception is the
explicit opt-in AUTH_DEV_BYPASS (used by unit tests, never in compose).
"""
import json
import logging
import re
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JOSEError, JWKError

from app.config import DEV_BYPASS_ENVIRONMENTS, settings
from app.core.errors import SecurityError
from app.schemas.errors import ErrorCode

bearer_scheme = HTTPBearer(auto_error=False, description="Keycloak JWT (rtk-frontend)")

JWKS_TTL_SECONDS = 600

# Realm roles of the rtk realm (§8). Technical roles (offline_access,
# uma_authorization, ...) are ignored so /auth/me matches the spec.
KNOWN_ROLES = {"admin", "manager", "curator", "user"}
IGNORED_TECHNICAL_ROLES = {"offline_access", "uma_authorization", "default-roles-rtk"}

logger = logging.getLogger("rtk.security")

_jwks_cache: dict[str, Any] = {"keys": [], "fetched_at": 0.0}
# M7: sync auth dependencies run in a threadpool — guard the shared JWKS
# cache so two concurrent refreshes cannot interleave a partial write.
_jwks_lock = threading.Lock()


def _safe_role_for_log(value: str) -> str:
    """Bound attacker-controlled role text before it reaches the log record."""
    return re.sub(r"[^A-Za-z0-9_.:@/-]", "?", value)[:64]


@dataclass
class CurrentUser:
    """Internal user model. `id` is the Keycloak `sub`.

    When PostgreSQL arrives, this `sub` maps to users.external_id
    (users.keycloak_id) — auth code will not need a rewrite.

    ``university_ids`` is an explicit assignment claim. Missing and empty
    claims are zero scope for non-admin roles; admin alone has implicit ALL.
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
    # Fast path without the lock; refresh path serializes on _jwks_lock and
    # re-checks freshness inside (another thread may have refreshed already).
    now = time.time()
    if (not force_refresh and _jwks_cache["keys"]
            and now - _jwks_cache["fetched_at"] < JWKS_TTL_SECONDS):
        return {"keys": _jwks_cache["keys"]}
    with _jwks_lock:
        now = time.time()
        if (not force_refresh and _jwks_cache["keys"]
                and now - _jwks_cache["fetched_at"] < JWKS_TTL_SECONDS):
            return {"keys": _jwks_cache["keys"]}
        try:
            doc = _fetch_jwks()
            if not isinstance(doc, dict) or not isinstance(doc.get("keys"), list):
                raise ValueError("Malformed JWKS")
            keys = doc["keys"]
            if not keys or not all(isinstance(key, dict) for key in keys):
                raise ValueError("Malformed JWKS key")
            if any(key.get("kty") == "RSA" and
                   (not isinstance(key.get("n"), str) or not isinstance(key.get("e"), str))
                   for key in keys):
                raise ValueError("Malformed RSA key")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SecurityError(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return {"keys": keys}


def _key_for_kid(kid: str) -> dict:
    doc = _get_jwks()
    for key in doc.get("keys", []):
        if (key.get("kid") == kid and key.get("kty") == "RSA"
                and key.get("alg", "RS256") == "RS256"
                and key.get("use", "sig") == "sig"):
            return key
    # Unknown kid: keys may have rotated — refresh once, then fail closed.
    doc = _get_jwks(force_refresh=True)
    for key in doc.get("keys", []):
        if (key.get("kid") == kid and key.get("kty") == "RSA"
                and key.get("alg", "RS256") == "RS256"
                and key.get("use", "sig") == "sig"):
            return key
    raise SecurityError(ErrorCode.TOKEN_INVALID)


def validate_token(token: str) -> CurrentUser:
    """Full validation: signature (kid/JWKS) + exp + iss + aud. Never skips."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise SecurityError(ErrorCode.TOKEN_INVALID) from None
    if header.get("alg") != "RS256":
        raise SecurityError(ErrorCode.TOKEN_INVALID)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise SecurityError(ErrorCode.TOKEN_INVALID)
    key = _key_for_kid(kid)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
            options={"require_exp": True},
        )
    except ExpiredSignatureError:
        raise SecurityError(ErrorCode.TOKEN_EXPIRED) from None
    except JWKError:
        raise SecurityError(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from None
    except (JOSEError, ValueError, TypeError):
        raise SecurityError(ErrorCode.TOKEN_INVALID) from None
    # python-jose skips audience validation when the claim is absent —
    # require it explicitly (fail closed).
    aud = claims.get("aud")
    auds = [aud] if isinstance(aud, str) else aud if isinstance(aud, list) else []
    if settings.keycloak_audience not in auds:
        raise SecurityError(ErrorCode.TOKEN_INVALID)
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise SecurityError(ErrorCode.TOKEN_INVALID)
    realm_access = claims.get("realm_access")
    raw_roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    role_names = {role for role in raw_roles if isinstance(role, str)} if isinstance(raw_roles, list) else set()
    unknown_roles = role_names - KNOWN_ROLES - IGNORED_TECHNICAL_ROLES
    if unknown_roles:
        logger.warning(
            "Ignoring unknown Keycloak realm roles roles=%s",
            sorted(_safe_role_for_log(role) for role in unknown_roles),
        )
    roles = role_names & KNOWN_ROLES
    scope: tuple[str, ...] | None = None
    raw_scope = claims.get("university_ids", claims.get("university_id"))
    if isinstance(raw_scope, str) and raw_scope:
        scope = (raw_scope,)
    elif isinstance(raw_scope, (list, tuple)):
        scope = tuple(str(v) for v in raw_scope if str(v))
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
        environment = settings.app_env.strip().lower()
        if settings.auth_dev_bypass and environment in DEV_BYPASS_ENVIRONMENTS:
            logger.warning("AUTH_DEV_BYPASS supplied a local development identity")
            return _dev_user()
        raise SecurityError(ErrorCode.AUTH_REQUIRED)
    return validate_token(credentials.credentials)


require_user = Depends(get_current_user)
