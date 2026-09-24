"""P1-05 teacher passport tests (PostgreSQL integration via TEST_DATABASE_URL).

Covers P1-05-01 (``GET /api/v1/teachers/{id}/passport`` mounted + OpenAPI),
P1-05-02 (qualifications / certificates + linked programs / programs with
direction) and P1-05-03 (``ready`` / ``attention`` / ``expired`` via the
canonical formula — reused, never reimplemented).

DB integration tests require PostgreSQL via ``TEST_DATABASE_URL`` pointing at
a DEDICATED test database: the fixture resets the schema (``DROP SCHEMA
public CASCADE``) and applies the canonical SQL migrations. Pure-unit tests
(OpenAPI shape) run anywhere.
"""

import base64
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProduct, ITProgram, University, Vendor
from app.models.enums import EXPIRY_WARNING_DAYS, TeacherReadiness
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.modules.teachers import passport_service as tp
from app.modules.teachers.passport_schemas import TeacherPassport
from app.modules.universities import passport_service as ps
from app.services.teacher_readiness import compute_teacher_readiness

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    """Isolated PG DB per test (canonical SQL migrations; skips w/o PG)."""
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
    """Counts SELECT statements only; reset before each measured call."""
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
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = old


def _counted(db: Session, select_counter, fn, *args, **kwargs):
    db.expire_all()
    select_counter["n"] = 0
    out = fn(*args, **kwargs)
    return out, select_counter["n"]


# ------------------------------------------------------------ builders ---


def _catalog(db: Session, tag: str):
    d = ITDirection(code=f"DIR-TP5-{tag}", name=f"Direction TP5 {tag}")
    db.add(d)
    db.flush()
    p1 = ITProgram(direction_id=d.id, name=f"Program TP5 {tag}-1", description="")
    p2 = ITProgram(direction_id=d.id, name=f"Program TP5 {tag}-2", description="")
    v = Vendor(name=f"Vendor TP5 {tag}")
    db.add_all([p1, p2, v])
    db.flush()
    prod = ITProduct(vendor_id=v.id, name=f"Product TP5 {tag}", version="1.0")
    db.add(prod)
    db.flush()
    return d, p1, p2, v, prod


def _university(db: Session, name: str) -> University:
    u = University(name=name, city="Казань")
    db.add(u)
    db.flush()
    return u


def _teacher(db: Session, uni: University, email: str) -> Teacher:
    t = Teacher(
        university_id=uni.id,
        full_name=f"Teacher {email}",
        email=email,
        position="доцент",
    )
    db.add(t)
    db.flush()
    return t


def _qual(
    db: Session,
    teacher: Teacher,
    name: str,
    expires: date | None,
    obtained_ago: int = 400,
) -> TeacherQualification:
    q = TeacherQualification(
        teacher_id=teacher.id,
        qualification_name=name,
        obtained_at=date.today() - timedelta(days=obtained_ago),
        expires_at=expires,
    )
    db.add(q)
    db.flush()
    return q


def _cert(
    db: Session,
    teacher: Teacher,
    name: str,
    expires: date | None,
    mandatory: bool = True,
    program_id: uuid.UUID | None = None,
) -> TeacherCertificate:
    c = TeacherCertificate(
        teacher_id=teacher.id,
        certificate_name=name,
        issued_by="АНО ДПО",
        issued_at=date.today() - timedelta(days=400),
        expires_at=expires,
        is_mandatory=mandatory,
        program_id=program_id,
    )
    db.add(c)
    db.flush()
    return c


def _link(
    db: Session, teacher: Teacher, program: ITProgram, can_teach: bool = True
) -> TeacherProgram:
    link = TeacherProgram(
        teacher_id=teacher.id,
        program_id=program.id,
        can_teach=can_teach,
        assigned_at=date.today(),
    )
    db.add(link)
    db.flush()
    return link


# ===================================================== P1-05-01 blocks ===


def test_teacher_and_university_blocks_match_db(db: Session):
    _, _, _, _, _ = _catalog(db, "blk")
    u = _university(db, "Uni TP5 Blocks")
    t = _teacher(db, u, "blocks@example.local")
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.teacher.id == t.id
    assert passport.teacher.university_id == u.id
    assert passport.teacher.full_name == "Teacher blocks@example.local"
    assert passport.teacher.email == "blocks@example.local"
    assert passport.teacher.position == "доцент"
    assert passport.university.id == u.id
    assert passport.university.name == "Uni TP5 Blocks"
    assert passport.university.city == "Казань"
    TeacherPassport.model_validate(passport.model_dump())


def test_empty_passport_returns_empty_lists(db: Session):
    u = _university(db, "Uni TP5 Empty")
    t = _teacher(db, u, "empty@example.local")
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.qualifications == []
    assert passport.certificates == []
    assert passport.programs == []
    # canonical rule: no mandatory dated items -> READY, no next date
    assert passport.readiness == TeacherReadiness.READY
    assert passport.next_qualification_date is None
    assert passport.readiness_reasons != []
    TeacherPassport.model_validate(passport.model_dump())


def test_empty_passport_http(engine, api_client):
    with Session(engine) as s:
        u = _university(s, "Uni TP5 HTTP Empty")
        t = _teacher(s, u, "http-empty@example.local")
        s.commit()
        tid = str(t.id)
    r = api_client.get(f"/api/v1/teachers/{tid}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qualifications"] == []
    assert body["certificates"] == []
    assert body["programs"] == []
    assert body["readiness"] == "ready"
    assert body["next_qualification_date"] is None
    assert body["teacher"]["email"] == "http-empty@example.local"
    assert body["university"]["name"] == "Uni TP5 HTTP Empty"
    TeacherPassport.model_validate(body)


def test_unknown_teacher_404(db: Session):
    import app.core.exceptions as exc

    with pytest.raises(exc.NotFound):
        tp.get_teacher_passport(db, uuid.uuid4())


def test_unknown_teacher_404_http(engine, api_client):
    r = api_client.get(f"/api/v1/teachers/{uuid.uuid4()}/passport")
    assert r.status_code == 404
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


def test_invalid_uuid_422_http(engine, api_client):
    r = api_client.get("/api/v1/teachers/not-a-uuid/passport")
    assert r.status_code == 422, r.text


# ===================================================== P1-05-02 quals ===


def test_qualifications_fields_and_nulls_last_ordering(db: Session):
    u = _university(db, "Uni TP5 Qual")
    t = _teacher(db, u, "qual@example.local")
    today = date.today()
    _qual(db, t, "Q-far", today + timedelta(days=400))
    _qual(db, t, "Q-nodate-A", None)
    _qual(db, t, "Q-near", today + timedelta(days=10))
    _qual(db, t, "Q-nodate-B", None)
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    names = [q.qualification_name for q in passport.qualifications]
    assert names[:2] == ["Q-near", "Q-far"]
    assert sorted(names[2:]) == ["Q-nodate-A", "Q-nodate-B"]
    for q in passport.qualifications:
        assert isinstance(q.obtained_at, date)
        assert isinstance(q.id, uuid.UUID)
    TeacherPassport.model_validate(passport.model_dump())


# ===================================================== P1-05-02 certs ===


def test_certificates_fields_and_program_relation(db: Session):
    _, p1, _, _, _ = _catalog(db, "crt")
    u = _university(db, "Uni TP5 Cert")
    t = _teacher(db, u, "cert@example.local")
    today = date.today()
    _cert(db, t, "C-linked", today + timedelta(days=200), program_id=p1.id)
    _cert(
        db,
        t,
        "C-plain",
        today + timedelta(days=50),
        mandatory=False,
        program_id=None,
    )
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert len(passport.certificates) == 2
    # ordering: soonest expiry first
    assert [c.certificate_name for c in passport.certificates] == ["C-plain", "C-linked"]
    linked = passport.certificates[1]
    assert linked.issued_by == "АНО ДПО"
    assert isinstance(linked.issued_at, date)
    assert linked.is_mandatory is True
    assert linked.program_id == p1.id
    assert linked.program is not None
    assert linked.program.id == p1.id
    assert linked.program.name == p1.name
    plain = passport.certificates[0]
    assert plain.program_id is None
    assert plain.program is None
    assert plain.is_mandatory is False
    TeacherPassport.model_validate(passport.model_dump())


# ================================================== P1-05-02 programs ===


def test_programs_join_direction_and_can_teach(db: Session):
    d, p1, p2, _, _ = _catalog(db, "prg")
    u = _university(db, "Uni TP5 Prog")
    t = _teacher(db, u, "prog@example.local")
    _link(db, t, p2, can_teach=True)
    _link(db, t, p1, can_teach=False)
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert len(passport.programs) == 2
    # deterministic ordering by program name
    assert [p.program.name for p in passport.programs] == sorted([p1.name, p2.name])
    by_name = {p.program.name: p for p in passport.programs}
    assert by_name[p1.name].program.direction_name == d.name
    assert by_name[p1.name].program.id == p1.id
    assert by_name[p1.name].can_teach is False
    assert by_name[p2.name].can_teach is True
    assert isinstance(by_name[p1.name].assigned_at, date)
    TeacherPassport.model_validate(passport.model_dump())


# ===================================================== P1-05-03 ready ===


def test_canonical_formula_reused_not_duplicated(db: Session, monkeypatch):
    """The service must CALL the canonical helper (single source of truth)."""
    calls: list = []
    real = tp.compute_teacher_readiness

    def _spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(tp, "compute_teacher_readiness", _spy)
    u = _university(db, "Uni TP5 Spy")
    t = _teacher(db, u, "spy@example.local")
    _cert(db, t, "C", date.today() + timedelta(days=100))
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert len(calls) == 1
    assert len(calls[0]["certificates"]) == 1
    assert len(calls[0]["qualifications"]) == 0
    assert passport.readiness == TeacherReadiness.READY


@pytest.mark.parametrize(
    "delta,expected",
    [
        (-1, TeacherReadiness.EXPIRED),
        (0, TeacherReadiness.ATTENTION),
        (1, TeacherReadiness.ATTENTION),
        (EXPIRY_WARNING_DAYS - 1, TeacherReadiness.ATTENTION),
        (EXPIRY_WARNING_DAYS, TeacherReadiness.ATTENTION),
        (EXPIRY_WARNING_DAYS + 1, TeacherReadiness.READY),
    ],
)
def test_readiness_boundaries_via_passport(db: Session, delta, expected):
    """Expired / today / warning-window / outside-window through the service."""
    u = _university(db, f"Uni TP5 Bound {delta}")
    t = _teacher(db, u, f"bound{delta}@example.local")
    _cert(db, t, "Обязательный", date.today() + timedelta(days=delta))
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.readiness == expected
    assert passport.next_qualification_date == date.today() + timedelta(days=delta)
    direct = compute_teacher_readiness(
        certificates=[
            {
                "certificate_name": "Обязательный",
                "is_mandatory": True,
                "expires_at": date.today() + timedelta(days=delta),
            }
        ],
        qualifications=[],
    )
    assert passport.readiness == direct.readiness
    assert passport.next_qualification_date == direct.next_qualification_date


def test_readiness_ignores_non_mandatory_and_undated(db: Session):
    u = _university(db, "Uni TP5 Ignore")
    t = _teacher(db, u, "ignore@example.local")
    _cert(db, t, "Soft", date.today() - timedelta(days=100), mandatory=False)
    _cert(db, t, "NoDate", None, mandatory=True)
    _qual(db, t, "Q-nodate", None)
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.readiness == TeacherReadiness.READY
    assert passport.next_qualification_date is None


def test_readiness_qualification_expiry_counts(db: Session):
    u = _university(db, "Uni TP5 QualExp")
    t = _teacher(db, u, "qualexp@example.local")
    _qual(db, t, "ПК", date.today() - timedelta(days=2))
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.readiness == TeacherReadiness.EXPIRED
    assert passport.readiness_reasons != []


def test_readiness_consistency_with_university_passport(db: Session):
    """UniversityPassport.teachers[].readiness == TeacherPassport.readiness."""
    _, p1, _, _, _ = _catalog(db, "con")
    from app.models.interactions import UniversityProgram

    u = _university(db, "Uni TP5 Consistency")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="active"))
    today = date.today()
    specs = {
        "con-ready@example.local": today + timedelta(days=400),
        "con-att@example.local": today + timedelta(days=5),
        "con-exp@example.local": today - timedelta(days=3),
    }
    teachers = {}
    for email, expires in specs.items():
        t = _teacher(db, u, email)
        _cert(db, t, "Обязательный", expires)
        _qual(db, t, "ПК", today + timedelta(days=500))
        _link(db, t, p1)
        teachers[email] = t
    db.commit()

    uni_passport = ps.get_passport(db, u.id)
    by_email = {t.email: t for t in uni_passport.teachers}
    for email, t in teachers.items():
        mine = tp.get_teacher_passport(db, t.id)
        assert mine.readiness == by_email[email].readiness, email
        assert mine.next_qualification_date == by_email[email].next_qualification_date, email


# ========================================================= query plan ===


def test_query_count_small_equals_large(db: Session, select_counter):
    """N+1 regression: small vs large teacher must issue equal SELECTs."""
    _, p1, p2, _, _ = _catalog(db, "cnt")
    u = _university(db, "Uni TP5 Counts")
    small = _teacher(db, u, "small@example.local")
    _cert(db, small, "C-small", date.today() + timedelta(days=100))
    _qual(db, small, "Q-small", date.today() + timedelta(days=200))
    _link(db, small, p1)
    db.commit()

    _, small_n = _counted(db, select_counter, tp.get_teacher_passport, db, small.id)

    large = _teacher(db, u, "large@example.local")
    today = date.today()
    for i in range(25):
        _cert(db, large, f"C-large-{i}", today + timedelta(days=100 + i))
    for i in range(25):
        _qual(db, large, f"Q-large-{i}", today + timedelta(days=200 + i))
    _link(db, large, p1)
    _link(db, large, p2)
    db.commit()

    _, large_n = _counted(db, select_counter, tp.get_teacher_passport, db, large.id)
    print(f"\nP1-05 teacher passport query counts: small={small_n} large={large_n}")
    assert (small_n, large_n) == (4, 4)


# ========================================================= isolation ===


def test_cross_teacher_and_university_isolation(db: Session):
    _, p1, p2, _, _ = _catalog(db, "iso")
    uA = _university(db, "Uni TP5 Iso A")
    uB = _university(db, "Uni TP5 Iso B")
    tA = _teacher(db, uA, "isoA@example.local")
    tB = _teacher(db, uB, "isoB@example.local")
    tA2 = _teacher(db, uA, "isoA2@example.local")
    _cert(db, tA, "C-A", date.today() + timedelta(days=100))
    _qual(db, tA, "Q-A", date.today() + timedelta(days=100))
    _link(db, tA, p1)
    _cert(db, tB, "C-B", date.today() + timedelta(days=100))
    _qual(db, tB, "Q-B", date.today() + timedelta(days=100))
    _link(db, tB, p2)
    _cert(db, tA2, "C-A2", date.today() + timedelta(days=100))
    db.commit()

    passport = tp.get_teacher_passport(db, tA.id)
    assert [c.certificate_name for c in passport.certificates] == ["C-A"]
    assert [q.qualification_name for q in passport.qualifications] == ["Q-A"]
    assert [p.program.name for p in passport.programs] == [p1.name]
    assert passport.teacher.university_id == uA.id
    assert passport.university.id == uA.id


# ========================================================= timezone ===


def test_all_datetimes_tz_aware(db: Session):
    _, p1, _, _, _ = _catalog(db, "tz")
    u = _university(db, "Uni TP5 TZ")
    t = _teacher(db, u, "tz@example.local")
    _cert(db, t, "C", date.today() + timedelta(days=100), program_id=p1.id)
    _qual(db, t, "Q", date.today() + timedelta(days=100))
    _link(db, t, p1)
    db.commit()

    passport = tp.get_teacher_passport(db, t.id)
    assert passport.teacher.created_at.tzinfo is not None
    assert passport.teacher.updated_at.tzinfo is not None
    for q in passport.qualifications:
        assert q.created_at.tzinfo is not None
    for c in passport.certificates:
        assert c.created_at.tzinfo is not None


# ========================================================= auth/rbac ===


def _rsa_setup(monkeypatch, kid: str):
    import app.core.security as sec

    def _b64url(num: int) -> str:
        raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(pub.n),
                "e": _b64url(pub.e),
            }
        ]
    }
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: jwks)
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
    return priv


def _mint(priv: str, kid: str, roles: list[str], university_ids=None) -> str:
    from jose import jwt as _jwt

    now = datetime.now(timezone.utc)
    return _jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "preferred_username": "t",
            "realm_access": {"roles": roles},
            "iss": settings.keycloak_issuer,
            "aud": settings.keycloak_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            **({"university_ids": university_ids} if university_ids is not None else {}),
        },
        priv,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture()
def real_client(engine):
    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = False
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = old


def test_401_missing_token(engine, real_client):
    with Session(engine) as s:
        u = _university(s, "Uni TP5 401")
        t = _teacher(s, u, "t401@example.local")
        s.commit()
        tid = str(t.id)
    r = real_client.get(f"/api/v1/teachers/{tid}/passport")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r.json()["error"]["details"] == {}
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


def test_403_guest_without_permission(engine, real_client, monkeypatch):
    with Session(engine) as s:
        u = _university(s, "Uni TP5 403")
        t = _teacher(s, u, "t403@example.local")
        s.commit()
        tid = str(t.id)
    priv = _rsa_setup(monkeypatch, "tp5-guest")
    token = _mint(priv, "tp5-guest", ["guest"])
    r = real_client.get(
        f"/api/v1/teachers/{tid}/passport", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("role", ["admin", "manager", "user"])
def test_200_allowed_roles(engine, real_client, monkeypatch, role):
    """Frozen contract: teacher passport reuses ``university.read`` (no new permission)."""
    with Session(engine) as s:
        u = _university(s, f"Uni TP5 200 {role}")
        t = _teacher(s, u, f"t200-{role}@example.local")
        university_id = str(u.id)
        s.commit()
        tid = str(t.id)
    priv = _rsa_setup(monkeypatch, f"tp5-{role}")
    token = _mint(priv, f"tp5-{role}", [role], [university_id])
    r = real_client.get(
        f"/api/v1/teachers/{tid}/passport", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, (role, r.text)
    TeacherPassport.model_validate(r.json())


# ============================================================ openapi ===


def test_openapi_teacher_passport_route():
    """Pure-unit: route mounted, unique operationId, schemas, error codes."""
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    path = "/api/v1/teachers/{teacher_id}/passport"
    assert path in spec["paths"], sorted(spec["paths"])
    op = spec["paths"][path]["get"]
    assert op["operationId"] == "get_teacher_passport_api_v1_teachers__teacher_id__passport_get"
    assert set(op["responses"]) >= {"200", "401", "403", "404", "422"}
    assert "TeacherPassport" in spec["components"]["schemas"]
    assert "422" in op["responses"]  # invalid UUID rejected by validation
    # operationId uniqueness across the whole spec
    ids = [
        details.get("operationId")
        for path_item in spec["paths"].values()
        for details in path_item.values()
        if isinstance(details, dict)
    ]
    assert len(ids) == len(set(ids))
