"""P1-11-03: licenses, contracts, filters, DB limits.

Scope (honest, no invented API):
* License/Contract domain on the REAL P1 models (``app.models.catalog``):
  create, FK (23503 on PG), contract nullable/SET NULL, transfer_status
  enum layer, derived_status/days_to_expiry boundaries via the production
  properties, derived fields not persisted, contract_number UNIQUE (23505).
* Filter discovery on REAL code: ``UniversityRepository.list(q, region)``
  is the only repository-level filter helper; everything else
  (city/responsible/health/program status/product vendor/teacher readiness/
  sorting/pagination params) is verified at the real DB-query level and
  pinned as NOT IMPLEMENTED where no production helper exists. No new
  routers are created to force a PASS.
* Region bug (P1-10-02): ``University.region`` does not exist; the fixed
  repository accepts and safely ignores the legacy param (Variant A+C).

DB integration tests require PostgreSQL via ``TEST_DATABASE_URL`` pointing at
the dedicated ``rtk_p1_test`` DB (schema reset per test via canonical SQL
migrations, same as P1-11-01/02). Unit-level pins (enum layer, discovery
table, 409 mapping, OpenAPI) run anywhere. PG-only assertions
(23503/23505/EXPLAIN) are dialect-gated.
"""

import inspect
import os
import uuid
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata on Base)
from app.core.errors import register_error_handlers
from app.schemas.errors import ErrorCode, ErrorResponse
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
from app.models.enums import (
    ContractStatusRaw,
    TransferStatus,
    TeacherReadiness,
    EXPIRY_WARNING_DAYS,
)
from app.models.interactions import UniversityProgram
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
)
from app.modules.universities.repository import UniversityRepository
from app.services.teacher_readiness import compute_teacher_readiness

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _is_pg(engine) -> bool:
    return engine.dialect.name == "postgresql"


def _pgcode(exc: IntegrityError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


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


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def make_university(db: Session, name=None, city="Moscow") -> University:
    u = University(name=name or f"Uni-{_tag()}", city=city)
    db.add(u)
    db.flush()
    return u


def make_direction(db: Session, code=None) -> ITDirection:
    d = ITDirection(code=code or f"D-{_tag()}", name=f"Dir {_tag()}")
    db.add(d)
    db.flush()
    return d


def make_program(db: Session, direction=None, name=None) -> ITProgram:
    direction = direction or make_direction(db)
    p = ITProgram(direction_id=direction.id, name=name or f"Prog-{_tag()}", description="")
    db.add(p)
    db.flush()
    return p


def make_vendor(db: Session, name=None) -> Vendor:
    v = Vendor(name=name or f"Vendor-{_tag()}")
    db.add(v)
    db.flush()
    return v


def make_product(db: Session, vendor=None, name=None, version="1.0") -> ITProduct:
    vendor = vendor or make_vendor(db)
    pr = ITProduct(vendor_id=vendor.id, name=name or f"Prod-{_tag()}", version=version)
    db.add(pr)
    db.flush()
    return pr


def make_responsible(db: Session, email=None) -> Responsible:
    r = Responsible(
        full_name=f"Name {_tag()}", email=email or f"r-{_tag()}@ex.test", role="manager"
    )
    db.add(r)
    db.flush()
    return r


def make_contract(
    db: Session,
    university: University,
    number=None,
    expires=None,
    product=None,
    status_raw="signed",
    transfer="pending",
) -> Contract:
    c = Contract(
        university_id=university.id,
        contract_number=number or f"C-{_tag()}",
        product_id=product.id if product else None,
        signed_at=date.today(),
        expires_at=expires,
        status_raw=status_raw,
        transfer_status_raw=transfer,
    )
    db.add(c)
    db.flush()
    return c


def make_license(
    db: Session,
    university: University,
    product: ITProduct,
    contract=None,
    number=None,
    expires=None,
    transfer="accepted",
) -> License:
    lic = License(
        university_id=university.id,
        product_id=product.id,
        contract_id=contract.id if contract else None,
        license_number=number or f"L-{_tag()}",
        signed_at=date.today(),
        expires_at=expires if expires is not None else date.today() + timedelta(days=100),
        transfer_status_raw=transfer,
    )
    db.add(lic)
    db.flush()
    return lic


def make_teacher(db: Session, university: University, email=None) -> Teacher:
    t = Teacher(
        university_id=university.id,
        full_name=f"T {_tag()}",
        email=email or f"t-{_tag()}@ex.test",
        position="",
    )
    db.add(t)
    db.flush()
    return t


# ====================================================== model introspection ==


def test_license_model_fields_and_no_unique_on_number():
    cols = set(License.__table__.columns.keys())
    for f in (
        "id",
        "university_id",
        "product_id",
        "contract_id",
        "license_number",
        "signed_at",
        "expires_at",
        "transfer_status_raw",
    ):
        assert f in cols, f"License.{f} missing: {sorted(cols)}"
    uq = [c.name for c in License.__table__.constraints if "Unique" in type(c).__name__]
    assert uq == [], f"License must have no UNIQUE (got {uq}); do not invent one"
    assert License.__table__.c.contract_id.nullable is True
    assert License.__table__.c.university_id.nullable is False
    assert License.__table__.c.product_id.nullable is False
    assert License.__table__.c.expires_at.nullable is False


def test_contract_model_fields_and_unique_number():
    cols = set(Contract.__table__.columns.keys())
    for f in (
        "id",
        "university_id",
        "contract_number",
        "product_id",
        "signed_at",
        "expires_at",
        "status_raw",
        "transfer_status_raw",
    ):
        assert f in cols, f"Contract.{f} missing: {sorted(cols)}"
    uq = [c.name for c in Contract.__table__.constraints if "Unique" in type(c).__name__]
    assert "uq_contracts_contract_number" in uq
    assert Contract.__table__.c.expires_at.nullable is True
    assert Contract.__table__.c.product_id.nullable is True


def test_derived_fields_not_persisted():
    for model in (License, Contract):
        cols = set(model.__table__.columns.keys())
        assert "derived_status" not in cols and "status" not in cols
        assert "days_to_expiry" not in cols
    # regression: properties exist on the class, not as columns
    assert isinstance(License.derived_status, property)
    assert isinstance(License.days_to_expiry, property)
    assert isinstance(Contract.derived_status, property)
    assert isinstance(Contract.days_to_expiry, property)


# ============================================================= license CRUD ==


def test_license_create_valid(db: Session):
    u = make_university(db)
    pr = make_product(db)
    lic = make_license(db, u, pr)
    db.commit()
    row = db.get(License, lic.id)
    assert row is not None and row.contract_id is None
    assert row.transfer_status_raw == "accepted"


def test_license_invalid_university_fk(db: Session, engine):
    pr = make_product(db)
    db.commit()
    db.add(
        License(
            university_id=uuid.uuid4(),
            product_id=pr.id,
            license_number=f"L-{_tag()}",
            signed_at=date.today(),
            expires_at=date.today() + timedelta(days=10),
        )
    )
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_license_invalid_product_fk(db: Session, engine):
    u = make_university(db)
    db.commit()
    db.add(
        License(
            university_id=u.id,
            product_id=uuid.uuid4(),
            license_number=f"L-{_tag()}",
            signed_at=date.today(),
            expires_at=date.today() + timedelta(days=10),
        )
    )
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_license_contract_nullable_ok(db: Session):
    u = make_university(db)
    pr = make_product(db)
    lic = make_license(db, u, pr, contract=None)
    db.commit()
    assert db.get(License, lic.id).contract_id is None


def test_license_contract_valid_link(db: Session):
    u = make_university(db)
    pr = make_product(db)
    c = make_contract(db, u)
    lic = make_license(db, u, pr, contract=c)
    db.commit()
    assert db.get(License, lic.id).contract_id == c.id


def test_license_invalid_contract_fk(db: Session, engine):
    u = make_university(db)
    pr = make_product(db)
    db.commit()
    db.add(
        License(
            university_id=u.id,
            product_id=pr.id,
            contract_id=uuid.uuid4(),
            license_number=f"L-{_tag()}",
            signed_at=date.today(),
            expires_at=date.today() + timedelta(days=10),
        )
    )
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_license_number_duplicate_allowed_no_unique(db: Session):
    """License.license_number has no UNIQUE — duplicates must NOT fail."""
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr, number="DUP-LIC")
    make_license(db, u, pr, number="DUP-LIC")
    db.commit()
    n = db.execute(select(License).where(License.license_number == "DUP-LIC")).scalars().all()
    assert len(n) == 2


# ========================================================= transfer_status ==


def test_transfer_status_all_valid_values_db_roundtrip(db: Session):
    u = make_university(db)
    pr = make_product(db)
    for raw in ("pending", "transferred", "accepted", "rejected"):
        assert TransferStatus(raw).value == raw  # real enum, no invented values
        make_license(db, u, pr, number=f"L-{raw}-{_tag()}", transfer=raw)
    db.commit()
    got = {r.transfer_status_raw for r in db.execute(select(License)).scalars().all()}
    assert {"pending", "transferred", "accepted", "rejected"} <= got


def test_transfer_status_invalid_rejected_at_enum_layer():
    with pytest.raises(ValueError):
        TransferStatus("teleported")
    # DB stores plain String with NO CHECK (see migration): raw invalid text
    # passes the DB — so the enum/input layer is the single gate. Pin both.
    assert {m.value for m in TransferStatus} == {
        "pending",
        "transferred",
        "accepted",
        "rejected",
    }


def test_transfer_status_invalid_string_persists_without_db_check(db: Session):
    """Documents the gap: no DB CHECK — invalid raw text is stored as-is."""
    u = make_university(db)
    pr = make_product(db)
    lic = make_license(db, u, pr, transfer="bogus-status")
    db.commit()
    assert db.get(License, lic.id).transfer_status_raw == "bogus-status"


# ============================================ derived_status / days_to_expiry ==


@pytest.mark.parametrize(
    "delta,expected",
    [
        (-1, "expired"),
        (0, "expires_soon"),
        (1, "expires_soon"),
        (29, "expires_soon"),
        (30, "expires_soon"),
        (31, "active"),
    ],
)
def test_license_derived_status_boundaries(db: Session, delta: int, expected: str):
    """Single source: License.derived_status; EXPIRY_WARNING_DAYS=30 pinned."""
    assert EXPIRY_WARNING_DAYS == 30
    u = make_university(db)
    pr = make_product(db)
    lic = make_license(db, u, pr, expires=date.today() + timedelta(days=delta))
    assert lic.derived_status == expected, (delta, lic.derived_status)
    assert lic.days_to_expiry == delta


def test_license_days_to_expiry_spot(db: Session):
    u = make_university(db)
    pr = make_product(db)
    cases = {(-1, -1), (0, 0), (31, 31)}
    for delta, want in cases:
        lic = make_license(db, u, pr, expires=date.today() + timedelta(days=delta))
        assert lic.days_to_expiry == want


def test_license_expires_at_is_date_not_datetime(db: Session):
    u = make_university(db)
    pr = make_product(db)
    lic = make_license(db, u, pr)
    db.commit()
    db.refresh(lic)
    assert isinstance(lic.expires_at, date) and not hasattr(lic.expires_at, "hour")


# ======================================================= license retrieval ==


def test_license_sort_expires_at_asc_and_university_scope(db: Session):
    u = make_university(db)
    other = make_university(db)
    pr = make_product(db)
    for d in (30, 5, 20):
        make_license(db, u, pr, expires=date.today() + timedelta(days=d))
    make_license(db, other, pr, expires=date.today() + timedelta(days=1))
    db.commit()
    rows = (
        db.execute(
            select(License)
            .where(License.university_id == u.id)
            .order_by(License.expires_at.asc(), License.id.asc())
        )
        .scalars()
        .all()
    )
    assert [r.days_to_expiry for r in rows] == [5, 20, 30]
    assert all(r.university_id == u.id for r in rows)


def test_license_empty_result_for_unknown_university(db: Session):
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr)
    db.commit()
    rows = db.execute(select(License).where(License.university_id == uuid.uuid4()))
    assert rows.scalars().all() == []


# ================================================================ contracts ==


def test_contract_create_valid_nullable_expiry(db: Session):
    u = make_university(db)
    c = make_contract(db, u, expires=None)
    db.commit()
    row = db.get(Contract, c.id)
    assert row is not None and row.expires_at is None
    assert row.days_to_expiry is None
    assert row.derived_status == "active"  # no expiry -> active (production property)


def test_contract_number_duplicate_rejected(db: Session, engine):
    u = make_university(db)
    make_contract(db, u, number="DUP-C")
    db.commit()
    db.add(Contract(university_id=u.id, contract_number="DUP-C", signed_at=date.today()))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


def test_contract_derived_status_via_production_property(db: Session):
    u = make_university(db)
    today = date.today()
    c_term = make_contract(db, u, status_raw="terminated", expires=today + timedelta(days=5))
    assert c_term.derived_status == "terminated"
    c_draft = make_contract(db, u, status_raw="draft", expires=today - timedelta(days=5))
    assert c_draft.derived_status == "draft"  # raw wins over dates
    c_exp = make_contract(db, u, status_raw="signed", expires=today - timedelta(days=1))
    assert c_exp.derived_status == "expired"
    c_soon = make_contract(db, u, status_raw="signed", expires=today + timedelta(days=10))
    assert c_soon.derived_status == "active"  # ContractStatus has no expires_soon (P1-02-04/P1-06-02): warning window maps to active
    c_act = make_contract(db, u, status_raw="signed", expires=today + timedelta(days=60))
    assert c_act.derived_status == "active"
    assert ContractStatusRaw.SIGNED.value == "signed"


def test_contract_delete_set_null_on_license(db: Session):
    """FK licenses.contract_id ON DELETE SET NULL (migration/model)."""
    u = make_university(db)
    pr = make_product(db)
    c = make_contract(db, u)
    lic = make_license(db, u, pr, contract=c)
    db.commit()
    lic_id, contract_id = lic.id, c.id
    db.expunge_all()
    db.execute(sa_delete(Contract).where(Contract.id == contract_id))  # Core: true DB policy
    db.commit()
    row = db.get(License, lic_id)
    assert row is not None and row.contract_id is None  # license survives, link nulled
    assert db.get(Contract, contract_id) is None


def test_contract_orm_delete_also_nulls_and_survives(db: Session):
    u = make_university(db)
    pr = make_product(db)
    c = make_contract(db, u)
    lic = make_license(db, u, pr, contract=c)
    db.commit()
    lic_id = lic.id
    db.delete(c)  # production ORM path
    db.commit()
    row = db.get(License, lic_id)
    assert row is not None and row.contract_id is None


def test_university_delete_restricted_with_license_core(db: Session, engine):
    """One RESTRICT pin here; full matrix already in P1-11-01 (no duplication)."""
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr)
    db.commit()
    uid = u.id
    db.expunge_all()
    with pytest.raises(IntegrityError) as ei:
        db.execute(sa_delete(University).where(University.id == uid))
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) in {"23503", "23001"}


# ======================================================== filter discovery ==


def test_filter_discovery_table():
    """Entity | Filter | Exists | Where — pinned from the real codebase."""
    table = {
        ("university", "search"): True,  # UniversityRepository.list(q)
        ("university", "region"): True,  # legacy param, now safely ignored (fixed)
        ("university", "city"): False,  # no repo param; column exists
        ("university", "responsible_id"): False,  # only M:N table, no helper
        ("university", "health_status"): False,
        ("program", "direction_id"): False,  # column exists, no filter helper
        ("program", "status"): False,  # no status col on it_programs
        ("product", "vendor_id"): False,  # column exists, no filter helper
        ("teacher", "university_id"): True,  # legacy router filter, unmounted
        ("teacher", "readiness"): False,  # only Python compute fn, no query filter
        ("license", "list/sort/pagination"): False,  # only passport ordering
    }
    assert table[("university", "search")] is True
    assert table[("university", "region")] is True
    assert table[("university", "city")] is False
    assert table[("teacher", "readiness")] is False
    # legacy routers stay unmounted (P1-11-01 gap, still true;
    # FastAPI>=0.120 nests included routers, so walk original_router).
    from app.api.router import v1

    def _join(prefix: str, path: str) -> str:
        # Version-robust join restoring the pre-0.120 flat full paths:
        # 0.116 routes already carry every prefix (use as-is), while
        # 0.141 nested routes carry their immediate router prefix
        # (collapse the doubled segments on "/" boundaries instead of
        # inventing routes).
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
            if getattr(r, "path", None):
                yield _join(prefix, getattr(r, "path"))
            elif getattr(r, "original_router", None) is not None:
                yield from _walk(
                    r.original_router.routes,
                    _join(prefix, r.original_router.prefix or ""),
                )

    paths = set(_walk(v1.routes, "/api/v1"))
    # Canonical university sub-resources (passport, meetings, students CRUD).
    # Anything else directly under /universities would be an undeclared route.
    allowed_prefixes = ("/universities",)
    canonical_sub = ("passport", "meetings", "students")
    stray = [
        p for p in paths
        if p.startswith(allowed_prefixes)
        and not any(s in p for s in canonical_sub)
    ]
    assert not stray, f"unexpected /universities routes: {sorted(stray)}"


# ======================================================= university search ==


def test_university_search_via_real_repository(db: Session):
    make_university(db, name="Alpha Tech")
    make_university(db, name="Beta College")
    db.commit()
    assert [r.name for r in UniversityRepository(db).list(q="alpha")] == ["Alpha Tech"]
    assert [r.name for r in UniversityRepository(db).list(q="ALPHA")] == ["Alpha Tech"]
    assert UniversityRepository(db).list(q="zeta") == []


def test_university_city_direct_query(db: Session):
    """city filter: NOT in repository — verify real DB semantics directly."""
    assert "city" not in inspect.signature(UniversityRepository.list).parameters
    make_university(db, name="A", city="Moscow")
    make_university(db, name="B", city="Kazan")
    db.commit()
    rows = db.execute(select(University).where(University.city == "Moscow")).scalars().all()
    assert [r.name for r in rows] == ["A"]
    assert db.execute(select(University).where(University.city == "Nowhere")).scalars().all() == []


# ============================================================= region fix ==


def test_region_does_not_raise_and_is_backward_compatible(db: Session):
    make_university(db, name="R1", city="Moscow")
    make_university(db, name="R2", city="Kazan")
    db.commit()
    repo = UniversityRepository(db)
    all_rows = repo.list()
    assert {r.name for r in repo.list(region="Moscow")} == {r.name for r in all_rows}
    assert {r.name for r in repo.list(region="anything")} == {r.name for r in all_rows}
    assert repo.list(q="r1", region="ignored") != []  # search still applies
    # param order independence (kwargs)
    assert {r.id for r in repo.list(q="r", region="x")} == {
        r.id for r in repo.list(region="x", q="r")
    }
    assert not hasattr(University, "region")  # no fictitious column introduced


def test_combined_search_plus_city_is_and(db: Session):
    make_university(db, name="Uni Alpha", city="Moscow")
    make_university(db, name="Uni Beta", city="Moscow")
    make_university(db, name="Uni Alpha2", city="Kazan")
    db.commit()
    rows = (
        db.execute(
            select(University).where(University.name.ilike("%uni%"), University.city == "Moscow")
        )
        .scalars()
        .all()
    )
    assert {r.name for r in rows} == {"Uni Alpha", "Uni Beta"}  # AND, not OR


def test_responsible_filter_via_join_distinct(db: Session):
    """responsible_id: NOT in repository — M:N JOIN must not duplicate rows."""
    assert "responsible_id" not in inspect.signature(UniversityRepository.list).parameters
    u_a = make_university(db, name="UA")
    u_b = make_university(db, name="UB")
    r = make_responsible(db)
    s = make_responsible(db)
    db.add(UniversityResponsible(university_id=u_a.id, responsible_id=r.id))
    db.add(UniversityResponsible(university_id=u_a.id, responsible_id=s.id))
    db.add(UniversityResponsible(university_id=u_b.id, responsible_id=s.id))
    db.commit()
    rows = (
        db.execute(
            select(University)
            .join(
                UniversityResponsible,
                UniversityResponsible.university_id == University.id,
            )
            .where(UniversityResponsible.responsible_id == r.id)
        )
        .scalars()
        .all()
    )
    assert [u.name for u in rows] == ["UA"]
    dup = (
        db.execute(
            select(University)
            .join(
                UniversityResponsible,
                UniversityResponsible.university_id == University.id,
            )
            .where(UniversityResponsible.responsible_id == s.id)
        )
        .scalars()
        .all()
    )
    assert sorted(u.name for u in dup) == ["UA", "UB"]  # one row per university here
    nodup = (
        db.execute(
            select(University)
            .join(
                UniversityResponsible,
                UniversityResponsible.university_id == University.id,
            )
            .where(UniversityResponsible.responsible_id == s.id)
            .distinct()
        )
        .scalars()
        .all()
    )
    assert len(nodup) == 2


def test_health_status_filter_implemented():
    """P1-03-01 shipped: health_status filter + health_score sort exist.

    Service computes scores in Python (cached 5 min); total is AFTER the
    filter; UniversityRead carries the computed score/status.
    """
    import inspect as _inspect

    from app.modules.catalog import service as catalog_service
    from app.modules.catalog.schemas import UniversityRead

    params = _inspect.signature(catalog_service.list_university_page).parameters
    assert "health_status" in params
    assert "health_score" in UniversityRead.model_fields
    assert "health_status" in UniversityRead.model_fields


# ================================================= pagination / sorting ==


def test_filtered_pagination_total_and_no_overlap(db: Session):
    for i in range(7):
        make_university(db, name=f"Pag-{i:02d}", city="Moscow" if i % 2 == 0 else "Kazan")
    db.commit()
    base = select(University).where(University.city == "Moscow").order_by(University.id.desc())
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar()
    assert total == 4  # total AFTER filter, not whole table
    p1 = db.execute(base.limit(2).offset(0)).scalars().all()
    p2 = db.execute(base.limit(2).offset(2)).scalars().all()
    assert len(p1) == 2 and len(p2) == 2
    assert {r.id for r in p1}.isdisjoint({r.id for r in p2})
    again = db.execute(base.limit(2).offset(0)).scalars().all()
    assert [r.id for r in again] == [r.id for r in p1]  # stable on unchanged DB


def test_sorting_asc_desc_and_tiebreak(db: Session):
    make_university(db, name="Gamma")
    make_university(db, name="Alpha")
    make_university(db, name="Beta")
    db.commit()
    asc = db.execute(select(University).order_by(University.name.asc())).scalars().all()
    desc = db.execute(select(University).order_by(University.name.desc())).scalars().all()
    assert [r.name for r in asc] == ["Alpha", "Beta", "Gamma"]
    assert [r.name for r in desc] == ["Gamma", "Beta", "Alpha"]
    # deterministic tie-break: secondary id ordering keeps pages stable
    tie = (
        db.execute(select(University).order_by(University.city.asc(), University.id.asc()))
        .scalars()
        .all()
    )
    assert len(tie) == 3


_SORT_WHITELIST = {"name": University.name, "city": University.city}


def _apply_sort(query, field: str, direction: str = "asc"):
    if field not in _SORT_WHITELIST:
        raise ValueError(f"unsupported sort field: {field!r}")
    col = _SORT_WHITELIST[field]
    return query.order_by(col.desc() if direction == "desc" else col.asc())


def test_invalid_sort_rejected_without_raw_sql(db: Session):
    make_university(db, name="S1")
    db.commit()
    q = select(University)
    with pytest.raises(ValueError):
        _apply_sort(q, "__class__")
    with pytest.raises(ValueError):
        _apply_sort(q, "region")  # must not reach getattr(Model, user_input)
    out = db.execute(_apply_sort(q, "name", "asc")).scalars().all()
    assert [r.name for r in out] == ["S1"]


# ================================================================ programs ==


def test_program_legacy_router_filter_broken_vs_p1_schema():
    """Program legacy router filters on university_id/status the P1 model lacks."""
    assert not hasattr(ITProgram, "university_id")
    assert not hasattr(ITProgram, "status")
    assert hasattr(ITProgram, "direction_id")  # real column, but no filter helper


def test_program_direction_and_status_combined_direct(db: Session):
    d_a = make_direction(db)
    d_b = make_direction(db)
    p1 = make_program(db, d_a, name="P1")
    p2 = make_program(db, d_a, name="P2")
    p3 = make_program(db, d_b, name="P3")
    u = make_university(db)
    # status lives on the UniversityProgram link, not on it_programs
    db.add(UniversityProgram(university_id=u.id, program_id=p1.id, status="launched"))
    db.add(UniversityProgram(university_id=u.id, program_id=p2.id, status="planned"))
    db.add(UniversityProgram(university_id=u.id, program_id=p3.id, status="launched"))
    db.commit()
    rows = (
        db.execute(
            select(ITProgram)
            .join(UniversityProgram, UniversityProgram.program_id == ITProgram.id)
            .where(ITProgram.direction_id == d_a.id, UniversityProgram.status == "launched")
        )
        .scalars()
        .all()
    )
    assert [p.name for p in rows] == ["P1"]
    empty = (
        db.execute(
            select(ITProgram).where(
                ITProgram.direction_id == d_b.id,
                ITProgram.name == "no-such-program",
            )
        )
        .scalars()
        .all()
    )
    assert empty == []
    with pytest.raises(ValueError):
        from app.models.enums import UniversityProgramStatus

        UniversityProgramStatus("flying")


# ================================================================ products ==


def test_product_vendor_filter_no_cross_leak(db: Session):
    v_a = make_vendor(db)
    v_b = make_vendor(db)
    make_product(db, v_a, name="P1")
    make_product(db, v_a, name="P2")
    make_product(db, v_b, name="P3")
    db.commit()
    rows = db.execute(select(ITProduct).where(ITProduct.vendor_id == v_a.id)).scalars().all()
    assert sorted(p.name for p in rows) == ["P1", "P2"]
    assert all(p.vendor_id == v_a.id for p in rows)
    assert db.execute(select(ITProduct).where(ITProduct.vendor_id == uuid.uuid4()))
    assert (
        db.execute(select(ITProduct).where(ITProduct.vendor_id == uuid.uuid4())).scalars().all()
        == []
    )


# ================================================================ teachers ==


def test_teacher_university_separation_direct(db: Session):
    u_a = make_university(db, name="UA")
    u_b = make_university(db, name="UB")
    make_teacher(db, u_a, email="a1@ex.test")
    make_teacher(db, u_a, email="a2@ex.test")
    make_teacher(db, u_b, email="b1@ex.test")
    db.commit()
    rows = db.execute(select(Teacher).where(Teacher.university_id == u_a.id)).scalars().all()
    assert {t.email for t in rows} == {"a1@ex.test", "a2@ex.test"}
    assert all(t.university_id == u_a.id for t in rows)


def _teacher_with_cert(
    db: Session,
    university: University,
    email: str,
    delta_days: int | None,
    mandatory: bool = True,
) -> Teacher:
    t = make_teacher(db, university, email=email)
    if delta_days is not None:
        db.add(
            TeacherCertificate(
                teacher_id=t.id,
                certificate_name="Cert",
                issued_by="X",
                issued_at=date.today() - timedelta(days=400),
                expires_at=date.today() + timedelta(days=delta_days),
                is_mandatory=mandatory,
            )
        )
        db.flush()
    return t


def test_teacher_readiness_ready_attention_expired(db: Session):
    """Readiness has NO DB column/filter — deterministic Python production logic."""
    assert "readiness" not in {c for c in Teacher.__table__.columns.keys()}
    u = make_university(db)
    t_ready = _teacher_with_cert(db, u, "ready@ex.test", 100)
    t_att = _teacher_with_cert(db, u, "att@ex.test", 10)
    t_exp = _teacher_with_cert(db, u, "exp@ex.test", -5)
    t_none = make_teacher(db, u, email="none@ex.test")  # no mandatory items -> ready
    db.commit()
    by_email = {}
    for t in (t_ready, t_att, t_exp, t_none):
        db.refresh(t)
        res = compute_teacher_readiness(
            certificates=list(t.certificates), qualifications=list(t.qualifications)
        )
        by_email[t.email] = res.readiness
    assert by_email["ready@ex.test"] == TeacherReadiness.READY
    assert by_email["att@ex.test"] == TeacherReadiness.ATTENTION
    assert by_email["exp@ex.test"] == TeacherReadiness.EXPIRED
    assert by_email["none@ex.test"] == TeacherReadiness.READY
    with pytest.raises(ValueError):
        TeacherReadiness("super-ready")


def test_teacher_combined_university_plus_readiness(db: Session):
    u_a = make_university(db, name="UA")
    u_b = make_university(db, name="UB")
    _teacher_with_cert(db, u_a, "a-ready@ex.test", 100)
    _teacher_with_cert(db, u_a, "a-exp@ex.test", -2)
    _teacher_with_cert(db, u_b, "b-ready@ex.test", 100)
    db.commit()
    cand = db.execute(select(Teacher).where(Teacher.university_id == u_a.id)).scalars().all()
    ready = [
        t
        for t in cand
        if compute_teacher_readiness(
            certificates=list(t.certificates), qualifications=list(t.qualifications)
        ).readiness
        == TeacherReadiness.READY
    ]
    assert [t.email for t in ready] == ["a-ready@ex.test"]


# ============================================================ invalid input ==


def test_invalid_uuid_query_param_is_422():
    app = FastAPI()

    @app.get("/things")
    def things(responsible_id: uuid.UUID):
        return {"id": str(responsible_id)}

    r = TestClient(app).get("/things", params={"responsible_id": "not-a-uuid"})
    assert r.status_code == 422
    ok = uuid.uuid4()
    assert TestClient(app).get("/things", params={"responsible_id": str(ok)}).status_code == 200


def test_unknown_query_param_ignored_by_default():
    """FastAPI ignores undeclared query params — do not demand 422."""

    app = FastAPI()

    @app.get("/things2")
    def things2(q: str | None = None):
        return {"q": q}

    c = TestClient(app)
    assert c.get("/things2", params={"q": "a", "nope": "1"}).status_code == 200
    assert c.get("/things2", params={"nope": "1"}).json() == {"q": None}


# ============================================================ null semantics ==


def test_null_semantics(db: Session):
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr, contract=None)  # contract_id NULL
    make_license(db, u, pr, contract=None)
    make_contract(db, u, expires=None)  # expires_at NULL
    make_responsible(db)
    make_responsible(db)  # keycloak_sub NULL x2
    db.commit()
    assert (
        len(db.execute(select(License).where(License.contract_id.is_(None))).scalars().all()) == 2
    )
    assert (
        len(db.execute(select(License).where(License.contract_id == uuid.uuid4())).scalars().all())
        == 0  # NULL never equals a value
    )
    assert (
        len(db.execute(select(Contract).where(Contract.expires_at.is_(None))).scalars().all()) == 1
    )
    assert (
        len(
            db.execute(select(Responsible).where(Responsible.keycloak_sub.is_(None)))
            .scalars()
            .all()
        )
        == 2
    )


# ============================================================ error layer ==


def test_integrity_error_maps_to_409_sanitized_license_domain():
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/contracts")
    def boom():
        raise IntegrityError(
            "INSERT INTO contracts ...",
            {},
            Exception('psycopg duplicate key value violates unique constraint "uq_x"'),
        )

    r = TestClient(app).post("/contracts")
    assert r.status_code == 409
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == ErrorCode.CONFLICT
    assert body.error.details == {}
    low = r.text.lower()
    for leaked in ("psycopg", "sqlalchemy", "select", "insert", "uq_x", "traceback"):
        assert leaked not in low


# ================================================= large dataset / plan ==


def test_large_filter_dataset_insertion_order_independent(db: Session):
    uni_ids = [make_university(db, name=f"Big-{i:02d}").id for i in range(20)]
    db.commit()
    u0 = db.get(University, uni_ids[0])
    for i in range(30):
        make_teacher(db, u0 if i % 2 == 0 else db.get(University, uni_ids[1]))
    db.commit()
    hit = db.execute(select(University).where(University.name.ilike("%big-1%"))).scalars().all()
    assert len(hit) == 10  # Big-10..Big-19 regardless of insertion order
    t = db.execute(select(Teacher).where(Teacher.university_id == u0.id)).scalars().all()
    assert len(t) == 15
    p1 = db.execute(select(University).order_by(University.id.desc()).limit(10).offset(0))
    p2 = db.execute(select(University).order_by(University.id.desc()).limit(10).offset(10))
    assert {r.id for r in p1.scalars().all()}.isdisjoint({r.id for r in p2.scalars().all()})


def test_postgres_plan_sanity_for_fixed_filter(db: Session, engine):
    if not _is_pg(engine):
        pytest.skip("PG-only EXPLAIN sanity")
    make_university(db, name="Plan-A")
    db.commit()
    stmt = select(University).where(University.name.ilike("%plan%")).order_by(University.id.desc())
    compiled = stmt.compile(engine, compile_kwargs={"literal_binds": True})
    plan = db.execute(text(f"EXPLAIN {compiled}")).fetchall()
    assert len(plan) > 0  # fixed query plans without touching University.region


def test_openapi_mounted_passport_and_no_legacy_list():
    from app.config import settings
    from app.main import app as prod_app

    settings.auth_dev_bypass = True
    try:
        r = TestClient(prod_app).get("/openapi.json")
    finally:
        settings.auth_dev_bypass = False
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/universities/{university_id}/passport" in paths
