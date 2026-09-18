"""P1-04-06 passport performance regression tests.

SQLite by default, PostgreSQL via TEST_DATABASE_URL. Covers:

* base passport SELECT count (<= 8) with an exact per-run count;
* ``?include=`` deltas (health +0, audit +1, both +1);
* scaling: query count is identical on a small and a large dataset;
* readiness adaptor equivalence vs the legacy full-input computation;
* paginated subresources (programs/teachers): structure, totals,
  invalid params, 404/403, constant query count across page sizes;
* latency on the demo dataset (< 500 ms, median of warm runs).
"""

import os
import statistics
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
import test_university_passport as base_t
from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.catalog import (
    Contract,
    License,
    Responsible,
    UniversityResponsible,
)
from app.models.enums import TeacherReadiness
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import TeacherCertificate, TeacherQualification
from app.modules.universities import passport_service as ps
from app.services.teacher_readiness import compute_teacher_readiness

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine(tmp_path):
    url = TEST_URL
    if url == "sqlite://":
        url = f"sqlite:///{tmp_path}/passport_perf_test.db"
    eng = create_engine(url)
    if eng.dialect.name == "sqlite":

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _rec):  # pragma: no cover
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture()
def select_counter(engine):
    """Counts ONLY SELECT statements (fixture setup excluded by resetting)."""
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


def _seed_small(db: Session):
    """Small dataset: a few programs/teachers/licenses + interactions."""
    _, p1, p2, _, prod = base_t._catalog(db, "perf-s")
    u = base_t._university(db, "Uni Perf Small")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="launched"))
    db.add(UniversityProgram(university_id=u.id, program_id=p2.id, status="active"))
    base_t._teacher(
        db, u, "ps1@example.local", [{"expires_at": date.today() + timedelta(days=400)}], [p1]
    )
    base_t._teacher(
        db, u, "ps2@example.local", [{"expires_at": date.today() - timedelta(days=3)}], [p1, p2]
    )
    for i in range(5):
        db.add(
            Student(
                external_id=f"PS-S-{i}",
                university_id=u.id,
                program_id=p1.id if i % 2 == 0 else p2.id,
                full_name=f"S {i}",
                started_at=date.today(),
                status="graduated" if i == 0 else "active",
                finished_at=date.today() if i == 0 else None,
            )
        )
    today = date.today()
    c = Contract(
        university_id=u.id,
        contract_number="DOG-PS-1",
        product_id=prod.id,
        signed_at=today - timedelta(days=30),
        expires_at=today + timedelta(days=300),
        status_raw="signed",
        transfer_status_raw="accepted",
    )
    db.add(c)
    db.flush()
    lic = License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=c.id,
        license_number="LIC-PS-1",
        signed_at=today - timedelta(days=30),
        expires_at=today + timedelta(days=300),
        transfer_status_raw="accepted",
    )
    db.add(lic)
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id, product_id=prod.id, license_id=lic.id, status="active"
        )
    )
    r = Responsible(full_name="Perf Contact", email="perf-s@example.local", role="dean")
    db.add(r)
    db.flush()
    db.add(UniversityResponsible(university_id=u.id, responsible_id=r.id, is_primary=True))
    db.add(
        Document(
            university_id=u.id,
            document_type="act",
            title="PS doc",
            file_path="p",
            file_name="f.pdf",
            file_size=1,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="s",
        )
    )
    db.add(
        Meeting(
            university_id=u.id,
            subject="PS meet",
            participants=[{"name": "N"}],
            meeting_at=datetime.now(timezone.utc),
            created_by_keycloak_sub="s",
        )
    )
    db.add(InteractionNote(university_id=u.id, author_keycloak_sub="s", content="PS note"))
    db.commit()
    return u


def _seed_large(db: Session, u=None):
    """Large dataset: +20 teachers, +10 programs, many links, students, licenses."""
    if u is None:
        u = _seed_small(db)
    else:
        # small seed already present (same tags) — only extend it.
        pass
    today = date.today()
    _, _, _, _, prod = base_t._catalog(db, "perf-l")
    extra_programs = []
    _, p1, p2, _, _ = base_t._catalog(db, "perf-l2")
    for i, p in enumerate([p1, p2]):
        db.add(UniversityProgram(university_id=u.id, program_id=p.id, status="active"))
        extra_programs.append(p)
    for i in range(8):
        dd, pp1, pp2, _, _ = base_t._catalog(db, f"perf-lx{i}")
        for p in (pp1, pp2):
            db.add(UniversityProgram(university_id=u.id, program_id=p.id, status="active"))
            extra_programs.append(p)
    all_programs = [p1, p2] + extra_programs
    for i in range(20):
        base_t._teacher(
            db,
            u,
            f"pl-{i}@example.local",
            [{"expires_at": today + timedelta(days=400 - i * 20)}],
            [all_programs[i % len(all_programs)], all_programs[(i + 1) % len(all_programs)]],
        )
    for i in range(60):
        db.add(
            Student(
                external_id=f"PL-S-{i}",
                university_id=u.id,
                program_id=all_programs[i % len(all_programs)].id,
                full_name=f"LS {i}",
                started_at=today,
                status="graduated" if i % 7 == 0 else "active",
                finished_at=today if i % 7 == 0 else None,
            )
        )
    for i in range(6):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=None,
                license_number=f"LIC-PL-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=50 + i * 30),
                transfer_status_raw="accepted",
            )
        )
    for i in range(4):
        db.add(
            Contract(
                university_id=u.id,
                contract_number=f"DOG-PL-{i}",
                signed_at=today - timedelta(days=i * 10),
                expires_at=today + timedelta(days=300),
                status_raw="signed",
                transfer_status_raw="accepted",
            )
        )
    for i in range(15):
        db.add(
            Document(
                university_id=u.id,
                document_type="act",
                title=f"PL doc {i}",
                file_path="p",
                file_name=f"{i}.pdf",
                file_size=10,
                mime_type="application/pdf",
                uploaded_by_keycloak_sub="s",
            )
        )
    db.commit()
    return u


def _counted(db: Session, select_counter, fn, *args, **kwargs):
    db.expire_all()
    select_counter["n"] = 0
    out = fn(*args, **kwargs)
    return out, select_counter["n"]


# ------------------------------------------------------------ query count ---


def test_base_passport_query_count_bounded(db: Session, select_counter):
    u = _seed_small(db)
    uid = u.id
    _, n = _counted(db, select_counter, ps.get_passport, db, uid)
    print(f"\nbase passport SELECT count (small): {n}")
    assert n <= 8, f"base passport took {n} SELECTs (budget 8)"


def test_include_query_count_deltas(db: Session, select_counter):
    from app.modules.audit.models import AuditEvent

    u = _seed_small(db)
    uid = u.id
    db.add(
        AuditEvent(
            user_id=1, entity_type="university", entity_id=1, action="update", university_id=uid
        )
    )
    db.commit()
    _, base = _counted(db, select_counter, ps.get_passport, db, uid)
    _, with_health = _counted(
        db,
        select_counter,
        ps.get_passport,
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE]),
    )
    _, with_audit = _counted(
        db,
        select_counter,
        ps.get_passport,
        db,
        uid,
        include=frozenset([ps.PassportInclude.AUDIT]),
    )
    _, with_both = _counted(
        db,
        select_counter,
        ps.get_passport,
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]),
    )
    print(f"\nbase={base} health={with_health} audit={with_audit} both={with_both}")
    assert with_health == base, (base, with_health)
    assert with_audit == base + 1, (base, with_audit)
    assert with_both == base + 1, (base, with_both)


def test_scaling_no_n_plus_1(db: Session, select_counter):
    u = _seed_small(db)
    uid = u.id
    _, small_n = _counted(db, select_counter, ps.get_passport, db, uid)
    _seed_large(db, u)
    _, large_n = _counted(db, select_counter, ps.get_passport, db, uid)
    print(f"\nscaling: small={small_n} large={large_n}")
    assert small_n <= 8 and large_n <= 8
    assert large_n == small_n, f"N+1: {small_n} -> {large_n}"


# -------------------------------------------------------------- readiness ---


def test_readiness_adaptor_matches_legacy_formula(db: Session):
    """Optimized teacher DTOs match compute_teacher_readiness on full objects."""
    _, p1, _, _, _ = base_t._catalog(db, "ra")
    u = base_t._university(db, "Uni Readiness Adaptor")
    today = date.today()
    cases = [
        ("ready", [{"expires_at": today + timedelta(days=400)}], True),
        ("attention", [{"expires_at": today + timedelta(days=10)}], True),
        ("expired", [{"expires_at": today - timedelta(days=5)}], True),
        (
            "nonmandatory",
            [{"expires_at": today - timedelta(days=5), "is_mandatory": False, "name": "Soft"}],
            True,
        ),
        ("noexpiry", [{"expires_at": None}], True),
        ("empty", [], True),
    ]
    teachers = []
    for email, certs, _ in cases:
        teachers.append(base_t._teacher(db, u, f"{email}@example.local", certs, [p1]))
    # qualification-only teacher (expired qual, no certs)
    tq = base_t._teacher(db, u, "qualonly@example.local", [], [p1])
    db.query(TeacherCertificate).filter(TeacherCertificate.teacher_id == tq.id).delete()
    db.query(TeacherQualification).filter(TeacherQualification.teacher_id == tq.id).delete()
    db.add(
        TeacherQualification(
            teacher_id=tq.id,
            qualification_name="ПК",
            obtained_at=today - timedelta(days=400),
            expires_at=today - timedelta(days=1),
        )
    )
    teachers.append(tq)
    db.commit()

    dtos = {t.email: t for t in ps.get_teachers(db, u.id)}
    assert len(dtos) == len(teachers)
    for t in teachers:
        db.expire_all()
        certs = (
            db.execute(select(TeacherCertificate).where(TeacherCertificate.teacher_id == t.id))
            .scalars()
            .all()
        )
        quals = (
            db.execute(select(TeacherQualification).where(TeacherQualification.teacher_id == t.id))
            .scalars()
            .all()
        )
        expected = compute_teacher_readiness(certificates=list(certs), qualifications=list(quals))
        got = dtos[t.email]
        assert got.readiness == expected.readiness, t.email
        assert got.next_qualification_date == expected.next_qualification_date, t.email
    by_email = {t.email: t for t in teachers}
    assert dtos["ready@example.local"].readiness == TeacherReadiness.READY
    assert dtos["attention@example.local"].readiness == TeacherReadiness.ATTENTION
    assert dtos["expired@example.local"].readiness == TeacherReadiness.EXPIRED
    assert by_email  # silence linters


# --------------------------------------------------------------- pagination ---


def test_programs_pagination_pages_and_total(db: Session, select_counter):
    u = _seed_large(db)
    items, total = ps.get_programs_page(db, u.id, page=1, page_size=5)
    assert total >= 10, total
    assert len(items) == 5
    items2, total2 = ps.get_programs_page(db, u.id, page=2, page_size=5)
    assert total2 == total
    assert len(items2) == 5
    assert {p.id for p in items} & {p.id for p in items2} == set()
    rest, _ = ps.get_programs_page(db, u.id, page=99, page_size=5)
    assert rest == []
    for p in items:
        assert p.teachers_count >= 0 and p.students_count >= 0
        assert p.direction_name


def test_teachers_pagination_pages_and_total(db: Session):
    u = _seed_large(db)
    items, total = ps.get_teachers_page(db, u.id, page=1, page_size=5)
    assert total >= 20, total
    assert len(items) == 5
    items2, _ = ps.get_teachers_page(db, u.id, page=2, page_size=5)
    assert {t.id for t in items} & {t.id for t in items2} == set()
    for t in items:
        assert t.readiness in (
            TeacherReadiness.READY,
            TeacherReadiness.ATTENTION,
            TeacherReadiness.EXPIRED,
        )
        assert isinstance(t.programs, list)


def test_pagination_query_count_constant(db: Session, select_counter):
    u = _seed_large(db)
    _, n5 = _counted(db, select_counter, ps.get_programs_page, db, u.id, 1, 5)
    _, n20 = _counted(db, select_counter, ps.get_programs_page, db, u.id, 1, 20)
    assert n5 == n20, (n5, n20)
    _, t5 = _counted(db, select_counter, ps.get_teachers_page, db, u.id, 1, 5)
    _, t20 = _counted(db, select_counter, ps.get_teachers_page, db, u.id, 1, 20)
    assert t5 == t20, (t5, t20)


def test_pagination_unknown_university_404(db: Session):
    with pytest.raises(Exception) as exc_info:
        ps.get_programs_page(db, uuid.uuid4(), 1, 20)
    assert getattr(exc_info.value, "status_code", None) == 404
    with pytest.raises(Exception) as exc_info:
        ps.get_teachers_page(db, uuid.uuid4(), 1, 20)
    assert getattr(exc_info.value, "status_code", None) == 404


def test_pagination_endpoints(engine, api_client):
    with Session(engine) as s:
        u = _seed_large(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport/programs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page"] == 1 and body["page_size"] == 20
    assert body["total"] >= 10 and len(body["items"]) > 0

    r2 = api_client.get(f"/api/v1/universities/{uid}/passport/programs?page=2&page_size=5")
    assert r2.status_code == 200, r2.text
    assert r2.json()["page_size"] == 5
    assert {p["id"] for p in body["items"][:5]} & {p["id"] for p in r2.json()["items"]} == set()

    t = api_client.get(f"/api/v1/universities/{uid}/passport/teachers?page=1&page_size=7")
    assert t.status_code == 200, t.text
    tbody = t.json()
    assert tbody["total"] >= 20 and len(tbody["items"]) == 7

    for bad in ("page=0", "page_size=0", "page_size=101"):
        bad_r = api_client.get(f"/api/v1/universities/{uid}/passport/programs?{bad}")
        assert bad_r.status_code == 422, (bad, bad_r.text)
        bad_t = api_client.get(f"/api/v1/universities/{uid}/passport/teachers?{bad}")
        assert bad_t.status_code == 422, (bad, bad_t.text)

    missing = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport/programs")
    assert missing.status_code == 404
    missing_t = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport/teachers")
    assert missing_t.status_code == 404


def test_pagination_endpoints_guest_forbidden(engine):
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
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "t406",
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
            u = _seed_small(s)
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
            headers={"kid": "t406"},
        )
        with TestClient(app) as client:
            for url in (
                f"/api/v1/universities/{uid}/passport/programs",
                f"/api/v1/universities/{uid}/passport/teachers",
            ):
                r = client.get(url, headers={"Authorization": f"Bearer {token}"})
                assert r.status_code == 403, (url, r.text)
    finally:
        sec._fetch_jwks = orig_fetch
        sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
        settings.keycloak_issuer, settings.keycloak_audience = (orig_issuer, orig_aud)
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = False


# ------------------------------------------------------------------ latency ---


def test_latency_demo_dataset(engine):
    from app.db.seed import seed_demo

    with Session(engine) as s:
        seed_demo(s)
        s.commit()
        uni_id = (
            s.execute(select(base_t.University.id).order_by(base_t.University.name))
            .scalars()
            .first()
        )
    assert uni_id is not None
    with Session(engine) as db:
        ps.get_passport(db, uni_id)  # warmup
        db.expire_all()
        t0 = time.perf_counter()
        ps.get_passport(db, uni_id)
        cold_ms = (time.perf_counter() - t0) * 1000
        warms = []
        for _ in range(7):
            db.expire_all()
            t0 = time.perf_counter()
            ps.get_passport(db, uni_id)
            warms.append((time.perf_counter() - t0) * 1000)
        median_ms = statistics.median(warms)
        print(
            f"\ndemo dataset latency: cold={cold_ms:.1f}ms "
            f"warm={[f'{w:.1f}' for w in warms]} median={median_ms:.1f}ms"
        )
        assert median_ms < 500, median_ms
        assert max(warms) < 500, warms
