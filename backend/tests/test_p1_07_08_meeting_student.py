"""P1-07-01 (Meeting) + P1-08-01 (Student) PostgreSQL constraint tests.

Proves the REAL PostgreSQL contract from the canonical SQL migrations
(``backend/migrations/000004_students_links.up.sql``,
``backend/migrations/000005_interactions.up.sql``) — not just Pydantic
validation:

* Meeting: UUID PK, valid/invalid University FK (23503), university
  CASCADE delete, ``meeting_type`` default ``'online'``, ``participants``
  JSONB ``'[]'::jsonb`` default + roundtrip, created_at/updated_at,
  meeting_documents link / unique pair (23505) / CASCADE both sides.
* Student: valid row, University + ITProgram FKs (valid + 23503 invalid),
  ``program_id`` really points at ``it_programs`` (not
  ``university_programs``), ``external_id`` UNIQUE (23505), default status
  ``'active'`` (VARCHAR, no PG ENUM), explicit statuses, university /
  program isolation (RESTRICT on delete), timestamps.
* Passport spot-check: meetings feed ``meetings`` + timeline,
  students feed ``students_summary`` + program ``students_count``.

PostgreSQL integration via ``TEST_DATABASE_URL`` (canonical SQL
migrations ONLY — ``tests/db_helpers.require_pg_engine``). Skips without
PG; there is deliberately no SQLite fallback.
"""

import os
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata on Base)
from app.models.catalog import ITDirection, ITProduct, ITProgram, University, Vendor
from app.models.interactions import Document, Meeting, MeetingDocument, Student

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _pgcode(exc: IntegrityError) -> str | None:
    """psycopg3 exposes the SQLSTATE as ``sqlstate`` (not ``pgcode``)."""
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


@pytest.fixture()
def engine():
    """Fresh isolated PG DB per test (canonical SQL migrations, never ORM)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _catalog(db: Session, tag: str):
    d = ITDirection(code=f"MS-{tag}", name=f"Direction {tag}")
    db.add(d)
    db.flush()
    p = ITProgram(direction_id=d.id, name=f"Program {tag}", description="")
    v = Vendor(name=f"Vendor {tag}")
    db.add_all([p, v])
    db.flush()
    prod = ITProduct(vendor_id=v.id, name=f"Product {tag}", version="1.0")
    u = University(name=f"University {tag}", city="Москва")
    db.add_all([prod, u])
    db.flush()
    return {"direction": d, "program": p, "vendor": v, "product": prod,
            "university": u}


def _meeting(db: Session, u: University, **kw) -> Meeting:
    args = dict(
        university_id=u.id,
        subject="Синк по запуску",
        participants=[],
        meeting_at=datetime.now(timezone.utc),
        created_by_keycloak_sub="tester",
    )
    args.update(kw)
    m = Meeting(**args)
    db.add(m)
    db.flush()
    return m


def _student(db: Session, u: University, p: ITProgram, ext: str, **kw) -> Student:
    args = dict(
        external_id=ext,
        university_id=u.id,
        program_id=p.id,
        full_name="Студентов С. С.",
        started_at=date.today(),
    )
    args.update(kw)
    s = Student(**args)
    db.add(s)
    db.flush()
    return s


def _document(db: Session, u: University) -> Document:
    d = Document(
        university_id=u.id, document_type="other", title="T",
        file_path="p", file_name="f", file_size=1, mime_type="x",
        uploaded_by_keycloak_sub="tester",
    )
    db.add(d)
    db.flush()
    return d


# ------------------------------------------------------------- Meeting ---


def test_meeting_create_uuid_pk_and_fields(db: Session):
    g = _catalog(db, "m1")
    m = _meeting(db, g["university"],
                 meeting_type="offline",
                 participants=[{"name": "Иванов", "role": "Ректор"}],
                 outcome="Договорились", next_action="Прислать план")
    db.commit()
    assert isinstance(m.id, uuid.UUID)
    assert m.university_id == g["university"].id
    assert m.meeting_type == "offline"
    assert m.subject == "Синк по запуску"
    assert m.participants == [{"name": "Иванов", "role": "Ректор"}]
    assert m.outcome == "Договорились"
    # relationship back-populates
    assert m.university.name == g["university"].name


def test_meeting_invalid_university_fk_is_23503(db: Session):
    m = Meeting(
        university_id=uuid.uuid4(), subject="S", participants=[],
        meeting_at=datetime.now(timezone.utc),
        created_by_keycloak_sub="tester",
    )
    db.add(m)
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23503"  # foreign_key_violation, real PG
    assert _pg_constraint(ei.value) == "fk_meetings_university_id_universities"


def test_meeting_university_delete_cascades(db: Session):
    """ON DELETE CASCADE: university -> meetings (+ their links)."""
    g = _catalog(db, "m2")
    u = g["university"]
    m = _meeting(db, u)
    d = _document(db, u)
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    db.commit()
    uid = u.id
    db.expunge_all()
    # Core DELETE probes the true DB policy (bypasses ORM cascades).
    db.execute(sa_delete(University).where(University.id == uid))
    db.commit()
    assert db.execute(select(Meeting)).scalars().all() == []
    assert db.execute(select(MeetingDocument)).scalars().all() == []


def test_meeting_type_default_online(db: Session, engine):
    # Canonical SQL default ...
    with engine.connect() as conn:
        default = conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='meetings' AND column_name='meeting_type'"
        )).scalar()
    assert default is not None and "online" in default
    # ... mirrored by the ORM Python-side default.
    g = _catalog(db, "m3")
    m = _meeting(db, g["university"])
    assert m.meeting_type == "online"
    db.commit()
    db.refresh(m)
    assert m.meeting_type == "online"


def test_meeting_participants_jsonb_type_and_empty_default(db: Session, engine):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT data_type, column_default FROM information_schema.columns "
            "WHERE table_name='meetings' AND column_name='participants'"
        )).mappings().one()
    assert row["data_type"] == "jsonb"  # never TEXT
    assert row["column_default"] is not None and "[]" in row["column_default"]
    # ORM default is an empty list (no shared-mutable-alias bug: default=list).
    g = _catalog(db, "m4")
    m = _meeting(db, g["university"])
    assert m.participants == []
    db.commit()
    db.refresh(m)
    assert m.participants == []


def test_meeting_participants_json_roundtrip(db: Session):
    g = _catalog(db, "m5")
    parts = [
        {"name": "Иванов И.И.", "role": "Ректор", "side": "university"},
        {"name": "Петрова А.А.", "role": "Менеджер", "side": "vendor"},
        "просто строка",
    ]
    m = _meeting(db, g["university"], participants=parts)
    mid = m.id
    db.commit()
    db.expunge_all()
    got = db.execute(select(Meeting).where(Meeting.id == mid)).scalar_one()
    assert got.participants == parts
    assert got.participants[0]["side"] == "university"


def test_meeting_timestamps(db: Session):
    g = _catalog(db, "m6")
    m = _meeting(db, g["university"])
    db.commit()
    assert m.created_at is not None and m.created_at.tzinfo is not None
    assert m.updated_at is not None and m.updated_at.tzinfo is not None
    assert m.updated_at >= m.created_at


def test_meeting_documents_unique_pair_is_23505(db: Session):
    g = _catalog(db, "m7")
    m = _meeting(db, g["university"])
    d = _document(db, g["university"])
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    db.commit()
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23505"  # unique_violation, real PG
    assert _pg_constraint(ei.value) == "uq_meeting_documents_meeting_document"


def test_meeting_documents_invalid_fk_is_23503(db: Session):
    g = _catalog(db, "m8")
    m = _meeting(db, g["university"])
    d = _document(db, g["university"])
    db.commit()  # commit the valid setup so later rollbacks keep it
    db.add(MeetingDocument(meeting_id=m.id, document_id=uuid.uuid4()))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23503"
    assert _pg_constraint(ei.value) == "fk_meeting_documents_document_id_documents"
    db.add(MeetingDocument(meeting_id=uuid.uuid4(), document_id=d.id))
    with pytest.raises(IntegrityError) as ei2:
        db.commit()
    db.rollback()
    assert _pgcode(ei2.value) == "23503"
    assert _pg_constraint(ei2.value) == "fk_meeting_documents_meeting_id_meetings"


def test_meeting_documents_cascade_both_sides(db: Session):
    """Both FKs are CASCADE: deleting either side removes only the link."""
    g = _catalog(db, "m9")
    u = g["university"]
    m = _meeting(db, u)
    d = _document(db, u)
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    db.commit()
    mid, did, uid = m.id, d.id, u.id
    # document side: link gone, meeting kept
    db.expunge_all()
    db.execute(sa_delete(Document).where(Document.id == did))
    db.commit()
    assert db.execute(select(MeetingDocument)).scalars().all() == []
    assert db.execute(select(Meeting)).scalars().all() != []
    # meeting side: link gone, document kept
    u2 = db.get(University, uid)
    d2 = _document(db, u2)
    m2 = db.get(Meeting, mid)
    db.add(MeetingDocument(meeting_id=m2.id, document_id=d2.id))
    db.commit()
    db.expunge_all()
    db.execute(sa_delete(Meeting).where(Meeting.id == mid))
    db.commit()
    assert db.execute(select(MeetingDocument)).scalars().all() == []
    assert db.execute(select(Document)).scalars().all() != []


def test_meeting_expected_indexes_exist(engine):
    idx = {i["name"] for i in inspect(engine).get_indexes("meetings")}
    assert {"ix_meetings_university_id", "ix_meetings_meeting_at",
            "ix_meetings_univ_meeting_at"} <= idx


# ------------------------------------------------------------- Student ---


def test_student_create_valid_uuid_pk(db: Session):
    g = _catalog(db, "s1")
    s = _student(db, g["university"], g["program"], "EXT-S1",
                 group_name="ИВТ-11", status="active")
    db.commit()
    assert isinstance(s.id, uuid.UUID)
    assert s.external_id == "EXT-S1"
    assert s.group_name == "ИВТ-11"
    assert s.status == "active"
    assert s.university_id == g["university"].id
    assert s.program_id == g["program"].id


def test_student_program_fk_points_to_it_programs(engine):
    fks = inspect(engine).get_foreign_keys("students")
    by_col = {tuple(f["constrained_columns"]): f for f in fks}
    assert by_col[("program_id",)]["referred_table"] == "it_programs"
    assert by_col[("program_id",)]["options"].get("ondelete") == "RESTRICT"
    assert by_col[("university_id",)]["referred_table"] == "universities"
    assert by_col[("university_id",)]["options"].get("ondelete") == "RESTRICT"


def test_student_invalid_university_fk_is_23503(db: Session):
    g = _catalog(db, "s2")
    s = Student(external_id="EXT-BAD-U", university_id=uuid.uuid4(),
                program_id=g["program"].id, full_name="X",
                started_at=date.today())
    db.add(s)
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23503"
    assert _pg_constraint(ei.value) == "fk_students_university_id_universities"


def test_student_invalid_program_fk_is_23503(db: Session):
    g = _catalog(db, "s3")
    s = Student(external_id="EXT-BAD-P", university_id=g["university"].id,
                program_id=uuid.uuid4(), full_name="X",
                started_at=date.today())
    db.add(s)
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23503"
    assert _pg_constraint(ei.value) == "fk_students_program_id_it_programs"


def test_student_external_id_unique_is_23505(db: Session):
    g = _catalog(db, "s4")
    _student(db, g["university"], g["program"], "EXT-DUP")
    db.commit()
    db.add(Student(
        external_id="EXT-DUP", university_id=g["university"].id,
        program_id=g["program"].id, full_name="Дубль",
        started_at=date.today(),
    ))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) == "23505"  # unique_violation, real PG
    assert _pg_constraint(ei.value) == "uq_students_external_id"


def test_student_default_status_active_varchar(db: Session, engine):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT data_type, udt_name, column_default "
            "FROM information_schema.columns "
            "WHERE table_name='students' AND column_name='status'"
        )).mappings().one()
    # VARCHAR with DB default 'active' — deliberately NOT a PG ENUM/CHECK.
    assert row["data_type"] == "character varying"
    assert row["udt_name"] == "varchar"
    assert row["column_default"] is not None and "active" in row["column_default"]
    g = _catalog(db, "s5")
    s = _student(db, g["university"], g["program"], "EXT-DEF")
    assert s.status == "active"
    db.commit()
    db.refresh(s)
    assert s.status == "active"


def test_student_explicit_statuses(db: Session):
    g = _catalog(db, "s6")
    for i, status in enumerate(["active", "graduated", "expelled",
                                "academic_leave"]):
        _student(db, g["university"], g["program"], f"EXT-ST-{i}",
                 status=status)
    db.commit()
    rows = db.execute(select(Student.status)).scalars().all()
    assert sorted(rows) == ["academic_leave", "active", "expelled", "graduated"]


def test_student_university_isolation_restrict(db: Session):
    """RESTRICT: a university with students cannot be deleted (Core DELETE)."""
    g = _catalog(db, "s7")
    u = g["university"]
    _student(db, u, g["program"], "EXT-ISO-U")
    db.commit()
    uid = u.id
    db.expunge_all()
    with pytest.raises(IntegrityError) as ei:
        db.execute(sa_delete(University).where(University.id == uid))
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) in {"23503", "23001"}
    # row survived the blocked delete
    assert db.execute(select(Student)).scalars().all() != []


def test_student_program_isolation_restrict(db: Session):
    """RESTRICT: an it_program with students cannot be deleted."""
    g = _catalog(db, "s8")
    p = g["program"]
    _student(db, g["university"], p, "EXT-ISO-P")
    db.commit()
    pid = p.id
    db.expunge_all()
    with pytest.raises(IntegrityError) as ei:
        db.execute(sa_delete(ITProgram).where(ITProgram.id == pid))
        db.commit()
    db.rollback()
    assert _pgcode(ei.value) in {"23503", "23001"}


def test_student_timestamps(db: Session):
    g = _catalog(db, "s9")
    s = _student(db, g["university"], g["program"], "EXT-TS")
    db.commit()
    assert s.created_at is not None and s.created_at.tzinfo is not None
    assert s.updated_at is not None and s.updated_at.tzinfo is not None
    assert s.updated_at >= s.created_at


def test_student_expected_indexes_exist(engine):
    idx = {i["name"] for i in inspect(engine).get_indexes("students")}
    assert {"ix_students_university_id", "ix_students_program_id",
            "ix_students_status"} <= idx


# ------------------------------------------------- passport spot-check ---


def test_passport_uses_meetings_and_students_data(db: Session):
    """Meetings -> meetings + timeline; students -> summary + program counts."""
    from app.models.interactions import UniversityProgram
    from app.modules.universities import passport_service as ps

    g = _catalog(db, "ps1")
    u = g["university"]
    db.add(UniversityProgram(university_id=u.id, program_id=g["program"].id,
                             status="active"))
    _student(db, u, g["program"], "EXT-PS-1", status="active")
    _student(db, u, g["program"], "EXT-PS-2", status="graduated")
    _meeting(db, u, subject="Стратегическая сессия",
             participants=[{"name": "Ректор", "role": "ректор"}])
    db.commit()

    passport = ps.get_passport(db, u.id)
    assert len(passport.meetings) == 1
    assert passport.meetings[0].subject == "Стратегическая сессия"
    assert passport.meetings[0].participants == ["Ректор"]
    assert any(t.type == "meeting" for t in passport.last_interactions)

    summary = passport.students_summary
    assert summary.total == 2
    assert summary.active == 1
    assert summary.graduated == 1
    assert summary.by_status == {"active": 1, "graduated": 1}
    assert len(summary.by_program) == 1
    assert summary.by_program[0].total == 2
    assert passport.programs[0].students_count == 2
