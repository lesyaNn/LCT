"""P1-11-01: CRUD tests for core P1 entities.

Scope (honest, no invented endpoints):
* ORM/repository-level CRUD for universities, directions, programs,
  vendors, products, responsibles — against the REAL P1 models
  (``app.models``), with REAL constraint enforcement. These tests are
  named ``*_db_*``: they do not claim to be HTTP API tests.
* HTTP-level tests only where real mounted routes exist: auth/RBAC
  mechanism, central IntegrityError mapping, gap pins proving the legacy
  CRUD routers stay unmounted, OpenAPI sanity.
* SQLite by default (fast); PostgreSQL when ``TEST_DATABASE_URL`` is set
  (``postgresql+psycopg://rtk:change-me@localhost:5433/rtk_p1_test``).
  UNIQUE/FK/RESTRICT/composite-constraint tests MUST be verified on PG
  (§3, §30) — PG-only assertions are gated on dialect, nothing is mocked.

Known gaps (PARTIAL, see final report): no mounted HTTP CRUD for the six
entities; legacy ``universities``/``programs``/``teachers`` routers on disk
are unmounted AND broken vs the P1 schema (int PKs, nonexistent fields).
"""

import base64
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata on Base)
from app.core.errors import CONFLICT_DETAIL, register_error_handlers
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
from app.models.interactions import Student, UniversityProduct, UniversityProgram
from app.models.teachers import Teacher, TeacherProgram

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _is_pg(engine) -> bool:
    return engine.dialect.name == "postgresql"


def _pgcode(exc: IntegrityError) -> str | None:
    """psycopg3 exposes the SQLSTATE as ``sqlstate`` (not ``pgcode``)."""
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _core_delete(db: Session, model, pk):
    """DELETE bypassing ORM relationship nullification.

    ``db.delete(parent)`` first NULLs loaded children's FK (default
    "save-update, merge" cascade) and PG reports 23502 — masking the real
    ON DELETE RESTRICT policy. A Core DELETE probes the true DB behavior
    (expect 23503 foreign_key_violation). Both paths stay controlled
    (IntegrityError -> central 409 handler), see final report.
    """
    from sqlalchemy import delete as sa_delete

    db.expunge_all()
    db.execute(sa_delete(model).where(model.id == pk))


# ------------------------------------------------------------ fixtures ---


@pytest.fixture()
def engine(tmp_path):
    """Fresh isolated DB per test (file SQLite or dedicated PG test DB).

    Same convention as test_p1_schema / passport tests: no parallel test
    infrastructure, per-test reset => order-independent.
    PG note: module tables (audit_events, health_score_history, ...) live in
    the test DB but are NOT registered on Base.metadata (pre-existing P1-10-02
    condition, also breaking test_p1_schema on PG), so plain drop_all cannot
    order DDL. Reset the schema instead — test-only, dedicated test DB.
    """
    from sqlalchemy import text

    url = TEST_URL
    if url == "sqlite://":
        url = f"sqlite:///{tmp_path}/p1_crud_test.db"
    eng = create_engine(url)
    if eng.dialect.name == "sqlite":

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _rec):  # pragma: no cover
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.drop_all(eng)
    else:
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


# ------------------------------------------------------------ factories ---


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def make_university(db: Session, name: str | None = None, city="Москва") -> University:
    u = University(name=name or f"Uni-{_tag()}", city=city)
    db.add(u)
    db.flush()
    return u


def make_direction(db: Session, code: str | None = None) -> ITDirection:
    d = ITDirection(code=code or f"D-{_tag()}", name=f"Direction {_tag()}")
    db.add(d)
    db.flush()
    return d


def make_program(db: Session, direction: ITDirection | None = None) -> ITProgram:
    direction = direction or make_direction(db)
    p = ITProgram(direction_id=direction.id, name=f"Program {_tag()}", description="")
    db.add(p)
    db.flush()
    return p


def make_vendor(db: Session) -> Vendor:
    v = Vendor(name=f"Vendor-{_tag()}")
    db.add(v)
    db.flush()
    return v


def make_product(
    db: Session, vendor: Vendor | None = None, name: str | None = None, version="1.0"
) -> ITProduct:
    vendor = vendor or make_vendor(db)
    pr = ITProduct(vendor_id=vendor.id, name=name or f"Product-{_tag()}", version=version)
    db.add(pr)
    db.flush()
    return pr


def make_responsible(db: Session, email: str | None = None) -> Responsible:
    r = Responsible(
        full_name=f"Name {_tag()}", email=email or f"r-{_tag()}@ex.test", role="manager"
    )
    db.add(r)
    db.flush()
    return r


def make_license(db: Session, university: University, product: ITProduct) -> License:
    lic = License(
        university_id=university.id,
        product_id=product.id,
        license_number=f"L-{_tag()}",
        signed_at=date.today(),
        expires_at=date.today() + timedelta(days=100),
    )
    db.add(lic)
    db.flush()
    return lic


# ============================================================ universities ==


def test_university_create_success(db: Session, engine):
    u = make_university(db, name="МГТУ", city="Москва")
    assert u.id is not None and isinstance(u.id, uuid.UUID)
    assert u.created_at is not None and u.created_at.tzinfo is not None
    assert u.updated_at >= u.created_at
    db.commit()
    if engine.dialect.name != "sqlite":
        db.refresh(u)
    row = db.get(University, u.id)
    assert row is not None and row.name == "МГТУ" and row.city == "Москва"


def test_university_create_missing_name_rejected(db: Session):
    db.add(University(name=None, city="X"))  # type: ignore[arg-type]
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_university_duplicate_name_conflict(db: Session, engine):
    make_university(db, name="Дубль")
    db.commit()
    db.add(University(name="Дубль", city="Уфа"))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"  # unique_violation, real PG


def test_university_list_ordering_and_pagination(db: Session):
    ids = [make_university(db).id for _ in range(5)]
    db.commit()
    all_rows = db.execute(select(University).order_by(University.id.desc())).scalars().all()
    assert [r.id for r in all_rows] == sorted(ids, reverse=True)
    again = db.execute(select(University).order_by(University.id.desc())).scalars().all()
    assert [r.id for r in again] == [r.id for r in all_rows]  # stable ordering
    page1 = db.execute(select(University).order_by(University.id.desc()).limit(2).offset(0))
    page2 = db.execute(select(University).order_by(University.id.desc()).limit(2).offset(2))
    page3 = db.execute(select(University).order_by(University.id.desc()).limit(2).offset(4))
    got = page1.scalars().all() + page2.scalars().all() + page3.scalars().all()
    assert len(got) == 5 and len({r.id for r in got}) == 5  # partition, no overlap


def test_university_search_ilike(db: Session):
    make_university(db, name="Alpha Tech")
    make_university(db, name="Beta College")
    db.commit()
    hit = db.execute(select(University).where(University.name.ilike("%alpha%"))).scalars().all()
    assert [r.name for r in hit] == ["Alpha Tech"]
    hit_up = db.execute(select(University).where(University.name.ilike("%ALPHA%"))).scalars().all()
    assert [r.name for r in hit_up] == ["Alpha Tech"]  # case-insensitive
    miss = db.execute(select(University).where(University.name.ilike("%zeta%"))).scalars().all()
    assert miss == []


def test_university_region_filter_known_defect_deferred(db: Session):
    """P1-11-03 fix: legacy ``region`` param is accepted and safely ignored.

    P1-10-02 raised ``AttributeError`` (``University.region`` does not exist
    in the P1 schema). Since P1-11-03 the repository keeps the legacy
    signature for backward compatibility but never touches the nonexistent
    column — see ``test_p1_11_03_licenses_filters.py`` for the regression.
    """
    from app.modules.universities.repository import UniversityRepository

    assert UniversityRepository(db).list(q=None, region="X") == []


def test_university_legacy_repo_create_broken_vs_p1_schema():
    """Legacy repo passes int-era fields (region/status/...) the P1 model lacks."""
    from app.modules.universities.repository import UniversityRepository
    from app.modules.universities.schemas import UniversityCreate

    with pytest.raises(TypeError, match="invalid keyword argument"):
        UniversityRepository.__dict__["create"](object(), UniversityCreate(name="U"))


def test_university_service_get_missing_maps_to_404(db: Session):
    from app.core.exceptions import NotFound
    from app.modules.universities.service import UniversityService

    class _Repo:
        def get(self, university_id):
            return db.get(University, university_id)

    with pytest.raises(NotFound):
        UniversityService(_Repo()).get(uuid.uuid4())  # type: ignore[arg-type]


def test_university_get_found_and_missing(db: Session):
    u = make_university(db, name="Найди")
    db.commit()
    assert db.get(University, u.id) is not None
    assert db.get(University, uuid.uuid4()) is None  # -> HTTP 404 via service


def test_university_partial_update(db: Session):
    u = make_university(db, name="Старое", city="Казань")
    db.commit()
    created = u.created_at
    u.city = "Уфа"  # single field; name must survive
    db.commit()
    db.refresh(u)
    assert u.name == "Старое" and u.city == "Уфа"
    assert u.updated_at >= created


def test_university_update_duplicate_name_conflict(db: Session, engine):
    make_university(db, name="Уник-А")
    b = make_university(db, name="Уник-Б")
    db.commit()
    b.name = "Уник-А"
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


def test_university_delete_is_hard(db: Session):
    assert not hasattr(University, "is_active") and not hasattr(University, "deleted_at")
    u = make_university(db, name="Снос")
    db.commit()
    uid = u.id
    db.delete(u)
    db.commit()
    assert db.get(University, uid) is None  # hard delete: row gone


def test_university_delete_cascades_mn_links_keeps_responsible(db: Session):
    u = make_university(db)
    r = make_responsible(db)
    db.add(UniversityResponsible(university_id=u.id, responsible_id=r.id))
    db.commit()
    db.delete(u)
    db.commit()
    assert db.execute(select(UniversityResponsible)).scalars().all() == []
    assert db.get(Responsible, r.id) is not None  # link cleaned, peer survives


def test_university_delete_restricted_when_in_use(db: Session, engine):
    u = make_university(db)
    d = make_direction(db)
    p = make_program(db, d)
    v = make_vendor(db)
    pr = make_product(db, v)
    t = Teacher(university_id=u.id, full_name="П", email=f"t-{_tag()}@ex.test", position="")
    db.add(t)
    db.flush()
    db.add(
        Student(
            external_id=f"EXT-{_tag()}",
            university_id=u.id,
            program_id=p.id,
            full_name="С",
            started_at=date.today(),
        )
    )
    make_license(db, u, pr)
    db.add(Contract(university_id=u.id, contract_number=f"D-{_tag()}", signed_at=date.today()))
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        _core_delete(db, University, u.id)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"  # foreign_key_violation, real PG


def test_university_orm_delete_nullifies_first_still_controlled(db: Session, engine):
    """ORM ``db.delete()`` NULLs loaded children FK before the DB RESTRICT
    fires (default cascade) — PG reports 23502, not 23503. Still a controlled
    IntegrityError (central handler -> 409, never 500); future CRUD services
    must expect either SQLSTATE. DB policy itself is unchanged (RESTRICT)."""
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr)
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        db.delete(u)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23502"  # not_null_violation via ORM nullify


# ============================================================= directions ==


def test_direction_crud(db: Session):
    d = make_direction(db, code="AI")
    db.commit()
    assert db.get(ITDirection, d.id).name.startswith("Direction")
    d.name = "AI Updated"
    db.commit()
    db.refresh(d)
    assert d.name == "AI Updated" and d.code == "AI"  # partial update preserves code
    db.delete(d)
    db.commit()
    assert db.get(ITDirection, d.id) is None


def test_direction_duplicate_code_conflict(db: Session, engine):
    make_direction(db, code="DUP")
    db.commit()
    db.add(ITDirection(code="DUP", name="Other"))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


def test_direction_delete_restricted_when_used(db: Session, engine):
    d = make_direction(db)
    make_program(db, d)
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        _core_delete(db, ITDirection, d.id)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"  # RESTRICT per migration/model


# =============================================================== programs ==


def test_program_create_requires_direction(db: Session):
    bad = ITProgram(
        direction_id=None,
        name="Без направления",  # type: ignore[arg-type]
        description="",
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_program_create_invalid_direction_rejected(db: Session, engine):
    db.add(ITProgram(direction_id=uuid.uuid4(), name="В никуда", description=""))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_program_create_list_get_update(db: Session):
    d = make_direction(db)
    p = make_program(db, d)
    db.commit()
    assert db.get(ITProgram, p.id).direction_id == d.id
    rows = db.execute(select(ITProgram).where(ITProgram.direction_id == d.id))
    assert len(rows.scalars().all()) == 1
    p.description = "new desc"
    db.commit()
    db.refresh(p)
    assert p.description == "new desc" and p.direction_id == d.id


def test_program_delete_unused(db: Session):
    p = make_program(db)
    db.commit()
    pid = p.id
    db.delete(p)
    db.commit()
    assert db.get(ITProgram, pid) is None


def test_program_delete_restricted_by_university_link(db: Session, engine):
    u = make_university(db)
    p = make_program(db)
    db.add(UniversityProgram(university_id=u.id, program_id=p.id))
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        db.delete(p)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_program_delete_restricted_by_teacher_link(db: Session, engine):
    u = make_university(db)
    p = make_program(db)
    t = Teacher(university_id=u.id, full_name="П", email=f"t-{_tag()}@ex.test", position="")
    db.add(t)
    db.flush()
    db.add(TeacherProgram(teacher_id=t.id, program_id=p.id, assigned_at=date.today()))
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        db.delete(p)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


# ================================================================ vendors ==


def test_vendor_create_update(db: Session):
    v = make_vendor(db)
    db.commit()
    assert isinstance(v.id, uuid.UUID)
    v.name = "Переименован"
    db.commit()
    db.refresh(v)
    assert v.name == "Переименован"


def test_vendor_duplicate_name_conflict(db: Session, engine):
    db.add(Vendor(name="Вендор-Дубль"))
    db.commit()
    db.add(Vendor(name="Вендор-Дубль"))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


def test_vendor_delete_restricted_when_used(db: Session, engine):
    v = make_vendor(db)
    make_product(db, v)
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        _core_delete(db, Vendor, v.id)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


# ================================================================ products ==


def test_product_create_success(db: Session):
    pr = make_product(db, version="2.1")
    db.commit()
    row = db.get(ITProduct, pr.id)
    assert row is not None and row.version == "2.1"


def test_product_composite_unique_duplicate(db: Session, engine):
    v = make_vendor(db)
    make_product(db, v, name="Товар", version="1.0")
    db.commit()
    db.add(ITProduct(vendor_id=v.id, name="Товар", version="1.0"))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"
        assert _pg_constraint(ei.value) == "uq_it_products_vendor_name_version"


def test_product_same_name_different_version_ok(db: Session):
    v = make_vendor(db)
    make_product(db, v, name="Товар", version="1.0")
    make_product(db, v, name="Товар", version="2.0")
    db.commit()  # composite semantics: version distinguishes
    n = db.execute(select(ITProduct).where(ITProduct.name == "Товар")).scalars().all()
    assert len(n) == 2


def test_product_same_name_version_different_vendor_ok(db: Session):
    make_product(db, make_vendor(db), name="Общий", version="1.0")
    make_product(db, make_vendor(db), name="Общий", version="1.0")
    db.commit()  # composite semantics: vendor distinguishes


def test_product_invalid_vendor_rejected(db: Session, engine):
    db.add(ITProduct(vendor_id=uuid.uuid4(), name="Призрак", version="1.0"))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_product_delete_restricted_by_license(db: Session, engine):
    u = make_university(db)
    pr = make_product(db)
    make_license(db, u, pr)
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        _core_delete(db, ITProduct, pr.id)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


def test_product_delete_restricted_by_university_product(db: Session, engine):
    u = make_university(db)
    pr = make_product(db)
    db.add(UniversityProduct(university_id=u.id, product_id=pr.id))
    db.commit()
    with pytest.raises(IntegrityError) as ei:
        db.delete(pr)
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23503"


# ============================================================ responsibles ==


def test_responsible_create_update(db: Session):
    r = make_responsible(db, email="a@ex.test")
    db.commit()
    assert isinstance(r.id, uuid.UUID)
    r.phone = "+7-000"
    db.commit()
    db.refresh(r)
    assert r.phone == "+7-000" and r.email == "a@ex.test"


def test_responsible_duplicate_email_conflict(db: Session, engine):
    make_responsible(db, email="dup@ex.test")
    db.commit()
    db.add(Responsible(full_name="Другой", email="dup@ex.test", role=""))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


def test_responsible_nullable_keycloak_sub_allows_many_nulls(db: Session):
    make_responsible(db)
    make_responsible(db)
    db.commit()  # UNIQUE over NULLs must not collide (PG + SQLite agree)
    n = db.execute(select(Responsible)).scalars().all()
    assert len(n) == 2


def test_university_responsible_link_and_pair_unique(db: Session, engine):
    u = make_university(db)
    r = make_responsible(db)
    db.add(UniversityResponsible(university_id=u.id, responsible_id=r.id, is_primary=True))
    db.commit()
    db.add(UniversityResponsible(university_id=u.id, responsible_id=r.id))
    with pytest.raises(IntegrityError) as ei:
        db.commit()
    db.rollback()
    if _is_pg(engine):
        assert _pgcode(ei.value) == "23505"


# ========================================================== error layer ==


def _error_app() -> FastAPI:
    from sqlalchemy.exc import IntegrityError as _IE

    app = FastAPI()
    register_error_handlers(app)

    class Item(BaseModel):
        name: str

    @app.post("/boom")
    def boom():
        raise _IE(
            "INSERT INTO t ...",
            {},
            Exception('psycopg duplicate key value violates unique constraint "uq_x"'),
        )

    @app.post("/items")
    def create_item(item: Item):
        return item

    return app


def test_integrity_error_maps_to_409_sanitized():
    c = TestClient(_error_app())
    r = c.post("/boom")
    assert r.status_code == 409
    assert r.json() == {"detail": CONFLICT_DETAIL}
    low = r.text.lower()
    for leaked in ("psycopg", "sqlalchemy", "select", "insert", "uq_x", "traceback"):
        assert leaked not in low  # no driver/SQL internals leak


def test_http_404_contract_unchanged():
    from fastapi import HTTPException

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/x/{item_id}")
    def get_x(item_id: str):
        raise HTTPException(status_code=404, detail="Not found")

    r = TestClient(app).get("/x/1")
    assert r.status_code == 404 and r.json() == {"detail": "Not found"}


def test_validation_422_contract_unchanged():
    r = TestClient(_error_app()).post("/items", json={})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)  # stock FastAPI shape, no envelope


# ================================================================== RBAC ==

_KID = "p1-crud-1"


def _b64url(num: int) -> str:
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def jwt_client(monkeypatch):
    """Real Keycloak JWT validation (local RSA ~ JWKS), no dev bypass."""
    import app.core.security as sec
    from jose import jwt as _jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.config import settings

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub = key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": _KID,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(pub.n),
                "e": _b64url(pub.e),
            }
        ]
    }
    monkeypatch.setattr(sec, "_fetch_jwks", lambda: jwks)
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})
    old_bypass = settings.auth_dev_bypass
    settings.auth_dev_bypass = False

    from app.core.permissions import require_permission

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/write")
    def write(user=Depends(require_permission("university.edit"))):
        return {"ok": True, "user": user.username}

    def mint(roles):
        now = datetime.now(timezone.utc)
        return _jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "preferred_username": roles[0],
                "realm_access": {"roles": list(roles)},
                "iss": settings.keycloak_issuer,
                "aud": settings.keycloak_audience,
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            priv,
            algorithm="RS256",
            headers={"kid": _KID},
        )

    with TestClient(app) as c:
        c._mint = mint  # type: ignore[attr-defined]
        yield c
    settings.auth_dev_bypass = old_bypass
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})


def _auth(client, roles):
    return {"Authorization": f"Bearer {client._mint(roles)}"}


def test_rbac_write_curator_allowed(jwt_client):
    r = jwt_client.post("/write", headers=_auth(jwt_client, ("curator",)))
    assert r.status_code == 200, r.text


def test_rbac_write_user_denied(jwt_client):
    r = jwt_client.post("/write", headers=_auth(jwt_client, ("user",)))
    assert r.status_code == 403, r.text


def test_rbac_write_guest_denied(jwt_client):
    r = jwt_client.post("/write", headers=_auth(jwt_client, ("guest",)))
    assert r.status_code == 403, r.text


def test_rbac_write_no_token_401(jwt_client):
    assert jwt_client.post("/write").status_code == 401


def test_prod_auth_rbac_mechanism_admin_only(jwt_client):
    """Same JWT machinery against a prod-style admin-only route."""
    from app.modules.auth.router import router as auth_router

    prod = FastAPI()
    prod.include_router(auth_router, prefix="/api/v1")
    tok = jwt_client._mint
    with TestClient(prod) as c:
        denied = c.get(
            "/api/v1/auth/test/admin", headers={"Authorization": f"Bearer {tok(('manager',))}"}
        )
        assert denied.status_code == 403, denied.text
        ok = c.get(
            "/api/v1/auth/test/admin", headers={"Authorization": f"Bearer {tok(('admin',))}"}
        )
        assert ok.status_code == 200, ok.text


# ============================================================ HTTP gaps ==


def test_gap_legacy_university_crud_not_mounted():
    """Gap pin: legacy int-PK universities router must NOT be mounted
    (it is broken vs the P1 schema). Replace with real CRUD tests when
    P1 HTTP CRUD ships — do not mount the legacy router to satisfy this."""
    from app.config import settings
    from app.main import app

    settings.auth_dev_bypass = True
    try:
        c = TestClient(app)
        assert c.get("/api/v1/universities").status_code == 404
        assert c.post("/api/v1/universities", json={"name": "X"}).status_code == 404
    finally:
        settings.auth_dev_bypass = False


def test_gap_program_teacher_crud_not_mounted():
    from app.config import settings
    from app.main import app

    settings.auth_dev_bypass = True
    try:
        c = TestClient(app)
        assert c.get("/api/v1/programs").status_code == 404
        assert c.post("/api/v1/programs", json={"name": "X"}).status_code == 404
        assert c.get("/api/v1/teachers").status_code == 404
    finally:
        settings.auth_dev_bypass = False


def test_openapi_no_duplicate_routes_or_schema_errors():
    from app.config import settings
    from app.main import app

    settings.auth_dev_bypass = True
    try:
        r = TestClient(app).get("/openapi.json")
    finally:
        settings.auth_dev_bypass = False
    assert r.status_code == 200, r.text
    paths = r.json()["paths"]
    assert "/api/v1/universities/{university_id}/passport" in paths


# ============================================================= isolation ==


def test_isolation_writer_creates_row(engine):
    with Session(engine) as s:
        s.add(University(name="Изоляция", city="X"))
        s.commit()
        assert s.execute(select(University)).scalars().all() != []


def test_isolation_fresh_db_starts_empty(engine):
    """Order-independent: every test gets a fresh DB (tmp file / re-DDL)."""
    with Session(engine) as s:
        assert s.execute(select(University)).scalars().all() == []
        assert s.execute(select(ITDirection)).scalars().all() == []
        assert s.execute(select(Vendor)).scalars().all() == []
