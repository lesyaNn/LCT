"""P1-11-02 passport regression suite (University Passport full coverage).

Complements (never duplicates) the existing suites:

* ``test_university_passport.py`` — base blocks, standalone getters, endpoint
  200/404/403, service-layer delegation;
* ``test_passport_include.py`` — include parsing, no-include spies, health /
  audit / both, graceful degradation, 404-no-calls, 422-no-calls, deltas;
* ``test_passport_performance.py`` — bounded counts, deltas, scaling,
  readiness adaptor, pagination, demo latency.

This file closes the remaining P1-11-02 acceptance gaps through the PUBLIC
passport pipeline (``get_passport`` / HTTP), never through private loaders:

* exact program counters (aggregate-reuse trap, §8);
* teacher university isolation (§9);
* deterministic readiness boundaries via the canonical formula (§10-12);
* extended readiness equivalence incl. qualifications (§13);
* students math consistency (§14-15);
* product vendor resolution + explicit-vs-fallback license choice (§16-17);
* license/contract field + derived-status pins via production properties
  (§18-20), license sort via passport (§21);
* documents/meetings caps via passport (§22-23), participant shapes (§24);
* responsibles M:N isolation + role fallback (§25);
* timeline sources/limit/ordering/reuse via passport (§26-28);
* tz-aware datetimes incl. optional blocks (§29);
* empty passport at HTTP level (§30);
* 404 schema / 403 / 401 (§31-33);
* include edge spellings at HTTP level (§39);
* base-error propagation (§44);
* EXACT query counts 8/8/9/9 + scaling + audit-row independence (§45-46);
* PostgreSQL latency <500 ms on the reused demo dataset (§47-48);
* pagination content + budgets via HTTP (§49-53);
* Teacher Passport production pin: endpoint mounted via P1-05 (§54);
* OpenAPI passport paths (§64);
* central 409 handler coexistence with 404/403/422 (§65).

DB integration tests require PostgreSQL via ``TEST_DATABASE_URL`` pointing at a
DEDICATED test database (``rtk_p1_test``): the fixture resets the schema
(``DROP SCHEMA public CASCADE``) and applies the canonical SQL migrations.
Pure-unit tests (readiness math, discovery pins) run anywhere.
"""

import base64
import os
import statistics
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register catalog/interactions/teachers metadata)
import test_passport_performance as perf
import test_university_passport as base_t
from app.config import settings
from app.core.errors import register_error_handlers
from app.db.session import get_db
from app.main import app
from app.models.catalog import Contract, License
from app.models.enums import EXPIRY_WARNING_DAYS, TeacherReadiness
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.modules.audit.models import AuditEvent
from app.modules.universities import passport_service as ps
from app.modules.universities.passport_schemas import UniversityPassport
from app.services.teacher_readiness import compute_teacher_readiness

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _is_pg(engine) -> bool:
    return engine.dialect.name == "postgresql"


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


class _FrozenDate(date):
    """Deterministic today for the passport pipeline (no flaky wall-clock)."""

    _today: date = date(2026, 3, 15)

    @classmethod
    def today(cls) -> date:
        return cls._today


# ============================================================ university ===


def test_university_block_matches_db_row(db: Session):
    u = base_t._university(db, "Uni Block Check")
    db.commit()
    passport = ps.get_passport(db, u.id)
    assert passport.university.id == u.id
    assert passport.university.name == "Uni Block Check"
    assert passport.university.city == "Москва"
    UniversityPassport.model_validate(passport.model_dump())


def test_full_schema_validation_types(db: Session):
    """UUID/enum/date/datetime/nested DTOs validate through production schema."""
    _, p1, _, _, _ = base_t._catalog(db, "schema")
    u = base_t._university(db, "Uni Schema")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="launched"))
    base_t._teacher(
        db,
        u,
        "schema-t@example.local",
        [{"expires_at": date.today() + timedelta(days=400)}],
        [p1],
    )
    db.add(
        Student(
            external_id="SCH-1",
            university_id=u.id,
            program_id=p1.id,
            full_name="С",
            started_at=date.today(),
        )
    )
    db.commit()
    passport = ps.get_passport(db, u.id)
    dumped = passport.model_dump()
    assert isinstance(dumped["university"]["id"], uuid.UUID)
    assert isinstance(dumped["teachers"][0]["readiness"], TeacherReadiness)
    assert isinstance(dumped["programs"][0]["launch_date"], (date, type(None)))
    assert isinstance(dumped["workflow_summary"]["progress_percent"], float)
    UniversityPassport.model_validate(dumped)


# ============================================================== programs ===


def test_program_exact_counters_catch_aggregate_reuse(db: Session):
    """Program A: 3 teachers / 5 students; Program B: 1 teacher / 2 students.

    Goes through get_passport (not the standalone getter) so a mix-up
    between the students aggregate and the teacher counter is caught.
    """
    _, pA, pB, _, _ = base_t._catalog(db, "exact")
    u = base_t._university(db, "Uni Exact Counts")
    db.add(UniversityProgram(university_id=u.id, program_id=pA.id, status="launched"))
    db.add(UniversityProgram(university_id=u.id, program_id=pB.id, status="active"))
    far = date.today() + timedelta(days=400)
    base_t._teacher(db, u, "exa1@example.local", [{"expires_at": far}], [pA])
    base_t._teacher(db, u, "exa2@example.local", [{"expires_at": far}], [pA])
    base_t._teacher(db, u, "exa3@example.local", [{"expires_at": far}], [pA])
    base_t._teacher(db, u, "exb1@example.local", [{"expires_at": far}], [pB])
    for i in range(5):
        db.add(
            Student(
                external_id=f"EXA-{i}",
                university_id=u.id,
                program_id=pA.id,
                full_name=f"A {i}",
                started_at=date.today(),
            )
        )
    for i in range(2):
        db.add(
            Student(
                external_id=f"EXB-{i}",
                university_id=u.id,
                program_id=pB.id,
                full_name=f"B {i}",
                started_at=date.today(),
            )
        )
    db.commit()

    passport = ps.get_passport(db, u.id)
    by_name = {p.name: p for p in passport.programs}
    assert (by_name[pA.name].teachers_count, by_name[pA.name].students_count) == (3, 5)
    assert (by_name[pB.name].teachers_count, by_name[pB.name].students_count) == (1, 2)
    assert by_name[pA.name].direction_name == "Direction exact"
    assert by_name[pA.name].status.value == "launched"


# ============================================================== teachers ===


def test_teachers_university_isolation_and_fields(db: Session):
    _, p1, _, _, _ = base_t._catalog(db, "iso")
    uA = base_t._university(db, "Uni A Iso")
    uB = base_t._university(db, "Uni B Iso")
    db.add(UniversityProgram(university_id=uA.id, program_id=p1.id, status="active"))
    base_t._teacher(
        db,
        uA,
        "mine@example.local",
        [{"expires_at": date.today() + timedelta(days=400)}],
        [p1],
    )
    other = Teacher(
        university_id=uB.id,
        full_name="Чужой Препод",
        email="other@example.local",
        position="профессор",
    )
    db.add(other)
    db.commit()

    passport = ps.get_passport(db, uA.id)
    emails = [t.email for t in passport.teachers]
    assert emails == ["mine@example.local"]
    t = passport.teachers[0]
    assert t.full_name and t.position == "доцент"
    assert t.readiness == TeacherReadiness.READY
    assert t.next_qualification_date is not None
    assert len(t.programs) == 1 and t.programs[0].name == p1.name


# ============================================================== readiness ==


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
def test_canonical_readiness_boundaries(delta, expected):
    """Boundary pin of the production formula (deterministic `today`, §12)."""
    today = date(2026, 3, 15)
    result = compute_teacher_readiness(
        certificates=[
            {
                "certificate_name": "Обязательный",
                "is_mandatory": True,
                "expires_at": today + timedelta(days=delta),
            }
        ],
        qualifications=[],
        today=today,
    )
    assert result.readiness == expected
    if expected == TeacherReadiness.READY:
        assert result.next_qualification_date == today + timedelta(days=delta)
    # expired yesterday / today / far future sanity on next_qualification_date
    assert result.next_qualification_date == today + timedelta(days=delta)


def test_canonical_ignores_non_mandatory_and_undated():
    today = date(2026, 3, 15)
    result = compute_teacher_readiness(
        certificates=[
            {
                "certificate_name": "Soft",
                "is_mandatory": False,
                "expires_at": today - timedelta(days=100),
            },
            {"certificate_name": "NoDate", "is_mandatory": True, "expires_at": None},
        ],
        qualifications=[{"qualification_name": "Q", "expires_at": None}],
        today=today,
    )
    assert result.readiness == TeacherReadiness.READY
    assert result.next_qualification_date is None


def test_passport_readiness_deterministic_under_frozen_clock(db: Session, monkeypatch):
    """Passport readiness uses the frozen today; matches canonical formula."""
    from app.services import teacher_readiness as tr_mod

    monkeypatch.setattr(ps, "date", _FrozenDate)
    monkeypatch.setattr(tr_mod, "date", _FrozenDate)
    today = _FrozenDate.today()
    _, p1, _, _, _ = base_t._catalog(db, "frozen")
    u = base_t._university(db, "Uni Frozen")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="active"))
    # expired yesterday / expires today / +30 / +31 under the frozen clock
    specs = [("fz-exp", -1), ("fz-today", 0), ("fz-30", 30), ("fz-31", 31)]
    for email, delta in specs:
        t = Teacher(
            university_id=u.id,
            full_name=f"T {email}",
            email=f"{email}@example.local",
            position="доцент",
        )
        db.add(t)
        db.flush()
        db.add(
            TeacherCertificate(
                teacher_id=t.id,
                certificate_name="Обязательный",
                issued_by="АНО ДПО",
                issued_at=today - timedelta(days=400),
                expires_at=today + timedelta(days=delta),
                is_mandatory=True,
            )
        )
        db.add(
            TeacherQualification(
                teacher_id=t.id,
                qualification_name="ПК ППС",
                obtained_at=today - timedelta(days=400),
                expires_at=today + timedelta(days=400),
            )
        )
        db.add(
            TeacherProgram(
                teacher_id=t.id,
                program_id=p1.id,
                can_teach=True,
                assigned_at=today,
            )
        )
    db.commit()

    passport = ps.get_passport(db, u.id)
    by_email = {t.email: t for t in passport.teachers}
    assert by_email["fz-exp@example.local"].readiness == TeacherReadiness.EXPIRED
    assert by_email["fz-today@example.local"].readiness == TeacherReadiness.ATTENTION
    assert by_email["fz-30@example.local"].readiness == TeacherReadiness.ATTENTION
    assert by_email["fz-31@example.local"].readiness == TeacherReadiness.READY
    # equivalence with canonical formula evaluated at the same frozen today
    for email, delta in specs:
        expected = compute_teacher_readiness(
            certificates=[
                {
                    "certificate_name": "Обязательный",
                    "is_mandatory": True,
                    "expires_at": today + timedelta(days=delta),
                }
            ],
            qualifications=[
                {
                    "qualification_name": "ПК ППС",
                    "expires_at": today + timedelta(days=400),
                }
            ],
            today=today,
        )
        got = by_email[f"{email}@example.local"]
        assert got.readiness == expected.readiness, email
        assert got.next_qualification_date == expected.next_qualification_date, email


def test_readiness_equivalence_qualification_combinations(db: Session):
    """Optimized passport readiness == canonical on qual-heavy combinations."""
    _, p1, _, _, _ = base_t._catalog(db, "qual")
    u = base_t._university(db, "Uni Qual Equiv")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="active"))
    today = date.today()
    combos = {
        "q-valid": ([], today + timedelta(days=200)),
        "q-soon": ([], today + timedelta(days=5)),
        "q-expired": ([], today - timedelta(days=2)),
        "q-none": ([], None),
    }
    teachers = []
    for email, (certs, q_exp) in combos.items():
        t = base_t._teacher(db, u, f"{email}@example.local", certs, [p1])
        db.query(TeacherQualification).filter(TeacherQualification.teacher_id == t.id).delete()
        if q_exp is not None:
            db.add(
                TeacherQualification(
                    teacher_id=t.id,
                    qualification_name="ПК",
                    obtained_at=today - timedelta(days=400),
                    expires_at=q_exp,
                )
            )
        teachers.append(t)
    # mixed: soon cert + expired qual -> EXPIRED wins
    tm = base_t._teacher(
        db,
        u,
        "q-mixed@example.local",
        [{"expires_at": today + timedelta(days=3)}],
        [p1],
    )
    db.add(
        TeacherQualification(
            teacher_id=tm.id,
            qualification_name="ПК-mix",
            obtained_at=today - timedelta(days=400),
            expires_at=today - timedelta(days=1),
        )
    )
    teachers.append(tm)
    db.commit()

    dtos = {t.email: t for t in ps.get_teachers(db, u.id)}
    assert dtos["q-valid@example.local"].readiness == TeacherReadiness.READY
    assert dtos["q-soon@example.local"].readiness == TeacherReadiness.ATTENTION
    assert dtos["q-expired@example.local"].readiness == TeacherReadiness.EXPIRED
    assert dtos["q-none@example.local"].readiness == TeacherReadiness.READY
    assert dtos["q-none@example.local"].next_qualification_date is None
    assert dtos["q-mixed@example.local"].readiness == TeacherReadiness.EXPIRED
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


# ============================================================== students ===


def test_students_summary_math_consistency(db: Session):
    """total=10 / active=6 / graduated=4; sums over by_status/by_program hold."""
    _, pA, pB, _, _ = base_t._catalog(db, "smath")
    u = base_t._university(db, "Uni Students Math")
    db.add(UniversityProgram(university_id=u.id, program_id=pA.id, status="active"))
    db.add(UniversityProgram(university_id=u.id, program_id=pB.id, status="active"))
    plan = [(pA, "active", 3), (pA, "graduated", 2), (pB, "active", 3), (pB, "graduated", 2)]
    n = 0
    for prog, status, cnt in plan:
        for _ in range(cnt):
            db.add(
                Student(
                    external_id=f"SM-{n}",
                    university_id=u.id,
                    program_id=prog.id,
                    full_name=f"S {n}",
                    started_at=date.today(),
                    status=status,
                    finished_at=date.today() if status == "graduated" else None,
                )
            )
            n += 1
    db.commit()

    passport = ps.get_passport(db, u.id)
    s = passport.students_summary
    assert (s.total, s.active, s.graduated) == (10, 6, 4)
    assert sum(s.by_status.values()) == s.total == 10
    assert sum(r.total for r in s.by_program) == s.total == 10
    assert s.by_status == {"active": 6, "graduated": 4}
    by_prog = {r.program_id: r for r in s.by_program}
    assert (by_prog[pA.id].total, by_prog[pA.id].active, by_prog[pA.id].graduated) == (5, 3, 2)
    assert (by_prog[pB.id].total, by_prog[pB.id].active, by_prog[pB.id].graduated) == (5, 3, 2)


# ============================================================== products ===


def _product_setup(db: Session, tag: str):
    _, _, _, v, prod = base_t._catalog(db, tag)
    u = base_t._university(db, f"Uni Prod {tag}")
    return u, prod, v


def test_product_vendor_from_catalog_not_contract_fallback(db: Session):
    """vendor_name follows it_products.vendor_id even with an unrelated contract."""
    u, prod, v = _product_setup(db, "vend")
    today = date.today()
    db.add(
        Contract(
            university_id=u.id,
            contract_number=f"DOG-VEND-{uuid.uuid4().hex[:6]}",
            product_id=None,
            signed_at=today - timedelta(days=5),
            expires_at=today + timedelta(days=500),
            status_raw="signed",
            transfer_status_raw="accepted",
        )
    )
    lic = License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=None,
        license_number="LIC-VEND-1",
        signed_at=today - timedelta(days=10),
        expires_at=today + timedelta(days=100),
        transfer_status_raw="accepted",
    )
    db.add(lic)
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id,
            product_id=prod.id,
            license_id=lic.id,
            status="active",
        )
    )
    db.commit()

    passport = ps.get_passport(db, u.id)
    assert len(passport.products) == 1
    assert passport.products[0].vendor_name == v.name
    assert passport.products[0].license is not None
    assert passport.products[0].license.vendor_name == v.name
    assert passport.licenses[0].vendor_name == v.name


def test_product_license_explicit_priority_over_nearest(db: Session):
    """Two licenses; explicit link points at the FAR one -> far one is chosen."""
    u, prod, _ = _product_setup(db, "expl")
    today = date.today()
    near = License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=None,
        license_number="LIC-EXPL-NEAR",
        signed_at=today - timedelta(days=10),
        expires_at=today + timedelta(days=10),
        transfer_status_raw="accepted",
    )
    far = License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=None,
        license_number="LIC-EXPL-FAR",
        signed_at=today - timedelta(days=10),
        expires_at=today + timedelta(days=200),
        transfer_status_raw="accepted",
    )
    db.add_all([near, far])
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id,
            product_id=prod.id,
            license_id=far.id,
            status="active",
        )
    )
    db.commit()

    passport = ps.get_passport(db, u.id)
    assert passport.products[0].license is not None
    assert passport.products[0].license.license_number == "LIC-EXPL-FAR"


def test_product_license_fallback_to_nearest_active(db: Session):
    """explicit=None -> nearest non-expired license of the same product."""
    u, prod, _ = _product_setup(db, "fb")
    today = date.today()
    for i, delta in enumerate([200, 10, 100]):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=None,
                license_number=f"LIC-FB-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=delta),
                transfer_status_raw="accepted",
            )
        )
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id,
            product_id=prod.id,
            license_id=None,
            status="active",
        )
    )
    db.commit()

    passport = ps.get_passport(db, u.id)
    assert passport.products[0].license is not None
    assert passport.products[0].license.license_number == "LIC-FB-1"  # +10 nearest
    # expired licenses are never a fallback
    assert passport.products[0].license.status != "expired"


# ============================================================== licenses ===


def test_license_fields_and_derived_match_production_property(db: Session):
    """Every LicenseShort field present; status/days equal the model property."""
    u, prod, _ = _product_setup(db, "lf")
    today = date.today()
    c = Contract(
        university_id=u.id,
        contract_number=f"DOG-LF-{uuid.uuid4().hex[:6]}",
        product_id=prod.id,
        signed_at=today - timedelta(days=30),
        expires_at=today + timedelta(days=300),
        status_raw="signed",
        transfer_status_raw="accepted",
    )
    db.add(c)
    db.flush()
    deltas = [-1, 0, 1, 29, 30, 31]
    for i, delta in enumerate(deltas):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=c.id,
                license_number=f"LIC-LF-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=delta),
                transfer_status_raw="accepted",
            )
        )
    db.commit()

    passport = ps.get_passport(db, u.id)
    assert len(passport.licenses) == 6
    for lic in passport.licenses:
        assert lic.license_number and lic.product_name and lic.vendor_name
        assert isinstance(lic.signed_at, date) and isinstance(lic.expires_at, date)
        assert lic.transfer_status == "accepted"
        assert lic.contract_number == c.contract_number
        transient = License(
            product_id=prod.id,
            signed_at=lic.signed_at,
            expires_at=lic.expires_at,
            transfer_status_raw="accepted",
        )
        assert lic.status == transient.derived_status, lic.license_number
        assert lic.days_to_expiry == transient.days_to_expiry, lic.license_number
    by_number = {lic.license_number: lic for lic in passport.licenses}
    assert by_number["LIC-LF-0"].status == "expired"
    assert by_number["LIC-LF-0"].days_to_expiry == -1
    for suffix in ("LIC-LF-1", "LIC-LF-2", "LIC-LF-3", "LIC-LF-4"):
        assert by_number[suffix].status == "expires_soon", suffix
    assert by_number["LIC-LF-1"].days_to_expiry == 0
    assert by_number["LIC-LF-5"].status == "active"
    assert by_number["LIC-LF-5"].days_to_expiry == 31


def test_framework_contract_vendor_via_linked_license(db: Session):
    """product_id NULL contract resolves vendor through its linked licenses."""
    u, prod, vendor = _product_setup(db, "fwlic")
    today = date.today()
    fw = Contract(
        university_id=u.id,
        contract_number=f"DOG-FWLIC-{uuid.uuid4().hex[:6]}",
        product_id=None,
        signed_at=today - timedelta(days=5),
        expires_at=today + timedelta(days=500),
        status_raw="signed",
        transfer_status_raw="accepted",
    )
    db.add(fw)
    db.flush()
    db.add(
        License(
            university_id=u.id,
            product_id=prod.id,
            contract_id=fw.id,
            license_number="LIC-FWLIC-1",
            signed_at=today - timedelta(days=5),
            expires_at=today + timedelta(days=500),
            transfer_status_raw="accepted",
        )
    )
    db.commit()
    passport = ps.get_passport(db, u.id)
    assert len(passport.contracts) == 1
    assert passport.contracts[0].vendor_name == vendor.name


def test_licenses_sorted_expires_asc_via_passport(db: Session):
    u, prod, _ = _product_setup(db, "lsort")
    today = date.today()
    for i, delta in enumerate([100, 5, 50]):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=None,
                license_number=f"LIC-LS-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=delta),
                transfer_status_raw="accepted",
            )
        )
    db.commit()
    passport = ps.get_passport(db, u.id)
    expiries = [lic.expires_at for lic in passport.licenses]
    assert expiries == sorted(expiries)
    assert [lic.license_number for lic in passport.licenses] == ["LIC-LS-1", "LIC-LS-2", "LIC-LS-0"]


# ============================================================== contracts ==


def test_contracts_fields_and_signed_desc_via_passport(db: Session):
    u, prod, vendor = _product_setup(db, "csort")
    today = date.today()
    for i, back in enumerate([10, 100, 50]):
        db.add(
            Contract(
                university_id=u.id,
                contract_number=f"DOG-CS-{i}",
                product_id=prod.id,
                signed_at=today - timedelta(days=back),
                expires_at=today + timedelta(days=300),
                status_raw="signed",
                transfer_status_raw="accepted",
            )
        )
    db.commit()
    passport = ps.get_passport(db, u.id)
    assert len(passport.contracts) == 3
    signed = [c.signed_at for c in passport.contracts]
    assert signed == sorted(signed, reverse=True)
    for c in passport.contracts:
        assert c.contract_number.startswith("DOG-CS-")
        assert c.vendor_name == vendor.name  # resolved via linked product
        assert c.status in ("active", "expires_soon", "expired", "draft", "signed", "terminated")


# ============================================================== documents ==


def test_documents_cap_selects_latest_via_passport(db: Session):
    u = base_t._university(db, "Uni Docs Cap")
    db.commit()
    base = datetime.now(timezone.utc)
    for i in range(25):
        db.add(
            Document(
                university_id=u.id,
                document_type="act",
                title=f"CapDoc {i:02d}",
                file_path=f"p/{i}",
                file_name=f"{i}.pdf",
                file_size=100 + i,
                mime_type="application/pdf",
                uploaded_by_keycloak_sub="seed",
            )
        )
    db.commit()
    rows = db.execute(select(Document).where(Document.university_id == u.id)).scalars().all()
    for i, d in enumerate(sorted(rows, key=lambda x: x.title)):
        d.created_at = base - timedelta(days=i)
    db.commit()
    db.expire_all()

    passport = ps.get_passport(db, u.id)
    assert len(passport.documents) == 20
    titles = [d.title for d in passport.documents]
    assert "CapDoc 24" not in titles  # oldest 5 dropped
    assert "CapDoc 00" in titles
    created = [d.created_at for d in passport.documents]
    assert created == sorted(created, reverse=True)


# =============================================================== meetings ===


def test_meetings_cap_and_order_via_passport(db: Session):
    u = base_t._university(db, "Uni Meet Cap")
    base = datetime.now(timezone.utc)
    for i in range(12):
        db.add(
            Meeting(
                university_id=u.id,
                subject=f"CapMeet {i:02d}",
                participants=[{"name": f"Человек {i}", "role": "Ректор"}],
                meeting_at=base - timedelta(days=i),
                created_by_keycloak_sub="mgr",
            )
        )
    db.commit()
    passport = ps.get_passport(db, u.id)
    assert len(passport.meetings) == 10
    times = [m.meeting_at for m in passport.meetings]
    assert times == sorted(times, reverse=True)
    assert passport.meetings[0].participants == ["Человек 0"]
    subjects = [m.subject for m in passport.meetings]
    assert "CapMeet 00" in subjects and "CapMeet 11" not in subjects


def test_participants_supported_shapes(db: Session):
    u = base_t._university(db, "Uni Part Shapes")
    base = datetime.now(timezone.utc)
    shapes = [
        None,
        "просто строка",
        [{"name": "Иванов И.И.", "role": "Ректор"}, "guest@example.local"],
        [{"email": "noname@example.local"}],
        [{"unknown_key": "x"}],
        42,
        [42, "", None, {"name": "Смешанный"}],
    ]
    for i, shape in enumerate(shapes):
        db.add(
            Meeting(
                university_id=u.id,
                subject=f"Shape {i}",
                participants=shape,  # type: ignore[arg-type]
                meeting_at=base - timedelta(hours=i),
                created_by_keycloak_sub="mgr",
            )
        )
    db.commit()
    passport = ps.get_passport(db, u.id)
    by_subject = {m.subject: m for m in passport.meetings}
    assert by_subject["Shape 0"].participants == []
    assert by_subject["Shape 1"].participants == ["просто строка"]
    assert by_subject["Shape 2"].participants == ["Иванов И.И.", "guest@example.local"]
    assert by_subject["Shape 3"].participants == ["noname@example.local"]
    assert by_subject["Shape 4"].participants == [str({"unknown_key": "x"})]
    assert by_subject["Shape 5"].participants == ["42"]
    assert by_subject["Shape 6"].participants == ["42", "Смешанный"]
    for m in passport.meetings:
        assert all(isinstance(p, str) for p in m.participants)


# =========================================================== responsibles ==


def test_responsibles_isolation_and_role_fallback(db: Session):
    from app.models.catalog import Responsible, UniversityResponsible

    uA = base_t._university(db, "Uni Resp A")
    uB = base_t._university(db, "Uni Resp B")
    r1 = Responsible(full_name="Роль Явная", email="r1-1102@example.local", role="contact")
    r2 = Responsible(full_name="Роль По Умолчанию", email="r2-1102@example.local", role="manager")
    r3 = Responsible(full_name="Чужой", email="r3-1102@example.local", role="dean")
    db.add_all([r1, r2, r3])
    db.flush()
    db.add(
        UniversityResponsible(
            university_id=uA.id, responsible_id=r1.id, role_in_university="dean", is_primary=True
        )
    )
    db.add(
        UniversityResponsible(
            university_id=uA.id, responsible_id=r2.id, role_in_university="", is_primary=False
        )
    )
    db.add(UniversityResponsible(university_id=uB.id, responsible_id=r3.id, is_primary=True))
    db.commit()

    passport = ps.get_passport(db, uA.id)
    by_email = {r.email: r for r in passport.responsibles}
    assert set(by_email) == {"r1-1102@example.local", "r2-1102@example.local"}
    assert by_email["r1-1102@example.local"].role == "dean"
    assert by_email["r2-1102@example.local"].role == "manager"  # fallback to role


# =============================================================== timeline ===


def test_timeline_sources_limit_order_via_passport(db: Session):
    u = base_t._university(db, "Uni Timeline Full")
    now = datetime.now(timezone.utc)
    for i in range(15):
        d = Document(
            university_id=u.id,
            document_type="act",
            title=f"TL Doc {i:02d}",
            file_path="p",
            file_name=f"{i}.pdf",
            file_size=5,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="a",
        )
        db.add(d)
        db.flush()
        d.created_at = now - timedelta(hours=i)
    for i in range(12):
        db.add(
            Meeting(
                university_id=u.id,
                subject=f"TL Meet {i:02d}",
                participants=[],
                meeting_at=now - timedelta(hours=30 + i),
                created_by_keycloak_sub="b",
            )
        )
    for i in range(8):
        n = InteractionNote(university_id=u.id, author_keycloak_sub="c", content=f"TL note {i:02d}")
        db.add(n)
        db.flush()
        n.created_at = now - timedelta(hours=60 + i)
    db.commit()
    db.expire_all()

    passport = ps.get_passport(db, u.id)
    tl = passport.last_interactions
    assert len(tl) == 10
    # the 15 documents are newer than every meeting/note, so the 10-slot
    # cap is filled with documents only — newest-first wins (production rule)
    assert {t.type for t in tl} == {"document"}
    times = [t.created_at for t in tl]
    assert times == sorted(times, reverse=True)
    # newest items win the 10-slot cap
    assert tl[0].title == "TL Doc 00"
    assert tl[-1].title == "TL Doc 09"

    # all three sources surface when the cap is not saturated by documents
    u2 = base_t._university(db, "Uni Timeline Sources")
    db.add(
        Document(
            university_id=u2.id,
            document_type="act",
            title="src doc",
            file_path="p",
            file_name="f.pdf",
            file_size=1,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="a",
        )
    )
    db.add(
        Meeting(
            university_id=u2.id,
            subject="src meet",
            participants=[],
            meeting_at=now,
            created_by_keycloak_sub="b",
        )
    )
    db.add(InteractionNote(university_id=u2.id, author_keycloak_sub="c", content="src note"))
    db.commit()
    tl2 = ps.get_passport(db, u2.id).last_interactions
    assert {t.type for t in tl2} >= {"meeting", "document", "note"}
    assert [t.created_at for t in tl2] == sorted([t.created_at for t in tl2], reverse=True)


def test_timeline_adds_no_queries(db: Session, select_counter):
    """Many interaction rows must not add SELECTs (timeline reuses block 7)."""
    u = base_t._university(db, "Uni TL Reuse")
    now = datetime.now(timezone.utc)
    db.add(
        Document(
            university_id=u.id,
            document_type="act",
            title="one",
            file_path="p",
            file_name="f.pdf",
            file_size=1,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="a",
        )
    )
    db.add(
        Meeting(
            university_id=u.id,
            subject="one",
            participants=[],
            meeting_at=now,
            created_by_keycloak_sub="b",
        )
    )
    db.commit()
    uid = u.id
    _, few_n = _counted(db, select_counter, ps.get_passport, db, uid)
    for i in range(19):
        db.add(
            Document(
                university_id=uid,
                document_type="act",
                title=f"m{i}",
                file_path="p",
                file_name=f"{i}.pdf",
                file_size=1,
                mime_type="application/pdf",
                uploaded_by_keycloak_sub="a",
            )
        )
    for i in range(9):
        db.add(
            Meeting(
                university_id=uid,
                subject=f"m{i}",
                participants=[],
                meeting_at=now - timedelta(hours=i + 1),
                created_by_keycloak_sub="b",
            )
        )
    for i in range(10):
        db.add(InteractionNote(university_id=uid, author_keycloak_sub="c", content=f"note {i}"))
    db.commit()
    _, many_n = _counted(db, select_counter, ps.get_passport, db, uid)
    assert (few_n, many_n) == (8, 8)


# =============================================================== timezone ===


def test_all_datetimes_tz_aware_with_includes(db: Session):
    u = base_t._seed_full(db)
    db.add(
        AuditEvent(
            user_id="1", entity_type="university", entity_id=uuid.uuid4(), action="update", university_id=u.id
        )
    )
    db.commit()
    uid = u.id
    passport = ps.get_passport(
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]),
    )
    assert passport.health_score is not None
    assert passport.health_score.calculated_at.tzinfo is not None
    assert len(passport.recent_audit or []) == 1
    assert passport.recent_audit[0].created_at.tzinfo is not None  # type: ignore[index]
    for d in passport.documents:
        assert d.created_at.tzinfo is not None
    for m in passport.meetings:
        assert m.meeting_at.tzinfo is not None
    for t in passport.last_interactions:
        assert t.created_at.tzinfo is not None


# ================================================================== empty ===


def test_empty_passport_http(engine, api_client):
    with Session(engine) as s:
        u = base_t._university(s, "Uni HTTP Empty")
        s.commit()
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    for block in (
        "programs",
        "teachers",
        "products",
        "licenses",
        "contracts",
        "documents",
        "meetings",
        "responsibles",
        "last_interactions",
    ):
        assert body[block] == [], block
    assert body["students_summary"]["total"] == 0
    assert body["students_summary"]["by_status"] == {}
    assert body["students_summary"]["by_program"] == []
    assert body["health_score"] is None
    assert body["recent_audit"] is None
    assert body["workflow_summary"]["progress_percent"] == 0.0
    UniversityPassport.model_validate(body)


# ============================================================== auth/rbac ===


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


def _mint(priv: str, kid: str, roles: list[str]) -> str:
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
        },
        priv,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _real_client(engine):
    """TestClient with real auth (no dev bypass)."""

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


@pytest.fixture()
def real_client(engine):
    yield from _real_client(engine)


def test_404_schema(engine, api_client):
    r = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport")
    assert r.status_code == 404
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


def test_403_guest_without_permission(engine, real_client, monkeypatch):
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    priv = _rsa_setup(monkeypatch, "p1102-guest")
    token = _mint(priv, "p1102-guest", ["guest"])
    for url in (
        f"/api/v1/universities/{uid}/passport",
        f"/api/v1/universities/{uid}/passport/programs",
        f"/api/v1/universities/{uid}/passport/teachers",
    ):
        r = real_client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, (url, r.text)


def test_401_missing_token(engine, real_client):
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    r = real_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r.json()["error"]["details"] == {}
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


# ============================================================ include edge ==


def test_include_http_edge_spellings(engine, api_client):
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    # empty / whitespace-only -> base passport
    for q in ("", "?include=", "?include=%20%20", "?include=,,"):
        r = api_client.get(f"/api/v1/universities/{uid}/passport{q}")
        assert r.status_code == 200, (q, r.text)
        body = r.json()
        assert body["health_score"] is None and body["recent_audit"] is None
    # trailing comma tolerated (production parser skips empty segments)
    r = api_client.get(f"/api/v1/universities/{uid}/passport?include=health_score,")
    assert r.status_code == 200, r.text
    assert r.json()["health_score"] is not None


def test_audit_tiebreak_id_desc(db: Session):
    """Same-second timestamps order deterministically by id DESC (production)."""
    uA = base_t._university(db, "Uni Tie A")
    uB = base_t._university(db, "Uni Tie B")
    db.commit()
    same = datetime.now(timezone.utc)
    for i in range(3):
        db.add(
            AuditEvent(
                user_id="1",
                entity_type="university",
                entity_id=uuid.uuid4(),
                action=f"A-{i}",
                university_id=uA.id,
            )
        )
    for i in range(2):
        db.add(
            AuditEvent(
                user_id="2",
                entity_type="university",
                entity_id=uuid.uuid4(),
                action=f"B-{i}",
                university_id=uB.id,
            )
        )
    db.commit()
    for ev in db.execute(select(AuditEvent)).scalars().all():
        ev.created_at = same
    db.commit()
    rows = ps.get_recent_audit(db, uA.id)
    assert {e.action for e in rows} == {"A-2", "A-1", "A-0"}
    ids = [e.id for e in rows]
    assert ids == sorted(ids, reverse=True)


def test_audit_isolation_http(engine, api_client):
    with Session(engine) as s:
        uA = base_t._seed_full(s)
        uB = base_t._university(s, "Uni Audit Other")
        s.commit()
        uid_a, uid_b = str(uA.id), str(uB.id)
        for i in range(3):
            s.add(
                AuditEvent(
                    user_id="1",
                    entity_type="university",
                    entity_id=uuid.uuid4(),
                    action=f"A-{i}",
                    university_id=uA.id,
                )
            )
        for i in range(4):
            s.add(
                AuditEvent(
                    user_id="2",
                    entity_type="university",
                    entity_id=uuid.uuid4(),
                    action=f"B-{i}",
                    university_id=uB.id,
                )
            )
        s.commit()
    r = api_client.get(f"/api/v1/universities/{uid_a}/passport?include=audit")
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in r.json()["recent_audit"]]
    assert set(actions) == {"A-2", "A-1", "A-0"}
    ids = [e["id"] for e in r.json()["recent_audit"]]
    assert ids == sorted(ids, reverse=True)
    assert not any(a.startswith("B-") for a in actions)
    assert uid_b  # other university exists but leaks nothing


# ======================================================= base error prop ===


def test_base_error_not_masked_by_graceful_degradation(engine, api_client, monkeypatch):
    """A base pipeline failure with ?include=... must NOT degrade to 200."""

    def _boom(db, university_id):
        raise RuntimeError("base pipeline down")

    monkeypatch.setattr(ps, "_load_program_rows", _boom)
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    # NOTE: the shared api_client re-raises server exceptions; a dedicated
    # client surfacing the real HTTP 500 is needed here (same app/overrides).
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(f"/api/v1/universities/{uid}/passport?include=health_score,audit")
    assert r.status_code == 500, r.text
    assert r.status_code != 200


# ========================================================= query counts ====


def test_exact_query_counts_8_8_9_9(db: Session, select_counter):
    """Acceptance gate: exact SELECT counts on a deterministic dataset."""
    u = base_t._seed_full(db)
    uid = u.id
    db.add(
        AuditEvent(
            user_id="1", entity_type="university", entity_id=uuid.uuid4(), action="update", university_id=uid
        )
    )
    db.commit()
    _, base = _counted(db, select_counter, ps.get_passport, db, uid)
    _, health = _counted(
        db,
        select_counter,
        ps.get_passport,
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE]),
    )
    _, audit = _counted(
        db, select_counter, ps.get_passport, db, uid, include=frozenset([ps.PassportInclude.AUDIT])
    )
    _, both = _counted(
        db,
        select_counter,
        ps.get_passport,
        db,
        uid,
        include=frozenset([ps.PassportInclude.HEALTH_SCORE, ps.PassportInclude.AUDIT]),
    )
    print(f"\nP1-11-02 query counts: base={base} health={health} audit={audit} both={both}")
    assert (base, health, audit, both) == (8, 8, 9, 9)


def test_scaling_counts_stable_and_audit_row_independent(db: Session, select_counter):
    u = perf._seed_small(db)
    uid = u.id
    _, small = _counted(db, select_counter, ps.get_passport, db, uid)
    perf._seed_large(db, u)
    for i in range(25):
        db.add(
            AuditEvent(
                user_id="1",
                entity_type="university",
                entity_id=uuid.uuid4(),
                action=f"bulk-{i}",
                university_id=uid,
            )
        )
    db.commit()
    _, large = _counted(db, select_counter, ps.get_passport, db, uid)
    _, large_audit = _counted(
        db, select_counter, ps.get_passport, db, uid, include=frozenset([ps.PassportInclude.AUDIT])
    )
    print(f"\nP1-11-02 scaling: small={small} large={large} large_audit={large_audit}")
    assert (small, large) == (8, 8)
    assert large_audit == large + 1  # +1 regardless of 25 audit rows


# =========================================================== performance ===


def test_latency_budget_on_reused_demo_dataset(engine):
    """<500 ms gate on the existing demo seed (no second seed written)."""
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
    with Session(engine) as s:
        ps.get_passport(s, uni_id)  # warmup
        s.expire_all()
        t0 = time.perf_counter()
        ps.get_passport(s, uni_id)
        cold_ms = (time.perf_counter() - t0) * 1000
        warms = []
        for _ in range(10):
            s.expire_all()
            t0 = time.perf_counter()
            ps.get_passport(s, uni_id)
            warms.append((time.perf_counter() - t0) * 1000)
        median_ms = statistics.median(warms)
        max_ms = max(warms)
        print(
            f"\nP1-11-02 latency (dialect={engine.dialect.name}): "
            f"cold={cold_ms:.1f}ms median={median_ms:.1f}ms max={max_ms:.1f}ms"
        )
        assert median_ms < 500, median_ms
        assert max_ms < 500, warms


# =========================================================== pagination ====


def test_pagination_content_no_overlap_readiness_links(engine, api_client):
    with Session(engine) as s:
        u = perf._seed_large(s)
        uid = str(u.id)
    p1 = api_client.get(f"/api/v1/universities/{uid}/passport/programs?page=1&page_size=5")
    p2 = api_client.get(f"/api/v1/universities/{uid}/passport/programs?page=2&page_size=5")
    assert p1.status_code == 200 and p2.status_code == 200
    b1, b2 = p1.json(), p2.json()
    assert b1["total"] == b2["total"] >= 10
    assert len(b1["items"]) == 5 and len(b2["items"]) == 5
    assert {p["id"] for p in b1["items"]} & {p["id"] for p in b2["items"]} == set()
    for item in b1["items"]:
        for field in (
            "id",
            "name",
            "direction_name",
            "status",
            "launch_date",
            "responsible_name",
            "teachers_count",
            "students_count",
        ):
            assert field in item, field

    t1 = api_client.get(f"/api/v1/universities/{uid}/passport/teachers?page=1&page_size=5")
    t2 = api_client.get(f"/api/v1/universities/{uid}/passport/teachers?page=2&page_size=5")
    assert t1.status_code == 200 and t2.status_code == 200
    tb1, tb2 = t1.json(), t2.json()
    assert tb1["total"] >= 20
    assert {t["id"] for t in tb1["items"]} & {t["id"] for t in tb2["items"]} == set()
    assert tb1["items"][0]["readiness"] in ("ready", "attention", "expired")
    assert isinstance(tb1["items"][0]["programs"], list)


def test_pagination_validation_404_and_budgets(engine, api_client, db, select_counter):
    u = perf._seed_small(db)
    uid = str(u.id)
    for bad in ("page=0", "page_size=0", "page_size=101"):
        for res in ("programs", "teachers"):
            r = api_client.get(f"/api/v1/universities/{uid}/passport/{res}?{bad}")
            assert r.status_code == 422, (res, bad, r.text)
    missing = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport/programs")
    assert missing.status_code == 404
    missing_t = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport/teachers")
    assert missing_t.status_code == 404

    u2 = perf._seed_large(db, u)
    uid2 = u2.id
    _, n5 = _counted(db, select_counter, ps.get_programs_page, db, uid2, 1, 5)
    _, n20 = _counted(db, select_counter, ps.get_programs_page, db, uid2, 1, 20)
    _, t5 = _counted(db, select_counter, ps.get_teachers_page, db, uid2, 1, 5)
    _, t20 = _counted(db, select_counter, ps.get_teachers_page, db, uid2, 1, 20)
    print(f"\nP1-11-02 pagination budgets: programs({n5},{n20}) teachers({t5},{t20})")
    assert n5 == n20 == 4
    assert t5 == t20 == 4
    empty_items, empty_total = ps.get_teachers_page(db, uid2, 99, 5)
    assert empty_items == [] and empty_total >= 20


# ============================================== teacher passport discovery ==


def test_teacher_passport_production_present():
    """Production pin (§54, P1-05 shipped): Teacher Passport endpoint exists.

    ``GET /api/v1/teachers/{id}/passport`` is mounted via the UUID-native
    ``app.modules.teachers.passport_router``; the legacy int-PK teachers
    CRUD router stays unmounted; the ``TeacherPassport`` DTO lives in the
    new ``passport_schemas`` module; readiness reuses the canonical
    ``compute_teacher_readiness`` helper (no second formula); no invented
    ``allowed_programs`` contract.
    """
    import app.modules.teachers.passport_router as teacher_passport_router
    import app.modules.teachers.passport_schemas as teacher_passport_schemas
    import app.modules.teachers.passport_service as teacher_passport_service
    import app.modules.teachers.router as teachers_router
    import app.modules.teachers.schemas as teachers_schemas
    import app.modules.universities.passport_schemas as uni_schemas
    from app.services.teacher_readiness import compute_teacher_readiness

    legacy_paths = sorted(getattr(route, "path", "") for route in teachers_router.router.routes)
    assert not any("passport" in p for p in legacy_paths), legacy_paths

    # Version-robust walk restoring the pre-0.120 flat full paths
    # (FastAPI>=0.120 nests included routers; nested routes already carry
    # their immediate router prefix, so collapse doubled segments on "/"
    # boundaries instead of inventing routes).
    def _join(prefix: str, path: str) -> str:
        if not prefix or not path.startswith("/"):
            return f"{prefix}{path}" if prefix else path
        pre = [s for s in prefix.split("/") if s != ""]
        parts = [s for s in path.split("/") if s != ""]
        overlap = 0
        for k in range(min(len(pre), len(parts)), 0, -1):
            if pre[-k:] == parts[:k]:
                overlap = k
                break
        return "/" + "/".join(pre + parts[overlap:])

    def _walk(routes, prefix=""):
        for r in routes:
            path = getattr(r, "path", None)
            if path:
                yield _join(prefix, path)
                continue
            original = getattr(r, "original_router", None)
            if original is not None:
                yield from _walk(
                    getattr(original, "routes", []) or [],
                    _join(prefix, getattr(original, "prefix", "") or ""),
                )
            elif getattr(r, "routes", None):
                yield from _walk(r.routes, prefix)

    mounted = sorted(_walk(app.routes))
    teacher_passport = [p for p in mounted if p.startswith("/api/v1/teachers") and "passport" in p]
    assert teacher_passport == ["/api/v1/teachers/{teacher_id}/passport"], teacher_passport

    assert hasattr(teacher_passport_schemas, "TeacherPassport")
    assert not hasattr(teachers_schemas, "TeacherPassport")
    assert not hasattr(uni_schemas, "TeacherPassport")

    assert teacher_passport_service.compute_teacher_readiness is compute_teacher_readiness
    assert "passport" in teacher_passport_router.router.prefix or any(
        "passport" in getattr(route, "path", "") for route in teacher_passport_router.router.routes
    )

    import app.modules.teachers.models as teachers_models

    for mod in (teachers_router, teachers_schemas, teachers_models, ps, uni_schemas):
        assert "allowed_programs" not in dir(mod), mod.__name__


# ================================================================ openapi ===


def test_openapi_passport_paths(api_client):
    r = api_client.get("/openapi.json")
    assert r.status_code == 200, r.text
    paths = r.json()["paths"]
    assert "/api/v1/universities/{university_id}/passport" in paths
    assert "/api/v1/universities/{university_id}/passport/programs" in paths
    assert "/api/v1/universities/{university_id}/passport/teachers" in paths
    assert "/api/v1/teachers/{teacher_id}/passport" in paths  # P1-05 shipped (§54)


# ==================================================== error handler coexist ==


def test_central_409_handler_coexists_with_passport_codes(engine, api_client):
    """P1-11-01 IntegrityError->409 mapping intact; 404/403/422 unaffected."""

    boom = FastAPI()
    register_error_handlers(boom)

    class Item(BaseModel):
        name: str

    @boom.post("/boom")
    def _boom():
        from sqlalchemy.exc import IntegrityError as _IE

        raise _IE(
            "INSERT INTO t ...", {}, Exception("duplicate key value violates unique constraint")
        )

    c = TestClient(boom)
    r = c.post("/boom")
    assert r.status_code == 409
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "CONFLICT"

    assert api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport").status_code == 404
    with Session(engine) as s:
        u = base_t._seed_full(s)
        uid = str(u.id)
    assert api_client.get(f"/api/v1/universities/{uid}/passport?include=nope").status_code == 422
    assert (
        api_client.get(f"/api/v1/universities/{uid}/passport/programs?page_size=0").status_code
        == 422
    )
