"""P1-04-05 passport include tests (health_score + audit blocks).

PostgreSQL integration via TEST_DATABASE_URL (canonical SQL migrations).
Reuses seed helpers
from the base passport test module (no duplication).
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
import test_university_passport as base_t
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditService
from app.modules.health_score.service import compute_score
from app.modules.universities import passport_service as ps
from app.modules.universities.passport_schemas import UniversityPassport

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    """PostgreSQL integration DB (canonical SQL migrations; skips w/o PG)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture()
def select_counter(engine):
    count = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            count["n"] += 1

    yield count
    event.remove(engine, "before_cursor_execute", _count)


@pytest.fixture()
def api_client(engine):
    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    settings.auth_dev_bypass = True
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = False


def _seed_audit(db: Session, university_id, n: int, base: datetime | None = None) -> None:
    """Create ``n`` audit events with staggered created_at (newest last)."""
    base = base or datetime.now(timezone.utc)
    for i in range(n):
        db.add(
            AuditEvent(
                user_id=str(100 + i),
                entity_type="university",
                entity_id=uuid.uuid4(),
                action=f"update-{i:02d}",
                university_id=university_id,
            )
        )
    db.flush()
    rows = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.university_id == university_id)
            .order_by(AuditEvent.id)
        )
        .scalars()
        .all()
    )
    for ev in rows:
        index = int(ev.action.rsplit("-", 1)[1])
        ev.created_at = base - timedelta(days=n - index)
    db.commit()


# ------------------------------------------------------- parse_include ---


def test_parse_include_variants():
    assert ps.parse_include(None) == frozenset()
    assert ps.parse_include("") == frozenset()
    assert ps.parse_include("   ") == frozenset()
    assert ps.parse_include("health_score") == frozenset([ps.PassportInclude.HEALTH_SCORE])
    assert ps.parse_include("audit") == frozenset([ps.PassportInclude.AUDIT])
    assert ps.parse_include("health_score,audit") == frozenset(
        [ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]
    )
    assert ps.parse_include("audit,health_score") == frozenset(
        [ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]
    )
    assert ps.parse_include(" health_score , audit ") == frozenset(
        [ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]
    )
    assert ps.parse_include("health_score,") == frozenset([ps.PassportInclude.HEALTH_SCORE])


def test_parse_include_unknown_is_422():
    from fastapi import HTTPException

    for raw in ("foobar", "health_score,foobar", "AUDIT"):
        with pytest.raises(HTTPException) as exc_info:
            ps.parse_include(raw)
        assert exc_info.value.status_code == 422


# ------------------------------------------------- compute_score guard ---


def test_compute_score_matches_legacy_formula():
    """Pure-unit guard: the extracted formula preserves the legacy scoring.

    DB-free by design (no engine fixture): persistence through
    ``HealthScoreService.calculate`` is intentionally NOT covered here —
    it depends on the legacy workflow ``tasks`` table, which is excluded
    from the canonical SQL schema (int FKs, reference to a nonexistent
    ``programs`` table), so no Python DDL path may create it.
    """
    score, details = compute_score(overdue_tasks=3, signals={"missing_license": True})
    assert score == 100 - 30 - 15 == 55
    assert details["overdue_tasks"].startswith("-30")
    capped, _ = compute_score(overdue_tasks=10)
    assert capped == 60  # 10 * 10 capped at 40
    full, _ = compute_score(
        signals={
            k: True
            for k in (
                "missing_docs",
                "stage_delay",
                "teacher_training",
                "missing_license",
                "launch_delay",
            )
        },
    )
    assert full == 100 - 15 - 10 - 10 - 15 - 15 == 35


# ------------------------------------------------------------ no include ---


def test_no_include_returns_base_and_calls_nothing(engine, api_client, monkeypatch):
    health_calls: list = []
    audit_calls: list = []
    real_health = ps.get_health_score_for_passport
    real_audit = AuditService.recent_for_university

    def _health_spy(*args, **kwargs):
        health_calls.append(args)
        return real_health(*args, **kwargs)

    def _audit_spy(self, *args, **kwargs):
        audit_calls.append(args)
        return real_audit(self, *args, **kwargs)

    monkeypatch.setattr(ps, "get_health_score_for_passport", _health_spy)
    monkeypatch.setattr(AuditService, "recent_for_university", _audit_spy)

    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["health_score"] is None
    assert body["recent_audit"] is None
    assert health_calls == []
    assert audit_calls == []
    UniversityPassport.model_validate(body)


# ---------------------------------------------------------------- health ---


def test_include_health_score(engine, api_client, monkeypatch):
    audit_calls: list = []
    real_audit = AuditService.recent_for_university

    def _audit_spy(self, *args, **kwargs):
        audit_calls.append(args)
        return real_audit(self, *args, **kwargs)

    monkeypatch.setattr(AuditService, "recent_for_university", _audit_spy)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=health_score")
    assert r.status_code == 200, r.text
    body = r.json()
    health = body["health_score"]
    assert health is not None
    assert health["university_id"] == uid
    assert isinstance(health["score"], int) and 0 <= health["score"] <= 100
    assert isinstance(health["details"], dict)
    assert body["recent_audit"] is None
    assert audit_calls == []
    UniversityPassport.model_validate(body)


def test_health_score_reflects_passport_signals(db: Session):
    from datetime import date

    _, p1, _, _, prod = base_t._catalog(db, "hs")
    u = base_t._university(db, "Uni HS")
    today = date.today()
    lic = base_t.License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=None,
        license_number="LIC-HS-EXP",
        signed_at=today - timedelta(days=100),
        expires_at=today - timedelta(days=1),
        transfer_status_raw="accepted",
    )
    db.add(lic)
    db.flush()
    db.add(
        base_t.UniversityProduct(
            university_id=u.id, product_id=prod.id, license_id=lic.id, status="active"
        )
    )
    base_t._teacher(
        db, u, "hs-exp@example.local", [{"expires_at": today - timedelta(days=2)}], [p1]
    )
    db.commit()

    passport = ps.get_passport(db, u.id, include=frozenset([ps.PassportInclude.HEALTH_SCORE]))
    assert passport.health_score is not None
    # expired license (-15) + non-ready teacher (-10), no docs penalty
    # (seed helper adds no documents here... _teacher adds none) -> docs empty
    # means missing_docs (-15) too.
    assert passport.health_score.score == 100 - 15 - 10 - 15 == 60
    assert set(passport.health_score.details) == {
        "missing_license",
        "teacher_training",
        "missing_docs",
    }
    assert passport.health_score.calculated_at.tzinfo is not None


# ----------------------------------------------------------------- audit ---


def test_include_audit_last_five_desc(engine, api_client, monkeypatch):
    health_calls: list = []
    real_health = ps.get_health_score_for_passport

    def _health_spy(*args, **kwargs):
        health_calls.append(args)
        return real_health(*args, **kwargs)

    monkeypatch.setattr(ps, "get_health_score_for_passport", _health_spy)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
        _seed_audit(s, u.id, 7)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=audit")
    assert r.status_code == 200, r.text
    body = r.json()
    events = body["recent_audit"]
    assert isinstance(events, list) and len(events) == 5
    created = [e["created_at"] for e in events]
    assert created == sorted(created, reverse=True)
    assert events[0]["action"] == "update-06"  # newest
    assert body["health_score"] is None
    assert health_calls == []
    for e in events:
        assert set(e) == {"id", "user_id", "entity_type", "entity_id", "action", "created_at"}
    UniversityPassport.model_validate(body)


def test_include_audit_empty(engine, api_client):
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=audit")
    assert r.status_code == 200, r.text
    assert r.json()["recent_audit"] == []


def test_audit_does_not_leak_other_universities(db: Session):
    u1 = base_t._university(db, "Uni A1")
    u2 = base_t._university(db, "Uni A2")
    db.commit()
    _seed_audit(db, u1.id, 2)
    _seed_audit(db, u2.id, 3)
    rows = ps.get_recent_audit(db, u1.id)
    assert len(rows) == 2
    assert all(isinstance(e.created_at, datetime) for e in rows)
    assert all(e.created_at.tzinfo is not None for e in rows)


# ------------------------------------------------------------------ both ---


@pytest.mark.parametrize(
    "query", ["health_score,audit", "audit,health_score", " health_score , audit "]
)
def test_include_both_orders(engine, api_client, query):
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
        _seed_audit(s, u.id, 2)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include={query}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["health_score"] is not None
    assert len(body["recent_audit"]) == 2
    UniversityPassport.model_validate(body)


# --------------------------------------------------------------- failures ---


def test_health_failure_degrades_to_null(engine, api_client, monkeypatch):
    def _boom(*args, **kwargs):
        raise TimeoutError("health backend down")

    monkeypatch.setattr(ps, "get_health_score_for_passport", _boom)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=health_score")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["health_score"] is None
    assert body["programs"]  # base passport intact
    assert "traceback" not in r.text


def test_audit_failure_degrades_to_empty(engine, api_client, monkeypatch):
    def _boom(self, *args, **kwargs):
        raise ConnectionError("audit store down")

    monkeypatch.setattr(AuditService, "recent_for_university", _boom)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=audit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recent_audit"] == []
    assert body["teachers"]  # base passport intact


def test_both_fail_base_still_200(engine, api_client, monkeypatch):
    monkeypatch.setattr(
        ps,
        "get_health_score_for_passport",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hs down")),
    )
    monkeypatch.setattr(
        AuditService,
        "recent_for_university",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("audit down")),
    )
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=health_score,audit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["health_score"] is None
    assert body["recent_audit"] == []
    assert body["university"]["name"] == "Uni Full Passport"


# ------------------------------------------------------------------ RBAC ---


def test_guest_with_include_gets_403(engine):
    import base64

    import app.core.security as sec
    from jose import jwt as _jwt

    def _b64url(num: int) -> str:
        raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "t405",
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(pub.n),
                "e": _b64url(pub.e),
            }
        ]
    }
    settings.auth_dev_bypass = False
    orig_issuer, orig_aud = settings.keycloak_issuer, settings.keycloak_audience
    settings.keycloak_issuer = "http://localhost:8081/realms/rtk"
    settings.keycloak_audience = "rtk-api"
    orig_fetch = sec._fetch_jwks
    sec._fetch_jwks = lambda: jwks  # noqa: E731
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    try:
        with Session(engine) as s:
            u = base_t._seed_full(s)
            uid = str(u.id)
        now = datetime.now(timezone.utc)
        token = _jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000000",
                "preferred_username": "guest",
                "realm_access": {"roles": ["guest"]},
                "iss": settings.keycloak_issuer,
                "aud": settings.keycloak_audience,
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            priv,
            algorithm="RS256",
            headers={"kid": "t405"},
        )
        with TestClient(app) as client:
            r = client.get(
                f"/api/v1/universities/{uid}/passport?include=health_score,audit",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 403, r.text
    finally:
        sec._fetch_jwks = orig_fetch
        sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
        settings.keycloak_issuer, settings.keycloak_audience = (orig_issuer, orig_aud)
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = False


# ------------------------------------------------------------- 404 / 422 ---


def test_unknown_university_with_include_404_and_no_integration_calls(
    engine, api_client, monkeypatch
):
    health_calls: list = []
    audit_calls: list = []
    real_health = ps.get_health_score_for_passport
    real_audit = AuditService.recent_for_university
    monkeypatch.setattr(
        ps,
        "get_health_score_for_passport",
        lambda *a, **k: (health_calls.append(a), real_health(*a, **k))[1],
    )
    monkeypatch.setattr(
        AuditService,
        "recent_for_university",
        lambda self, *a, **k: (audit_calls.append(a), real_audit(self, *a, **k))[1],
    )
    r = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport?include=health_score,audit")
    assert r.status_code == 404
    assert health_calls == []
    assert audit_calls == []


def test_unknown_include_422(engine, api_client, monkeypatch):
    import app.modules.universities.passport_router as router_mod

    calls: list = []
    real = router_mod.get_passport

    def _spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(router_mod, "get_passport", _spy)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=foobar")
    assert r.status_code == 422, r.text
    assert calls == []
    r2 = api_client.get(f"/api/v1/universities/{uid}/passport?include=health_score,foobar")
    assert r2.status_code == 422


# ---------------------------------------------------------- query counts ---


def test_include_query_counts(db: Session, select_counter):
    with Session(db.bind) as s:
        u = base_t._seed_full(s)
        uid = u.id
        _seed_audit(s, uid, 3)
    db.expire_all()

    select_counter["n"] = 0
    ps.get_passport(db, uid)
    base = select_counter["n"]

    db.expire_all()
    select_counter["n"] = 0
    ps.get_passport(db, uid, include=frozenset([ps.PassportInclude.HEALTH_SCORE]))
    with_health = select_counter["n"]

    db.expire_all()
    select_counter["n"] = 0
    ps.get_passport(db, uid, include=frozenset([ps.PassportInclude.AUDIT]))
    with_audit = select_counter["n"]

    db.expire_all()
    select_counter["n"] = 0
    ps.get_passport(
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]),
    )
    with_both = select_counter["n"]

    assert with_health == base, (base, with_health)  # pure compute, 0 queries
    assert with_audit == base + 1, (base, with_audit)
    assert with_both == base + 1, (base, with_both)


# ------------------------------------------------------------------ mock ---


def test_legacy_mock_still_validates():
    from pathlib import Path

    mock_path = Path(__file__).resolve().parents[2] / "docs/mocks/university-passport.json"
    mock = json.loads(mock_path.read_text(encoding="utf-8"))
    UniversityPassport.model_validate(mock)  # old JSON has no include blocks
    assert mock.get("health_score", None) is None
    assert mock.get("recent_audit", None) is None
