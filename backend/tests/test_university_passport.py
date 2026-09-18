"""P1-04-01/02/03/04 passport tests (SQLite by default, PG via TEST_DATABASE_URL).

Covers: programs array, teachers + readiness (ready/attention/expired),
students total/active/graduated/by_program, empty university, N+1 guard,
products + nested license, license without contract, derived status +
days_to_expiry boundaries, license/contract sorting, empty arrays, vendor
resolution, no stored derived status, docs/meetings limits + sorting,
participants coercion, multiple responsibles, timeline merge + sort,
tz-aware datetimes, endpoint 200/404/403 + schema validation.
"""

import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
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
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.modules.universities import passport_service as ps
from app.modules.universities.passport_schemas import UniversityPassport

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine(tmp_path):
    url = TEST_URL
    if url == "sqlite://":
        url = f"sqlite:///{tmp_path}/passport_test.db"
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
def query_counter(engine):
    count = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            count["n"] += 1

    yield count
    event.remove(engine, "before_cursor_execute", _count)


# ------------------------------------------------------------ builders ---


def _catalog(db: Session, tag: str):
    d = ITDirection(code=f"DIR-{tag}", name=f"Direction {tag}")
    db.add(d)
    db.flush()
    p1 = ITProgram(direction_id=d.id, name=f"Program {tag}-1", description="")
    p2 = ITProgram(direction_id=d.id, name=f"Program {tag}-2", description="")
    v = Vendor(name=f"Vendor {tag}")
    db.add_all([p1, p2, v])
    db.flush()
    prod = ITProduct(vendor_id=v.id, name=f"Product {tag}", version="1.0")
    db.add(prod)
    db.flush()
    return d, p1, p2, v, prod


def _university(db: Session, name: str) -> University:
    u = University(name=name, city="Москва")
    db.add(u)
    db.flush()
    return u


def _teacher(
    db: Session,
    uni: University,
    email: str,
    certs: list[dict],
    programs: list[ITProgram] | None = None,
) -> Teacher:
    t = Teacher(university_id=uni.id, full_name=f"Teacher {email}", email=email, position="доцент")
    db.add(t)
    db.flush()
    for c in certs:
        db.add(
            TeacherCertificate(
                teacher_id=t.id,
                certificate_name=c.get("name", "Обязательный"),
                issued_by="АНО ДПО",
                issued_at=date.today() - timedelta(days=400),
                expires_at=c.get("expires_at"),
                is_mandatory=c.get("is_mandatory", True),
                program_id=None,
                document_ref=None,
            )
        )
    db.add(
        TeacherQualification(
            teacher_id=t.id,
            qualification_name="ПК ППС",
            obtained_at=date.today() - timedelta(days=400),
            expires_at=date.today() + timedelta(days=300),
        )
    )
    for p in programs or []:
        db.add(
            TeacherProgram(
                teacher_id=t.id, program_id=p.id, can_teach=True, assigned_at=date.today()
            )
        )
    db.flush()
    return t


# ============================================================ P1-04-02 ---


def test_programs_array_with_counts(db: Session):
    _, p1, p2, _, _ = _catalog(db, "prog")
    u = _university(db, "Uni Prog")
    r = Responsible(full_name="Ответственный О.О.", email="resp-prog@example.local", role="dean")
    db.add(r)
    db.flush()
    db.add(
        UniversityProgram(
            university_id=u.id,
            program_id=p1.id,
            status="launched",
            launch_date=date.today() - timedelta(days=10),
            responsible_id=r.id,
        )
    )
    db.add(UniversityProgram(university_id=u.id, program_id=p2.id, status="planned"))
    _teacher(db, u, "t1@example.local", [{"expires_at": date.today() + timedelta(days=400)}], [p1])
    _teacher(
        db, u, "t2@example.local", [{"expires_at": date.today() + timedelta(days=400)}], [p1, p2]
    )
    for i in range(3):
        db.add(
            Student(
                external_id=f"ST-P-{i}",
                university_id=u.id,
                program_id=p1.id,
                full_name=f"С {i}",
                started_at=date.today(),
            )
        )
    db.add(
        Student(
            external_id="ST-P-9",
            university_id=u.id,
            program_id=p2.id,
            full_name="С 9",
            started_at=date.today(),
            status="graduated",
            finished_at=date.today() - timedelta(days=1),
        )
    )
    db.commit()

    programs = ps.get_programs(db, u.id)
    assert len(programs) == 2
    by_name = {p.name: p for p in programs}
    assert by_name[p1.name].direction_name == "Direction prog"
    assert by_name[p1.name].teachers_count == 2
    assert by_name[p1.name].students_count == 3
    assert by_name[p1.name].responsible_name == "Ответственный О.О."
    assert by_name[p1.name].launch_date is not None
    assert by_name[p2.name].teachers_count == 1
    assert by_name[p2.name].students_count == 1
    assert by_name[p2.name].responsible_name is None


def test_teachers_and_readiness_matrix(db: Session):
    _, p1, _, _, _ = _catalog(db, "tch")
    u = _university(db, "Uni Teach")
    today = date.today()
    _teacher(db, u, "ready@example.local", [{"expires_at": today + timedelta(days=400)}], [p1])
    _teacher(db, u, "attention@example.local", [{"expires_at": today + timedelta(days=10)}], [p1])
    _teacher(db, u, "expired@example.local", [{"expires_at": today - timedelta(days=5)}], [p1])
    _teacher(
        db,
        u,
        "nocert@example.local",
        [{"expires_at": today + timedelta(days=500), "is_mandatory": False, "name": "Soft"}],
        [p1],
    )
    db.commit()

    teachers = ps.get_teachers(db, u.id)
    assert len(teachers) == 4
    by_email = {t.email: t for t in teachers}
    assert by_email["ready@example.local"].readiness == TeacherReadiness.READY
    assert by_email["attention@example.local"].readiness == TeacherReadiness.ATTENTION
    assert by_email["expired@example.local"].readiness == TeacherReadiness.EXPIRED
    assert by_email["nocert@example.local"].readiness == TeacherReadiness.READY
    assert by_email["ready@example.local"].next_qualification_date is not None
    assert len(by_email["ready@example.local"].programs) == 1
    assert by_email["ready@example.local"].programs[0].name == p1.name


def test_students_summary_totals_and_by_program(db: Session):
    _, p1, p2, _, _ = _catalog(db, "stu")
    u = _university(db, "Uni Stu")
    today = date.today()
    for i in range(4):
        db.add(
            Student(
                external_id=f"SS-A-{i}",
                university_id=u.id,
                program_id=p1.id,
                full_name=f"A {i}",
                started_at=today,
                status="active",
            )
        )
    for i in range(2):
        db.add(
            Student(
                external_id=f"SS-G-{i}",
                university_id=u.id,
                program_id=p1.id,
                full_name=f"G {i}",
                started_at=today,
                status="graduated",
                finished_at=today,
            )
        )
    for i in range(3):
        db.add(
            Student(
                external_id=f"SS-B-{i}",
                university_id=u.id,
                program_id=p2.id,
                full_name=f"B {i}",
                started_at=today,
                status="active",
            )
        )
    db.commit()

    summary = ps.get_students_summary(db, u.id)
    assert summary.total == 9
    assert summary.active == 7
    assert summary.graduated == 2
    assert summary.by_status["active"] == 7
    assert summary.by_status["graduated"] == 2
    assert len(summary.by_program) == 2
    row = next(r for r in summary.by_program if r.program_id == p1.id)
    assert (row.total, row.active, row.graduated) == (6, 4, 2)


def test_empty_university(db: Session):
    u = _university(db, "Uni Empty")
    db.commit()
    assert ps.get_programs(db, u.id) == []
    assert ps.get_teachers(db, u.id) == []
    summary = ps.get_students_summary(db, u.id)
    assert summary.total == 0 and summary.by_program == []
    products, licenses, contracts = ps.get_products_licenses_contracts(db, u.id)
    assert products == [] and licenses == [] and contracts == []
    assert ps.get_documents(db, u.id) == []
    assert ps.get_meetings(db, u.id) == []
    assert ps.get_responsibles(db, u.id) == []
    assert ps.get_timeline(db, u.id) == []
    passport = ps.get_passport(db, u.id)
    assert passport.students_summary.total == 0
    assert passport.last_interactions == []


def test_no_n_plus_1_programs(db: Session, query_counter):
    _, p1, p2, _, _ = _catalog(db, "n1")
    u = _university(db, "Uni N1")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="active"))
    db.add(UniversityProgram(university_id=u.id, program_id=p2.id, status="active"))
    for i in range(6):
        _teacher(
            db,
            u,
            f"n1-{i}@example.local",
            [{"expires_at": date.today() + timedelta(days=400)}],
            [p1 if i % 2 == 0 else p2],
        )
        db.add(
            Student(
                external_id=f"N1-{i}",
                university_id=u.id,
                program_id=p1.id,
                full_name=f"N {i}",
                started_at=date.today(),
            )
        )
    db.commit()
    # NOTE: capture uid before touching expired attributes — accessing
    # ``u.id`` after commit would refresh the University row (+ selectin
    # load of university_responsibles) and pollute the query count.
    uid = u.id
    db.expire_all()

    query_counter["n"] = 0
    ps.get_programs(db, uid)
    first = query_counter["n"]
    assert first <= 3, f"programs took {first} queries"

    for i in range(6, 12):
        _teacher(
            db,
            u,
            f"n1-{i}@example.local",
            [{"expires_at": date.today() + timedelta(days=400)}],
            [p1],
        )
    db.commit()
    uid = u.id
    db.expire_all()
    query_counter["n"] = 0
    ps.get_programs(db, uid)
    second = query_counter["n"]
    assert second == first, f"N+1: {first} -> {second} queries"


def test_passport_query_count_bounded(db: Session, engine, query_counter):
    _, p1, _, _, _ = _catalog(db, "qc")
    u = _university(db, "Uni QC")
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="active"))
    _teacher(db, u, "qc@example.local", [{"expires_at": date.today() + timedelta(days=400)}], [p1])
    db.add(
        Student(
            external_id="QC-1",
            university_id=u.id,
            program_id=p1.id,
            full_name="К",
            started_at=date.today(),
        )
    )
    db.add(
        Document(
            university_id=u.id,
            document_type="act",
            title="T",
            file_path="p",
            file_name="f.pdf",
            file_size=10,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="s",
        )
    )
    db.add(
        Meeting(
            university_id=u.id,
            subject="S",
            participants=[],
            meeting_at=datetime.now(timezone.utc),
            created_by_keycloak_sub="s",
        )
    )
    db.commit()

    query_counter["n"] = 0
    passport = ps.get_passport(db, u.id)
    assert passport.university.name == "Uni QC"
    assert query_counter["n"] <= 20, f"passport took {query_counter['n']} queries"


# ============================================================ P1-04-03 ---


def _license_setup(db: Session, tag: str):
    _, _, _, v, prod = _catalog(db, tag)
    u = _university(db, f"Uni Lic {tag}")
    return u, prod, v


def test_products_with_nested_license(db: Session):
    u, prod, v = _license_setup(db, "pl")
    today = date.today()
    c = Contract(
        university_id=u.id,
        contract_number=f"DOG-PL-{uuid.uuid4().hex[:6]}",
        product_id=prod.id,
        signed_at=today - timedelta(days=100),
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
        license_number="LIC-PL-1",
        signed_at=today - timedelta(days=90),
        expires_at=today + timedelta(days=200),
        transfer_status_raw="accepted",
    )
    db.add(lic)
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id, product_id=prod.id, license_id=lic.id, status="active"
        )
    )
    db.commit()

    products, licenses, contracts = ps.get_products_licenses_contracts(db, u.id)
    assert len(products) == 1
    assert products[0].vendor_name == v.name
    assert products[0].license is not None
    assert products[0].license.license_number == "LIC-PL-1"
    assert products[0].license.contract_number == c.contract_number
    assert products[0].license.vendor_name == v.name
    assert len(licenses) == 1 and len(contracts) == 1
    assert contracts[0].vendor_name == v.name


def test_license_without_contract(db: Session):
    u, prod, _ = _license_setup(db, "nc")
    today = date.today()
    lic = License(
        university_id=u.id,
        product_id=prod.id,
        contract_id=None,
        license_number="LIC-NC-1",
        signed_at=today - timedelta(days=10),
        expires_at=today + timedelta(days=100),
        transfer_status_raw="pending",
    )
    db.add(lic)
    db.flush()
    db.add(
        UniversityProduct(
            university_id=u.id, product_id=prod.id, license_id=lic.id, status="active"
        )
    )
    db.commit()

    _, licenses, _ = ps.get_products_licenses_contracts(db, u.id)
    assert licenses[0].contract_number is None


def test_license_derived_status_boundaries(db: Session):
    u, prod, _ = _license_setup(db, "bd")
    today = date.today()
    for i, delta in enumerate([-1, 0, 1, 29, 30, 31]):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=None,
                license_number=f"LIC-BD-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=delta),
                transfer_status_raw="accepted",
            )
        )
    db.commit()
    _, licenses, _ = ps.get_products_licenses_contracts(db, u.id)
    by_number = {lic.license_number: lic for lic in licenses}
    assert by_number["LIC-BD-0"].status == "expired"
    assert by_number["LIC-BD-0"].days_to_expiry == -1
    for suffix in ("LIC-BD-1", "LIC-BD-2", "LIC-BD-3", "LIC-BD-4"):
        assert by_number[suffix].status == "expires_soon", suffix
    assert by_number["LIC-BD-1"].days_to_expiry == 0
    assert by_number["LIC-BD-5"].status == "active"
    assert by_number["LIC-BD-5"].days_to_expiry == 31


def test_licenses_sorted_by_expiry_contracts_by_signed_desc(db: Session):
    u, prod, _ = _license_setup(db, "sort")
    today = date.today()
    for i, delta in enumerate([100, 5, 50]):
        db.add(
            License(
                university_id=u.id,
                product_id=prod.id,
                contract_id=None,
                license_number=f"LIC-S-{i}",
                signed_at=today - timedelta(days=10),
                expires_at=today + timedelta(days=delta),
                transfer_status_raw="accepted",
            )
        )
    for i, back in enumerate([10, 100, 50]):
        db.add(
            Contract(
                university_id=u.id,
                contract_number=f"DOG-S-{i}",
                signed_at=today - timedelta(days=back),
                expires_at=today + timedelta(days=300),
                status_raw="signed",
                transfer_status_raw="accepted",
            )
        )
    db.commit()
    _, licenses, contracts = ps.get_products_licenses_contracts(db, u.id)
    expiries = [lic.expires_at for lic in licenses]
    assert expiries == sorted(expiries), "licenses must be expires_at ASC"
    signed = [c.signed_at for c in contracts]
    assert signed == sorted(signed, reverse=True), "contracts signed_at DESC"


def test_framework_contract_vendor_empty_and_derived_not_stored(db: Session):
    u, _, _ = _license_setup(db, "fw")
    today = date.today()
    db.add(
        Contract(
            university_id=u.id,
            contract_number="DOG-FW-1",
            product_id=None,
            signed_at=today - timedelta(days=5),
            expires_at=today + timedelta(days=500),
            status_raw="signed",
            transfer_status_raw="transferred",
        )
    )
    db.commit()
    _, _, contracts = ps.get_products_licenses_contracts(db, u.id)
    assert contracts[0].vendor_name == ""

    cols = set(License.__table__.columns.keys())
    assert "status" not in cols and "derived_status" not in cols
    cols_c = set(Contract.__table__.columns.keys())
    assert "derived_status" not in cols_c


# ============================================================ P1-04-04 ---


def test_documents_limit_and_sort(db: Session):
    u = _university(db, "Uni Docs")
    base = datetime.now(timezone.utc)
    for i in range(25):
        db.add(
            Document(
                university_id=u.id,
                document_type="act",
                title=f"Doc {i:02d}",
                file_path=f"p/{i}",
                file_name=f"{i}.pdf",
                file_size=100 + i,
                mime_type="application/pdf",
                uploaded_by_keycloak_sub="seed",
            )
        )
    db.commit()
    # stagger created_at to enforce ordering
    rows = db.execute(select(Document).where(Document.university_id == u.id)).scalars().all()
    for i, d in enumerate(sorted(rows, key=lambda x: x.title)):
        d.created_at = base - timedelta(days=i)
    db.commit()

    docs = ps.get_documents(db, u.id)
    assert len(docs) == 20
    created = [d.created_at for d in docs]
    assert created == sorted(created, reverse=True)
    assert all(d.created_at.tzinfo is not None for d in docs)


def test_meetings_limit_sort_participants(db: Session):
    u = _university(db, "Uni Meet")
    base = datetime.now(timezone.utc)
    for i in range(12):
        db.add(
            Meeting(
                university_id=u.id,
                subject=f"Meet {i:02d}",
                participants=[{"name": f"Человек {i}", "role": "Ректор"}, "guest@example.local"],
                meeting_at=base - timedelta(days=i),
                created_by_keycloak_sub="mgr",
            )
        )
    db.commit()
    meetings = ps.get_meetings(db, u.id)
    assert len(meetings) == 10
    times = [m.meeting_at for m in meetings]
    assert times == sorted(times, reverse=True)
    assert meetings[0].participants == ["Человек 0", "guest@example.local"]
    assert all(isinstance(p, str) for m in meetings for p in m.participants)
    assert all(m.meeting_at.tzinfo is not None for m in meetings)


def test_multiple_responsibles(db: Session):
    u = _university(db, "Uni Resp")
    ids = []
    for i in range(3):
        r = Responsible(
            full_name=f"Контакт {i}",
            email=f"resp-{uuid.uuid4().hex[:8]}@example.local",
            role="contact",
        )
        db.add(r)
        db.flush()
        ids.append(r.id)
        db.add(
            UniversityResponsible(
                university_id=u.id,
                responsible_id=r.id,
                role_in_university="dean" if i == 0 else "manager",
                is_primary=(i == 0),
            )
        )
    db.commit()
    resps = ps.get_responsibles(db, u.id)
    assert len(resps) == 3
    assert resps[0].role in ("dean", "manager", "contact")


def test_timeline_merge_and_sort(db: Session):
    u = _university(db, "Uni Timeline")
    now = datetime.now(timezone.utc)
    db.add(
        Document(
            university_id=u.id,
            document_type="protocol",
            title="Doc TL",
            file_path="p",
            file_name="d.pdf",
            file_size=5,
            mime_type="application/pdf",
            uploaded_by_keycloak_sub="a",
        )
    )
    db.add(
        Meeting(
            university_id=u.id,
            subject="Meet TL",
            participants=[],
            meeting_at=now - timedelta(hours=1),
            created_by_keycloak_sub="b",
        )
    )
    db.add(InteractionNote(university_id=u.id, author_keycloak_sub="c", content="Заметка TL"))
    db.commit()
    docs = ps.get_documents(db, u.id)
    meetings = ps.get_meetings(db, u.id)
    timeline = ps.get_timeline(db, u.id, docs, meetings)
    assert 1 <= len(timeline) <= 10
    kinds = {t.type for t in timeline}
    assert {"meeting", "document", "note"} <= kinds
    times = [t.created_at for t in timeline]
    assert times == sorted(times, reverse=True)
    assert all(t.created_at.tzinfo is not None for t in timeline)
    assert ps.get_workflow_transitions(db, u.id) == []  # P2 not yet wired


# ============================================================ P1-04-01 ---


def _seed_full(db: Session) -> University:
    _, p1, _, v, prod = _catalog(db, "full")
    u = _university(db, "Uni Full Passport")
    db.add(
        UniversityProgram(
            university_id=u.id, program_id=p1.id, status="launched", launch_date=date.today()
        )
    )
    _teacher(
        db, u, "full-t@example.local", [{"expires_at": date.today() + timedelta(days=400)}], [p1]
    )
    db.add(
        Student(
            external_id="FULL-1",
            university_id=u.id,
            program_id=p1.id,
            full_name="С Полный",
            started_at=date.today(),
        )
    )
    today = date.today()
    c = Contract(
        university_id=u.id,
        contract_number="DOG-FULL-1",
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
        license_number="LIC-FULL-1",
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
    r = Responsible(
        full_name="Полный Контакт", email=f"full-{uuid.uuid4().hex[:8]}@example.local", role="dean"
    )
    db.add(r)
    db.flush()
    db.add(UniversityResponsible(university_id=u.id, responsible_id=r.id, is_primary=True))
    db.add(
        Document(
            university_id=u.id,
            document_type="act",
            title="Full doc",
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
            subject="Full meet",
            participants=[],
            meeting_at=datetime.now(timezone.utc),
            created_by_keycloak_sub="s",
        )
    )
    db.add(InteractionNote(university_id=u.id, author_keycloak_sub="s", content="Full note"))
    db.commit()
    return u


def _client_with_db(engine):
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


@pytest.fixture()
def api_client(engine):
    yield from _client_with_db(engine)


def test_endpoint_200_full_structure(engine, api_client):
    with Session(engine) as s:
        u = _seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    for block in (
        "university",
        "programs",
        "teachers",
        "students_summary",
        "products",
        "licenses",
        "contracts",
        "documents",
        "meetings",
        "responsibles",
        "workflow_summary",
        "last_interactions",
    ):
        assert block in body, f"missing block {block}"
    assert body["programs"][0]["teachers_count"] >= 1
    assert body["students_summary"]["total"] >= 1
    assert body["students_summary"]["by_status"]["active"] >= 1
    assert body["licenses"][0]["days_to_expiry"] is not None
    UniversityPassport.model_validate(body)  # Pydantic validation
    assert body["workflow_summary"]["progress_percent"] == 0.0


def test_endpoint_empty_collections(engine, api_client):
    with Session(engine) as s:
        u = _university(s, "Uni API Empty")
        s.commit()
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["programs"] == [] and body["contracts"] == []
    assert body["students_summary"]["total"] == 0


def test_endpoint_404(engine, api_client):
    r = api_client.get(f"/api/v1/universities/{uuid.uuid4()}/passport")
    assert r.status_code == 404


def test_endpoint_403_for_role_without_permission(engine):
    """Valid JWT whose realm roles grant nothing -> 403 (not 401)."""
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
                "kid": "t403",
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
            u = _seed_full(s)
            uid = str(u.id)
        now = datetime.now(timezone.utc)
        claims = {
            "sub": "00000000-0000-0000-0000-000000000000",
            "preferred_username": "guest",
            "realm_access": {"roles": ["guest"]},  # unknown role -> no permissions
            "iss": settings.keycloak_issuer,
            "aud": settings.keycloak_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        token = _jwt.encode(claims, priv, algorithm="RS256", headers={"kid": "t403"})
        with TestClient(app) as client:
            denied = client.get(
                f"/api/v1/universities/{uid}/passport",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert denied.status_code == 403, denied.text
            ok_claims = dict(claims)
            ok_claims["realm_access"] = {"roles": ["manager"]}
            ok_token = _jwt.encode(ok_claims, priv, algorithm="RS256", headers={"kid": "t403"})
            ok = client.get(
                f"/api/v1/universities/{uid}/passport",
                headers={"Authorization": f"Bearer {ok_token}"},
            )
            assert ok.status_code == 200, ok.text
    finally:
        sec._fetch_jwks = orig_fetch
        sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
        settings.keycloak_issuer, settings.keycloak_audience = orig_issuer, orig_aud
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = False


def test_endpoint_uses_service_layer(engine, api_client, monkeypatch):
    """Route must delegate to the service (no SQL/business logic in route)."""
    import app.modules.universities.passport_router as router_mod

    calls: list = []
    real = router_mod.get_passport

    def _spy(db, university_id, *args, **kwargs):
        calls.append(university_id)
        return real(db, university_id, *args, **kwargs)

    monkeypatch.setattr(router_mod, "get_passport", _spy)
    with Session(engine) as s:
        u = _seed_full(s)
        uid = str(u.id)
    r = api_client.get(f"/api/v1/universities/{uid}/passport")
    assert r.status_code == 200, r.text
    assert len(calls) == 1 and str(calls[0]) == uid
