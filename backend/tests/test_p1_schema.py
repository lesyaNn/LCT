"""P1 schema integration tests (task §16).

Runs that need a database are PostgreSQL integration tests (canonical SQL
migrations via ``tests/db_helpers.py``). Pure-unit checks (timestamp tz-awareness
on metadata, derived statuses on transient objects, readiness math, migration
chain shape) run anywhere.

DB tests need PostgreSQL::

    TEST_DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk_p1_test \\
        python -m pytest tests/test_p1_schema.py -q
"""

import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata)
from app.db.base import Base
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
from app.models.interactions import (
    Document,
    Meeting,
    MeetingDocument,
    Student,
)
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.services.teacher_readiness import compute_teacher_readiness

EXPECTED_TABLES = {
    "universities",
    "it_directions",
    "it_programs",
    "vendors",
    "it_products",
    "contracts",
    "licenses",
    "responsibles",
    "university_responsibles",
    "teachers",
    "teacher_qualifications",
    "teacher_certificates",
    "teacher_programs",
    "students",
    "university_programs",
    "university_products",
    "meetings",
    "meeting_documents",
    "documents",
    "interaction_notes",
}

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


def _mini_catalog(db: Session, tag: str = "t"):
    """Minimal valid graph: direction/program/vendor/product/uni/resp."""
    d = ITDirection(code=f"D-{tag}", name=f"Direction {tag}")
    db.add(d)
    db.flush()
    p = ITProgram(direction_id=d.id, name=f"Program {tag}", description="")
    v = Vendor(name=f"Vendor {tag}")
    db.add_all([p, v])
    db.flush()
    pr = ITProduct(vendor_id=v.id, name=f"Product {tag}", version="1.0")
    u = University(name=f"University {tag}", city="Москва")
    r = Responsible(full_name="Иванов И.И.", email=f"r-{tag}@example.local", role="manager")
    db.add_all([pr, u, r])
    db.flush()
    return {
        "direction": d,
        "program": p,
        "vendor": v,
        "product": pr,
        "university": u,
        "responsible": r,
    }


# ------------------------------------------------------------ structure


def test_all_tables_exist(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_foreign_keys_really_created(engine):
    insp = inspect(engine)
    fks = {
        (t, tuple(f["constrained_columns"]), f["referred_table"])
        for t in EXPECTED_TABLES
        for f in insp.get_foreign_keys(t)
    }
    assert ("licenses", ("university_id",), "universities") in fks
    assert ("licenses", ("product_id",), "it_products") in fks
    assert ("teacher_programs", ("teacher_id",), "teachers") in fks
    assert ("meeting_documents", ("meeting_id",), "meetings") in fks
    assert ("documents", ("license_id",), "licenses") in fks
    assert len(fks) >= 25


def test_no_direct_responsible_column_on_universities(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("universities")}
    assert "responsible_id" not in cols
    assert {"id", "name", "city", "created_at", "updated_at"} <= cols


def test_all_models_have_timezone_aware_timestamps():
    from sqlalchemy import DateTime

    for table in EXPECTED_TABLES:
        cols = inspect(Base.metadata.tables[table]).columns
        for name in ("created_at", "updated_at"):
            if name in cols:
                assert isinstance(cols[name].type, DateTime)
                assert cols[name].type.timezone, f"{table}.{name} naive!"
                assert not cols[name].nullable


def test_timestamptz_in_postgres():
    if not TEST_URL.startswith("postgresql"):
        pytest.skip("needs TEST_DATABASE_URL=postgresql...")
    eng = create_engine(TEST_URL)
    insp = inspect(eng)
    try:
        from sqlalchemy import text

            # noqa
        with eng.connect() as conn:
            rows = conn.execute(
                text(
                "SELECT DISTINCT data_type FROM information_schema.columns "
                "WHERE column_name='created_at' AND table_schema='public'"
                )
            ).fetchall()
        assert rows and all(r[0] == "timestamp with time zone" for r in rows)
    finally:
        eng.dispose()
    _ = insp


# ------------------------------------------------------------ constraints


def test_unique_constraints(db: Session):
    db.add(University(name="Уник", city="Казань"))
    db.commit()
    db.add(University(name="Уник", city="Уфа"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    g = _mini_catalog(db, tag="uniq")
    db.add(
        Student(
            external_id="EXT-1",
            university_id=g["university"].id,
            program_id=g["program"].id,
            full_name="С",
            started_at=date.today(),
        )
    )
    db.commit()
    db.add(
        Student(
            external_id="EXT-1",
            university_id=g["university"].id,
            program_id=g["program"].id,
            full_name="С2",
            started_at=date.today(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_mn_uniqueness(db: Session):
    g = _mini_catalog(db)
    t = Teacher(
        university_id=g["university"].id, full_name="П", email="t@example.local", position=""
    )
    db.add(t)
    db.flush()
    db.add(TeacherProgram(teacher_id=t.id, program_id=g["program"].id, assigned_at=date.today()))
    db.commit()
    db.add(TeacherProgram(teacher_id=t.id, program_id=g["program"].id, assigned_at=date.today()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(
        UniversityResponsible(university_id=g["university"].id, responsible_id=g["responsible"].id)
    )
    db.commit()
    db.add(
        UniversityResponsible(university_id=g["university"].id, responsible_id=g["responsible"].id)
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_restrict_blocks_parent_delete(db: Session):
    g = _mini_catalog(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.delete(g["direction"])
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.delete(g["vendor"])
        db.commit()
    db.rollback()


def test_cascade_teacher_children(db: Session):
    g = _mini_catalog(db)
    t = Teacher(
        university_id=g["university"].id, full_name="П", email="c@example.local", position=""
    )
    db.add(t)
    db.flush()
    q = TeacherQualification(teacher_id=t.id, qualification_name="К", obtained_at=date.today())
    c = TeacherCertificate(
        teacher_id=t.id,
        certificate_name="С",
        issued_by="X",
        issued_at=date.today(),
        is_mandatory=True,
    )
    db.add_all([q, c])
    db.commit()
    db.delete(t)
    db.commit()
    assert db.execute(select(TeacherQualification)).scalars().all() == []
    assert db.execute(select(TeacherCertificate)).scalars().all() == []


def test_set_null_on_contract_delete(db: Session):
    g = _mini_catalog(db)
    u, pr = g["university"], g["product"]
    c = Contract(university_id=u.id, contract_number="D-1", signed_at=date.today())
    db.add(c)
    db.flush()
    lic = License(
        university_id=u.id,
        product_id=pr.id,
        contract_id=c.id,
        license_number="L-1",
        signed_at=date.today(),
        expires_at=date.today() + timedelta(days=100),
    )
    db.add(lic)
    db.commit()
    db.delete(c)
    db.commit()
    db.refresh(lic)
    assert lic.contract_id is None


def test_documents_single_link_check(db: Session):
    g = _mini_catalog(db)
    u = g["university"]
    bad = Document(
        university_id=u.id,
        document_type="act",
        title="T",
        file_path="p",
        file_name="f",
        file_size=1,
        mime_type="x",
        license_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        uploaded_by_keycloak_sub="s",
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_meeting_documents_link(db: Session):
    g = _mini_catalog(db)
    u = g["university"]
    m = Meeting(
        university_id=u.id,
        subject="S",
        participants=[],
                meeting_at=datetime.now(timezone.utc),
        created_by_keycloak_sub="s",
    )
    d = Document(
        university_id=u.id,
        document_type="other",
        title="T",
        file_path="p",
        file_name="f",
        file_size=1,
        mime_type="x",
        uploaded_by_keycloak_sub="s",
    )
    db.add_all([m, d])
    db.flush()
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    db.commit()
    db.add(MeetingDocument(meeting_id=m.id, document_id=d.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # cascade: deleting the meeting removes the link, keeps the document
    db.delete(m)
    db.commit()
    assert db.execute(select(MeetingDocument)).scalars().all() == []
    assert db.execute(select(Document)).scalars().all() != []


def test_participants_json_roundtrip(db: Session):
    g = _mini_catalog(db)
    parts = [{"name": "Иванов И.И.", "role": "Ректор", "side": "university"}]
    m = Meeting(
        university_id=g["university"].id,
        subject="S",
                participants=parts,
                meeting_at=datetime.now(timezone.utc),
        created_by_keycloak_sub="s",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    assert m.participants[0]["side"] == "university"


# ------------------------------------------------------------ timestamps


def test_created_updated_behaviour(db: Session, engine):
    u = University(name="Временная", city="Москва")
    db.add(u)
    db.flush()
    # Python-side default applied at flush is always tz-aware.
    assert u.created_at is not None and u.created_at.tzinfo is not None
    db.commit()
    assert u.created_at is not None
    if engine.dialect.name != "sqlite":
        # SQLite cannot store tzinfo (stores naive CURRENT_TIMESTAMP);
        # PostgreSQL round-trips timestamptz (verified live in
        # test_timestamptz_in_postgres + db_inspect.py).
        assert u.created_at.tzinfo is not None
    assert u.updated_at >= u.created_at
    created = u.created_at
    time.sleep(0.02)
    u.city = "Казань"
    db.commit()
    db.refresh(u)
    assert u.created_at == created
    assert u.updated_at >= created


# ------------------------------------------------------------ derived status


def test_license_derived_status(db: Session):
    g = _mini_catalog(db)
    u, pr = g["university"], g["product"]
    cases = [
        (-5, "expired"),
        (5, "expires_soon"),
        (30, "expires_soon"),
        (31, "active"),
        (400, "active"),
    ]
    for i, (delta, expected) in enumerate(cases):
        lic = License(
            university_id=u.id,
            product_id=pr.id,
                      license_number=f"LX-{i}",
                      signed_at=date.today() - timedelta(days=300),
            expires_at=date.today() + timedelta(days=delta),
        )
        assert lic.derived_status == expected, (delta, lic.derived_status)
        assert lic.days_to_expiry == delta
    db.rollback()


def test_contract_derived_status(db: Session):
    c = Contract(
        university_id=uuid.uuid4(), contract_number="D-X", signed_at=date.today(), expires_at=None
    )
    assert c.derived_status == "active"
    assert c.days_to_expiry is None
    c.status_raw = "terminated"
    assert c.derived_status == "terminated"
    c.status_raw = "draft"
    assert c.derived_status == "draft"
    c.status_raw = "signed"
    c.expires_at = date.today() - timedelta(days=1)
    assert c.derived_status == "expired"


# ------------------------------------------------------------ readiness


def test_teacher_readiness_matrix():
    today = date.today()
    ready = compute_teacher_readiness(
        [
            {
                "certificate_name": "Инфобез",
                "is_mandatory": True,
                "expires_at": today + timedelta(days=400),
            }
        ]
    )
    assert ready.readiness.value == "ready"

    attention = compute_teacher_readiness(
        [
            {
                "certificate_name": "Инфобез",
                "is_mandatory": True,
                "expires_at": today + timedelta(days=10),
            }
        ]
    )
    assert attention.readiness.value == "attention"
    assert len(attention.reasons) == 1

    expired = compute_teacher_readiness(
        [
            {
                "certificate_name": "Инфобез",
                "is_mandatory": True,
                "expires_at": today - timedelta(days=5),
            }
        ]
    )
    assert expired.readiness.value == "expired"

    # edge: no mandatory -> ready; non-mandatory expired ignored
    assert compute_teacher_readiness([]).readiness.value == "ready"
    assert (
        compute_teacher_readiness(
            [
                {
                    "certificate_name": "Soft",
                    "is_mandatory": False,
                    "expires_at": today - timedelta(days=100),
                }
            ]
        ).readiness.value
        == "ready"
    )
    assert (
        compute_teacher_readiness(
            [{"certificate_name": "Инфобез", "is_mandatory": True, "expires_at": None}]
        ).readiness.value
        == "ready"
    )


# ------------------------------------------------------------ seed


def test_seed_idempotent(engine):
    from app.db.seed import seed_demo

    with Session(engine) as s:
        first = seed_demo(s)
    with Session(engine) as s:
        second = seed_demo(s)
    assert first == second
    assert second["universities"] == 10
    assert second["teachers"] == 34
    assert second["students"] > 0
    # no dangling FKs
    with Session(engine) as s:
        for lic in s.execute(select(License)).scalars():
            assert s.get(University, lic.university_id) is not None
            assert s.get(ITProduct, lic.product_id) is not None
        n_links = len(s.execute(select(MeetingDocument)).scalars().all())
        assert n_links >= 10


# ------------------------------------------------------------ migration chain


def test_sql_migration_single_head_chain():
    """SQL files are the single schema source: 000001..000021, paired up/down."""
    import re as _re

    versions = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
    )
    ups, downs = set(), set()
    for fname in os.listdir(versions):
        m = _re.match(r"^(\d{6}_[a-z0-9_]+)\.(up|down)\.sql$", fname)
        assert m, f"bad migration filename: {fname}"
        (ups if m.group(2) == "up" else downs).add(m.group(1))
    assert ups == downs, f"unpaired migrations: up^down={ups ^ downs}"
    assert sorted(ups)[-1] == "000021_audit_p5"
    assert len(ups) == 21


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL=postgresql..."
)
def test_sql_migrate_upgrade_downgrade_cycle():
    import subprocess

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Start from a truly clean DB (schema reset, test-only dedicated DB).
    eng = create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        with eng.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            )
            conn.commit()
    finally:
        eng.dispose()
    env = dict(os.environ)
    env["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    for cmd in (
        ["python", "scripts/migrate.py", "down", "--to", "base", "--yes"],
        ["python", "scripts/migrate.py", "up"],
    ):
        subprocess.run(cmd, cwd=backend_dir, env=env, check=True, capture_output=True)
    eng = create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        assert EXPECTED_TABLES <= set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
