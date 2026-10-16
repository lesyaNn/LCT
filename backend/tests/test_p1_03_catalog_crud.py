"""P1-03: mounted HTTP CRUD for the catalog + pagination/search/filters.

All DB integration tests run on PostgreSQL (``TEST_DATABASE_URL`` pointing
at the dedicated ``rtk_p1_test`` DB); the schema always comes from the
canonical SQL migrations (``tests/db_helpers.py``). No SQLite, no
``create_all`` — the HTTP stack is tested for real via ``TestClient`` with
``get_db`` overridden to the PG engine.

Coverage per entity (universities, directions, programs, products, vendors,
responsibles): create / get / list / update / delete / 404s / duplicate
UNIQUE -> 409 / FK violation -> 409 / RBAC matrix. Plus: pagination
(disjoint pages, total, stable ordering), case-insensitive search,
single/combined/empty filters, sorting whitelist, query-count (N+1)
regression, OpenAPI route inventory.
"""

import base64
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import (
    ITDirection,
    License,
    Responsible,
    University,
    Vendor,
)

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _tag() -> str:
    return uuid.uuid4().hex[:8]


# --------------------------------------------------------------- fixtures


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


@pytest.fixture()
def client(engine):
    """Bypass-auth HTTP client bound to the PG engine."""

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = old


@pytest.fixture()
def select_counter(engine):
    """Counts ONLY SELECT statements."""
    count = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            count["n"] += 1

    yield count
    event.remove(engine, "before_cursor_execute", _count)


_KID = "p1-03-1"


def _b64url(num: int) -> str:
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def auth_client(engine, monkeypatch):
    """Real JWT validation (local RSA ~ JWKS), dev bypass OFF, real app+DB."""
    import app.core.security as sec
    from jose import jwt as _jwt
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

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override

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
    app.dependency_overrides.pop(get_db, None)
    settings.auth_dev_bypass = old_bypass
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})


def _auth(c, roles):
    return {"Authorization": f"Bearer {c._mint(roles)}"}


# ---------------------------------------------------------------- helpers


def _uni(client, name=None, city="Moscow"):
    r = client.post("/api/v1/universities", json={"name": name or f"Uni-{_tag()}", "city": city})
    assert r.status_code == 201, r.text
    return r.json()


def _direction(client, code=None, name=None):
    r = client.post(
        "/api/v1/directions",
        json={"code": code or f"D-{_tag()}", "name": name or f"Direction {_tag()}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _program(client, direction_id, name=None):
    r = client.post(
        "/api/v1/programs",
        json={"direction_id": str(direction_id), "name": name or f"Program {_tag()}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _vendor(client, name=None):
    r = client.post("/api/v1/vendors", json={"name": name or f"Vendor-{_tag()}"})
    assert r.status_code == 201, r.text
    return r.json()


def _product(client, vendor_id, name=None, version="1.0"):
    r = client.post(
        "/api/v1/products",
        json={"vendor_id": str(vendor_id), "name": name or f"Product-{_tag()}", "version": version},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _responsible(client, email=None, full_name=None):
    r = client.post(
        "/api/v1/responsibles",
        json={"full_name": full_name or f"Name {_tag()}", "email": email or f"r-{_tag()}@ex.test"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ============================================================ universities


def test_university_http_crud(client):
    created = _uni(client, name="МГТУ", city="Москва")
    assert uuid.UUID(created["id"])
    assert created["responsibles"] == []
    assert created["created_at"] and created["updated_at"]
    uid = created["id"]

    got = client.get(f"/api/v1/universities/{uid}")
    assert got.status_code == 200, got.text
    assert got.json()["name"] == "МГТУ"

    lst = client.get("/api/v1/universities")
    assert lst.status_code == 200
    body = lst.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] == 1 and body["items"][0]["id"] == uid

    patched = client.patch(f"/api/v1/universities/{uid}", json={"city": "Казань"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["city"] == "Казань"
    assert patched.json()["name"] == "МГТУ"  # partial update preserves name

    assert client.delete(f"/api/v1/universities/{uid}").status_code == 204
    assert client.get(f"/api/v1/universities/{uid}").status_code == 404
    assert client.delete(f"/api/v1/universities/{uid}").status_code == 404


def test_university_duplicate_name_409_sanitized(client):
    _uni(client, name="Дубль")
    r = client.post("/api/v1/universities", json={"name": "Дубль"})
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "CONFLICT"
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]
    low = r.text.lower()
    for leaked in ("psycopg", "traceback", "uq_universities", "insert into"):
        assert leaked not in low


def test_university_validation_422(client):
    assert client.post("/api/v1/universities", json={}).status_code == 422
    assert client.post("/api/v1/universities", json={"name": ""}).status_code == 422
    assert client.get("/api/v1/universities/not-a-uuid").status_code == 422
    assert client.get("/api/v1/universities?page=0").status_code == 422
    assert client.get("/api/v1/universities?page_size=101").status_code == 422


def test_university_delete_restricted_when_licensed(client, db):
    u = _uni(client)
    v = _vendor(client)
    p = _product(client, v["id"])
    db.add(
        License(
            university_id=uuid.UUID(u["id"]),
            product_id=uuid.UUID(p["id"]),
            license_number="LIC-1",
            signed_at=date.today(),
            expires_at=date.today() + timedelta(days=100),
        )
    )
    db.commit()
    r = client.delete(f"/api/v1/universities/{u['id']}")
    assert r.status_code == 409, r.text


def test_university_delete_is_hard(client, db):
    u = _uni(client, name="Снос")
    uid = u["id"]
    assert client.delete(f"/api/v1/universities/{uid}").status_code == 204
    assert db.get(University, uuid.UUID(uid)) is None


def test_university_pagination_disjoint_stable(client):
    ids = [_uni(client, name=f"Pag-{i:02d}")["id"] for i in range(7)]
    p1 = client.get("/api/v1/universities?page=1&page_size=3").json()
    p2 = client.get("/api/v1/universities?page=2&page_size=3").json()
    p3 = client.get("/api/v1/universities?page=3&page_size=3").json()
    assert (p1["total"], p2["total"], p3["total"]) == (7, 7, 7)
    assert len(p1["items"]) == 3 and len(p2["items"]) == 3 and len(p3["items"]) == 1
    got = [it["id"] for it in p1["items"] + p2["items"] + p3["items"]]
    assert sorted(got) == sorted(ids) and len(set(got)) == 7  # partition, no overlap
    again = client.get("/api/v1/universities?page=1&page_size=3").json()
    assert [it["id"] for it in again["items"]] == [it["id"] for it in p1["items"]]
    empty = client.get("/api/v1/universities?page=99&page_size=3").json()
    assert empty["items"] == [] and empty["total"] == 7


def test_university_search_case_insensitive(client):
    _uni(client, name="Alpha Tech")
    _uni(client, name="Beta College")
    _uni(client, name="Gamma", city="Almaty")
    hit = client.get("/api/v1/universities?search=alpha").json()
    assert [it["name"] for it in hit["items"]] == ["Alpha Tech"]
    hit_up = client.get("/api/v1/universities?search=ALPHA").json()
    assert [it["name"] for it in hit_up["items"]] == ["Alpha Tech"]
    by_city = client.get("/api/v1/universities?search=almaty").json()
    assert [it["name"] for it in by_city["items"]] == ["Gamma"]
    miss = client.get("/api/v1/universities?search=zzz-no-such").json()
    assert miss["items"] == [] and miss["total"] == 0


def test_university_filters_single_combined_empty(client):
    r1 = _responsible(client)
    u1 = _uni(client, name="F1", city="Moscow")
    u2 = _uni(client, name="F2", city="Moscow")
    u3 = _uni(client, name="F3", city="Kazan")
    client.post(f"/api/v1/universities/{u1['id']}/responsibles/{r1['id']}", json={})
    client.post(f"/api/v1/universities/{u3['id']}/responsibles/{r1['id']}", json={})

    by_city = client.get("/api/v1/universities?city=Moscow").json()
    assert sorted(it["id"] for it in by_city["items"]) == sorted([u1["id"], u2["id"]])

    by_resp = client.get(f"/api/v1/universities?responsible_id={r1['id']}").json()
    assert sorted(it["id"] for it in by_resp["items"]) == sorted([u1["id"], u3["id"]])

    both = client.get(f"/api/v1/universities?city=Moscow&responsible_id={r1['id']}").json()
    assert [it["id"] for it in both["items"]] == [u1["id"]]  # combined = AND

    assert client.get("/api/v1/universities?city=Nowhere").json()["items"] == []
    assert client.get(f"/api/v1/universities?responsible_id={uuid.uuid4()}").json()["items"] == []


def test_university_sorting_whitelist(client):
    _uni(client, name="Bravo")
    _uni(client, name="Alpha")
    _uni(client, name="Charlie")
    desc = client.get("/api/v1/universities?sort_by=name&sort_order=desc").json()
    assert [it["name"] for it in desc["items"]] == ["Charlie", "Bravo", "Alpha"]
    asc = client.get("/api/v1/universities?sort_by=name&sort_order=asc").json()
    assert [it["name"] for it in asc["items"]] == ["Alpha", "Bravo", "Charlie"]
    assert client.get("/api/v1/universities?sort_by=region").status_code == 422
    assert client.get("/api/v1/universities?sort_order=sideways").status_code == 422


def test_university_region_deprecated_ignored(client):
    _uni(client, name="Reg")
    r = client.get("/api/v1/universities?region=anything")
    assert r.status_code == 200, r.text  # accepted, safely ignored
    assert r.json()["total"] == 1


def test_university_assign_unassign_responsible(client):
    u = _uni(client)
    r1 = _responsible(client)
    a1 = client.post(
        f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}",
        json={"role_in_university": "curator", "is_primary": True},
    )
    assert a1.status_code == 201, a1.text
    link = a1.json()
    assert link["role_in_university"] == "curator" and link["is_primary"] is True

    a2 = client.post(f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}", json={})
    assert a2.status_code == 200  # idempotent re-assign
    assert a2.json()["id"] == link["id"]

    detail = client.get(f"/api/v1/universities/{u['id']}").json()
    assert [x["id"] for x in detail["responsibles"]] == [r1["id"]]

    assert (
        client.delete(f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}").status_code == 204
    )
    assert (
        client.delete(f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}").status_code == 404
    )
    assert (
        client.post(
            f"/api/v1/universities/{uuid.uuid4()}/responsibles/{r1['id']}", json={}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/universities/{u['id']}/responsibles/{uuid.uuid4()}", json={}
        ).status_code
        == 404
    )


def test_passport_program_relation_is_atomic_and_rejects_duplicate(client, engine):
    from sqlalchemy import select
    from app.models.interactions import UniversityProgram

    university = _uni(client)
    direction = _direction(client)
    program = _program(client, direction["id"])
    url = f"/api/v1/universities/{university['id']}/programs"
    created = client.post(url, json={"program_id": program["id"], "status": "active"})
    assert created.status_code == 201, created.text
    assert created.json()["program_id"] == program["id"]
    assert client.post(url, json={"program_id": program["id"]}).status_code == 409
    passport = client.get(f"/api/v1/universities/{university['id']}/passport")
    assert passport.status_code == 200, passport.text
    assert program["id"] in [item["id"] for item in passport.json()["programs"]]
    with Session(engine) as db:
        links = db.scalars(select(UniversityProgram).where(
            UniversityProgram.university_id == uuid.UUID(university["id"])
        )).all()
        assert len(links) == 1


def test_passport_product_relation_is_atomic_and_rejects_duplicate(client, engine):
    from sqlalchemy import select
    from app.models.interactions import UniversityProduct

    university = _uni(client)
    vendor = _vendor(client)
    product = _product(client, vendor["id"])
    url = f"/api/v1/universities/{university['id']}/products"
    created = client.post(url, json={"product_id": product["id"], "status": "active"})
    assert created.status_code == 201, created.text
    assert created.json()["product_id"] == product["id"]
    assert client.post(url, json={"product_id": product["id"]}).status_code == 409
    passport = client.get(f"/api/v1/universities/{university['id']}/passport")
    assert passport.status_code == 200, passport.text
    assert product["id"] in [item["id"] for item in passport.json()["products"]]
    with Session(engine) as db:
        links = db.scalars(select(UniversityProduct).where(
            UniversityProduct.university_id == uuid.UUID(university["id"])
        )).all()
        assert len(links) == 1


def test_primary_responsible_change_preserves_old_link_and_audits(client, engine):
    from sqlalchemy import select
    from app.models.catalog import UniversityResponsible
    from app.modules.audit.models import AuditEvent

    university = _uni(client)
    first = _responsible(client)
    second = _responsible(client)
    prefix = f"/api/v1/universities/{university['id']}/responsibles"
    assert client.post(f"{prefix}/{first['id']}", json={"is_primary": True}).status_code == 201
    changed = client.patch(f"{prefix}/primary", json={
        "responsible_id": second["id"], "reason": "Передача ответственности",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["is_primary"] is True
    with Session(engine) as db:
        links = db.scalars(select(UniversityResponsible).where(
            UniversityResponsible.university_id == uuid.UUID(university["id"])
        )).all()
        assert len(links) == 2
        assert [str(link.responsible_id) for link in links if link.is_primary] == [second["id"]]
        event = db.scalars(select(AuditEvent).where(
            AuditEvent.university_id == uuid.UUID(university["id"]),
            AuditEvent.action == "ASSIGN_RESPONSIBLE",
            AuditEvent.entity_id == uuid.UUID(changed.json()["id"]),
        )).one()
        assert event.old_value["responsible_id"] == first["id"]
        assert event.new_value["responsible_id"] == second["id"]


def test_university_responsible_delete_cascades_link_keeps_university(client):
    u = _uni(client)
    r1 = _responsible(client)
    client.post(f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}", json={})
    assert client.delete(f"/api/v1/responsibles/{r1['id']}").status_code == 204
    detail = client.get(f"/api/v1/universities/{u['id']}").json()  # university survives
    assert detail["responsibles"] == []


# ============================================================= directions


def test_direction_http_crud(client):
    created = _direction(client, code="AI", name="AI Dir")
    did = created["id"]
    assert created["programs"] == []
    got = client.get(f"/api/v1/directions/{did}").json()
    assert got["code"] == "AI"
    patched = client.patch(f"/api/v1/directions/{did}", json={"name": "AI Updated"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "AI Updated"
    assert patched.json()["code"] == "AI"
    assert client.delete(f"/api/v1/directions/{did}").status_code == 204
    assert client.get(f"/api/v1/directions/{did}").status_code == 404
    assert client.delete(f"/api/v1/directions/{did}").status_code == 404


def test_direction_duplicate_code_409(client):
    _direction(client, code="DUP")
    r = client.post("/api/v1/directions", json={"code": "DUP", "name": "Other"})
    assert r.status_code == 409, r.text


def test_direction_delete_restricted_when_used(client):
    d = _direction(client)
    _program(client, d["id"])
    r = client.delete(f"/api/v1/directions/{d['id']}")
    assert r.status_code == 409, r.text  # real FK RESTRICT, not bypassed


def test_direction_search_and_sort(client):
    _direction(client, code="net-sec", name="Security")
    _direction(client, code="data-sci", name="Data")
    hit = client.get("/api/v1/directions?search=SEC").json()
    assert [it["code"] for it in hit["items"]] == ["net-sec"]
    by_name = client.get("/api/v1/directions?search=data").json()
    assert [it["code"] for it in by_name["items"]] == ["data-sci"]
    assert client.get("/api/v1/directions?search=zzz").json()["items"] == []
    desc = client.get("/api/v1/directions?sort_by=code&sort_order=desc").json()
    codes = [it["code"] for it in desc["items"]]
    assert codes == sorted(codes, reverse=True)
    assert client.get("/api/v1/directions?sort_by=bogus").status_code == 422


def test_direction_validation_422(client):
    assert client.post("/api/v1/directions", json={"code": "", "name": "x"}).status_code == 422
    assert client.post("/api/v1/directions", json={"code": "x"}).status_code == 422


# =============================================================== programs


def test_program_http_crud_with_direction_filter(client):
    d1 = _direction(client)
    d2 = _direction(client)
    p = _program(client, d1["id"], name="Analysis")
    pid = p["id"]
    assert p["direction_name"] == d1["name"]
    assert p["direction"]["id"] == d1["id"]

    got = client.get(f"/api/v1/programs/{pid}").json()
    assert got["direction_id"] == d1["id"]

    filtered = client.get(f"/api/v1/programs?direction_id={d1['id']}").json()
    assert [it["id"] for it in filtered["items"]] == [pid]
    other = client.get(f"/api/v1/programs?direction_id={d2['id']}").json()
    assert other["items"] == [] and other["total"] == 0  # cross-direction isolation

    patched = client.patch(
        f"/api/v1/programs/{pid}", json={"description": "new desc", "direction_id": d2["id"]}
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "new desc"
    assert patched.json()["direction_id"] == d2["id"]

    assert client.delete(f"/api/v1/programs/{pid}").status_code == 204
    assert client.get(f"/api/v1/programs/{pid}").status_code == 404


def test_program_invalid_direction_409(client):
    r = client.post("/api/v1/programs", json={"direction_id": str(uuid.uuid4()), "name": "Nowhere"})
    assert r.status_code == 409, r.text


def test_program_search_and_pagination(client):
    d = _direction(client)
    _program(client, d["id"], name="Alpha Prog")
    _program(client, d["id"], name="Beta Prog")
    hit = client.get("/api/v1/programs?search=ALPHA").json()
    assert [it["name"] for it in hit["items"]] == ["Alpha Prog"]
    assert client.get("/api/v1/programs?search=zzz").json()["items"] == []
    page = client.get("/api/v1/programs?page=1&page_size=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1


def test_program_delete_restricted_by_university_link(client, db):
    d = _direction(client)
    p = _program(client, d["id"])
    u = _uni(client)
    from app.models.interactions import UniversityProgram

    db.add(UniversityProgram(university_id=uuid.UUID(u["id"]), program_id=uuid.UUID(p["id"])))
    db.commit()
    r = client.delete(f"/api/v1/programs/{p['id']}")
    assert r.status_code == 409, r.text


# ================================================================ vendors


def test_vendor_http_crud(client):
    created = _vendor(client, name="РЕД СОФТ")
    vid = created["id"]
    assert created["products"] == []
    assert client.get(f"/api/v1/vendors/{vid}").json()["name"] == "РЕД СОФТ"
    patched = client.patch(f"/api/v1/vendors/{vid}", json={"name": "Renamed"})
    assert patched.status_code == 200 and patched.json()["name"] == "Renamed"
    assert client.delete(f"/api/v1/vendors/{vid}").status_code == 204
    assert client.get(f"/api/v1/vendors/{vid}").status_code == 404
    assert client.delete(f"/api/v1/vendors/{vid}").status_code == 404


def test_vendor_contacts_are_editable_and_visible_through_product(client):
    created = client.post("/api/v1/vendors", json={
        "name": "Vendor with contact",
        "contacts": [{"full_name": "Ирина", "email": "irina@example.org", "phone": "+70000000000"}],
    })
    assert created.status_code == 201, created.text
    vendor_id = created.json()["id"]
    assert len(created.json()["contacts"]) == 1
    assert created.json()["contacts"][0]["product_id"] is None
    product = _product(client, vendor_id)
    assert [contact["email"] for contact in client.get(f"/api/v1/products/{product['id']}").json()["contacts"]] == ["irina@example.org"]

    updated = client.patch(f"/api/v1/vendors/{vendor_id}", json={
        "contacts": [{"full_name": "Мария", "email": "maria@example.org"}],
    })
    assert updated.status_code == 200, updated.text
    assert [contact["email"] for contact in updated.json()["contacts"]] == ["maria@example.org"]
    assert [contact["email"] for contact in client.get(f"/api/v1/products/{product['id']}").json()["contacts"]] == ["maria@example.org"]


def test_passport_documents_filter_and_authenticated_download(client, db, tmp_path, monkeypatch):
    from app.models.interactions import Document
    from app.modules.workflow_attachments.router import get_storage
    from app.modules.workflow_attachments.storage import LocalStorageBackend

    university = _uni(client)
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: LocalStorageBackend(tmp_path)
    (tmp_path / "jury.txt").write_bytes(b"jury document")
    db.add_all([
        Document(university_id=uuid.UUID(university["id"]), document_type="contract", title="Жюри", file_path="jury.txt", file_name="jury.txt", file_size=13, mime_type="text/plain", status_raw="signed", uploaded_by_keycloak_sub="test"),
        Document(university_id=uuid.UUID(university["id"]), document_type="license", title="Лицензия", file_path="missing.txt", file_name="missing.txt", file_size=10, status_raw="draft", uploaded_by_keycloak_sub="test"),
    ])
    db.commit()
    base = f"/api/v1/universities/{university['id']}/passport/documents"
    page = client.get(base, params={"search": "Жюри", "document_type": "contract", "status": "signed", "page_size": 1})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["types"] == ["contract", "license"]
    document = page.json()["items"][0]
    assert document["file_available"] is True
    assert client.get(f"{base}/{document['id']}/download").content == b"jury document"
    assert client.get(base, params={"document_type": "license"}).json()["items"][0]["file_available"] is False
    try:
        uploaded = client.post(base, data={"document_type": "act", "title": "Новый акт"}, files={"file": ("act.pdf", b"act bytes", "application/pdf")})
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["file_available"] is True
        assert client.get(f"{base}/{uploaded.json()['id']}/download").content == b"act bytes"
        assert client.get(base, params={"document_type": "act"}).json()["total"] == 1
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_vendor_duplicate_name_409(client):
    _vendor(client, name="Dup-V")
    assert client.post("/api/v1/vendors", json={"name": "Dup-V"}).status_code == 409


def test_vendor_delete_restricted_when_used(client):
    v = _vendor(client)
    _product(client, v["id"])
    assert client.delete(f"/api/v1/vendors/{v['id']}").status_code == 409


def test_vendor_search(client):
    _vendor(client, name="Alpha Vendor")
    _vendor(client, name="Beta Vendor")
    hit = client.get("/api/v1/vendors?search=ALPHA").json()
    assert [it["name"] for it in hit["items"]] == ["Alpha Vendor"]
    assert client.get("/api/v1/vendors?search=zzz").json()["items"] == []


# ================================================================ products


def test_product_http_crud_with_vendor_filter(client):
    v1 = _vendor(client)
    v2 = _vendor(client)
    p = _product(client, v1["id"], name="РЕД ОС", version="8")
    pid = p["id"]
    assert p["vendor_name"] == v1["name"]
    assert p["vendor"]["id"] == v1["id"]

    by_vendor = client.get(f"/api/v1/products?vendor_id={v1['id']}").json()
    assert [it["id"] for it in by_vendor["items"]] == [pid]
    assert client.get(f"/api/v1/products?vendor_id={v2['id']}").json()["items"] == []

    patched = client.patch(f"/api/v1/products/{pid}", json={"version": "9"})
    assert patched.status_code == 200 and patched.json()["version"] == "9"
    assert patched.json()["name"] == "РЕД ОС"

    assert client.delete(f"/api/v1/products/{pid}").status_code == 204
    assert client.get(f"/api/v1/products/{pid}").status_code == 404


def test_product_composite_unique_409_and_variants_ok(client):
    v1 = _vendor(client)
    v2 = _vendor(client)
    _product(client, v1["id"], name="Товар", version="1.0")
    dup = client.post(
        "/api/v1/products", json={"vendor_id": v1["id"], "name": "Товар", "version": "1.0"}
    )
    assert dup.status_code == 409, dup.text
    _product(client, v1["id"], name="Товар", version="2.0")  # version distinguishes
    _product(client, v2["id"], name="Товар", version="1.0")  # vendor distinguishes


def test_product_invalid_vendor_409(client):
    r = client.post("/api/v1/products", json={"vendor_id": str(uuid.uuid4()), "name": "Ghost"})
    assert r.status_code == 409, r.text


def test_product_search_and_sort(client):
    v = _vendor(client)
    _product(client, v["id"], name="Alpha Soft", version="2.0")
    _product(client, v["id"], name="Beta Soft", version="1.0")
    hit = client.get("/api/v1/products?search=ALPHA").json()
    assert [it["name"] for it in hit["items"]] == ["Alpha Soft"]
    assert client.get("/api/v1/products?search=zzz").json()["items"] == []
    by_ver = client.get("/api/v1/products?sort_by=version&sort_order=desc").json()
    assert [it["version"] for it in by_ver["items"]] == ["2.0", "1.0"]


def test_product_delete_restricted_by_license(client, db):
    u = _uni(client)
    v = _vendor(client)
    p = _product(client, v["id"])
    db.add(
        License(
            university_id=uuid.UUID(u["id"]),
            product_id=uuid.UUID(p["id"]),
            license_number="LIC-P",
            signed_at=date.today(),
            expires_at=date.today() + timedelta(days=50),
        )
    )
    db.commit()
    assert client.delete(f"/api/v1/products/{p['id']}").status_code == 409


# ============================================================ responsibles


def test_responsible_http_crud(client):
    created = _responsible(client, email="a@ex.test")
    rid = created["id"]
    assert created["universities"] == []
    got = client.get(f"/api/v1/responsibles/{rid}").json()
    assert got["email"] == "a@ex.test"
    invalid = client.patch(f"/api/v1/responsibles/{rid}", json={"phone": "+7-000"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["field_errors"][0]["field"] == "phone"
    patched = client.patch(
        f"/api/v1/responsibles/{rid}",
        json={"phone": "+7 (999) 123-45-67", "role": "dean"},
    )
    assert patched.status_code == 200
    assert patched.json()["phone"] == "+7 (999) 123-45-67"
    assert patched.json()["email"] == "a@ex.test"
    assert client.delete(f"/api/v1/responsibles/{rid}").status_code == 204
    assert client.get(f"/api/v1/responsibles/{rid}").status_code == 404


def test_responsible_duplicate_email_409(client):
    _responsible(client, email="dup@ex.test")
    r = client.post("/api/v1/responsibles", json={"full_name": "Other", "email": "dup@ex.test"})
    assert r.status_code == 409, r.text


def test_responsible_keycloak_sub_unique_but_nullable(client):
    a = client.post(
        "/api/v1/responsibles",
        json={"full_name": "A", "email": "k1@ex.test", "keycloak_sub": "sub-1"},
    )
    assert a.status_code == 201
    dup = client.post(
        "/api/v1/responsibles",
        json={"full_name": "B", "email": "k2@ex.test", "keycloak_sub": "sub-1"},
    )
    assert dup.status_code == 409
    _responsible(client)  # NULL sub ...
    _responsible(client)  # ... never collides


def test_responsible_patch_email_conflict_409(client):
    _responsible(client, email="first@ex.test")
    second = _responsible(client, email="second@ex.test")
    r = client.patch(f"/api/v1/responsibles/{second['id']}", json={"email": "first@ex.test"})
    assert r.status_code == 409


def test_responsible_search_filters(client):
    r1 = _responsible(client, email="ivan@ex.test", full_name="Ivan Petrov")
    r1_id = r1["id"]
    client.patch(f"/api/v1/responsibles/{r1_id}", json={"role": "dean"})
    _responsible(client, email="petr@ex.test", full_name="Petr Sidorov")
    u = _uni(client)
    client.post(f"/api/v1/universities/{u['id']}/responsibles/{r1_id}", json={})

    by_name = client.get("/api/v1/responsibles?search=IVAN").json()
    assert [it["id"] for it in by_name["items"]] == [r1_id]
    by_email = client.get("/api/v1/responsibles?search=petr@ex").json()
    assert len(by_email["items"]) == 1
    assert client.get("/api/v1/responsibles?search=zzz").json()["items"] == []

    by_role = client.get("/api/v1/responsibles?role=dean").json()
    assert [it["id"] for it in by_role["items"]] == [r1_id]
    by_uni = client.get(f"/api/v1/responsibles?university_id={u['id']}").json()
    assert [it["id"] for it in by_uni["items"]] == [r1_id]
    both = client.get(f"/api/v1/responsibles?role=dean&university_id={u['id']}").json()
    assert [it["id"] for it in both["items"]] == [r1_id]
    assert client.get("/api/v1/responsibles?role=no-such-role").json()["items"] == []


# ======================================================= pagination shape


def test_pagination_contract_on_all_lists(client):
    for path in (
        "/api/v1/universities",
        "/api/v1/directions",
        "/api/v1/programs",
        "/api/v1/products",
        "/api/v1/vendors",
        "/api/v1/responsibles",
    ):
        body = client.get(path).json()
        assert set(body) == {"items", "page", "page_size", "total"}, path
        assert body["page"] == 1 and body["page_size"] == 20 and body["total"] == 0


# ============================================================ N+1 guard


def test_list_query_count_bounded(client, engine, select_counter):
    r1 = _responsible(client)
    u = _uni(client)
    client.post(f"/api/v1/universities/{u['id']}/responsibles/{r1['id']}", json={})
    d = _direction(client)
    _program(client, d["id"])
    v = _vendor(client)
    _product(client, v["id"])

    with Session(engine) as s:
        s.expire_all()
        select_counter["n"] = 0
        r = client.get(f"/api/v1/universities?responsible_id={r1['id']}")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["responsible"]["id"] == r1["id"]
        n_uni = select_counter["n"]

        for _ in range(9):
            extra = _uni(client)
            linked = client.post(
                f"/api/v1/universities/{extra['id']}/responsibles/{r1['id']}", json={}
            )
            assert linked.status_code in (200, 201), linked.text
        select_counter["n"] = 0
        many = client.get(f"/api/v1/universities?responsible_id={r1['id']}")
        assert many.status_code == 200
        assert many.json()["total"] == len(many.json()["items"]) == 10
        n_uni_many = select_counter["n"]

        select_counter["n"] = 0
        r = client.get(f"/api/v1/programs?direction_id={d['id']}")
        assert r.status_code == 200
        n_prog = select_counter["n"]

        select_counter["n"] = 0
        r = client.get(f"/api/v1/products?vendor_id={v['id']}")
        assert r.status_code == 200
        n_prod = select_counter["n"]

        select_counter["n"] = 0
        r = client.get(f"/api/v1/universities/{u['id']}")
        assert r.status_code == 200
        n_detail = select_counter["n"]

    print(
        f"\nSELECT counts: universities(1)={n_uni} universities(10)={n_uni_many} programs={n_prog} "
        f"products={n_prod} uni_detail={n_detail}"
    )
    # COUNT + page + eight page-wide presentation aggregates; no per-row SELECT.
    assert n_uni <= 10, n_uni
    assert n_uni_many == n_uni, (n_uni, n_uni_many)
    assert n_prog <= 3, n_prog  # COUNT + joined page
    assert n_prod <= 3, n_prod  # COUNT + joined page
    assert n_detail <= 3, n_detail  # row + links


# ================================================================== RBAC


def test_rbac_matrix_all_entities(auth_client, db):
    c = auth_client
    d = ITDirection(code=f"RBAC-D-{_tag()}", name="RBAC dir")
    db.add(d)
    v = Vendor(name=f"RBAC-V-{_tag()}")
    db.add(v)
    db.commit()

    cases = [
        ("universities", {"name": f"RBAC-U-{_tag()}"}),
        ("directions", {"code": f"RBAC-D2-{_tag()}", "name": "x"}),
        ("programs", {"direction_id": str(d.id), "name": f"RBAC-P-{_tag()}"}),
        ("products", {"vendor_id": str(v.id), "name": f"RBAC-PR-{_tag()}"}),
        ("vendors", {"name": f"RBAC-V2-{_tag()}"}),
        ("responsibles", {"full_name": "RBAC R", "email": f"rbac-{_tag()}@ex.test"}),
    ]
    for entity, payload in cases:
        path = f"/api/v1/{entity}"
        assert c.get(path).status_code == 401, entity  # no token
        assert c.get(path, headers=_auth(c, ("guest",))).status_code == 403, entity
        assert c.post(path, json=payload, headers=_auth(c, ("guest",))).status_code == 403, entity
        for roles in (("user",),):
            assert c.get(path, headers=_auth(c, roles)).status_code == 200, (entity, roles)
            assert c.post(path, json=payload, headers=_auth(c, roles)).status_code == 403, (
                entity,
                roles,
            )
        for roles in (("manager",), ("admin",)):
            assert c.get(path, headers=_auth(c, roles)).status_code == 200, (entity, roles)
            # unique payloads: the second writer bumps the identifying field
            # after a 409 on the already-taken value.
            r = c.post(path, json=dict(payload), headers=_auth(c, roles))
            if entity == "universities" and roles == ("manager",):
                assert r.status_code == 403, (entity, roles, r.text)
                continue
            if r.status_code == 409:
                payload = _bump(payload)
                r = c.post(path, json=payload, headers=_auth(c, roles))
            assert r.status_code == 201, (entity, roles, r.text)


def _bump(payload: dict) -> dict:
    out = dict(payload)
    tag = _tag()
    for key in ("name", "code", "email", "full_name"):
        if key in out:
            out[key] = f"{out[key]}-{tag}"
    return out


def test_rbac_write_verbs_university(auth_client, db):
    c = auth_client
    u = University(name=f"RBAC-U-{_tag()}", city="X")
    db.add(u)
    db.commit()
    uid = u.id
    r1 = Responsible(full_name="RBAC Resp", email=f"rbac-r-{_tag()}@ex.test")
    db.add(r1)
    db.commit()

    assert c.patch(f"/api/v1/universities/{uid}", json={"city": "Y"}).status_code == 401
    assert c.delete(f"/api/v1/universities/{uid}").status_code == 401
    user = _auth(c, ("user",))
    assert (
        c.patch(f"/api/v1/universities/{uid}", json={"city": "Y"}, headers=user).status_code == 403
    )
    assert c.delete(f"/api/v1/universities/{uid}", headers=user).status_code == 403
    assert (
        c.post(
            f"/api/v1/universities/{uid}/responsibles/{r1.id}", json={}, headers=user
        ).status_code
        == 403
    )

    manager = _auth(c, ("manager",))
    assert (
        c.patch(f"/api/v1/universities/{uid}", json={"city": "Y"}, headers=manager).status_code
        == 404
    )
    assert c.post(
        f"/api/v1/universities/{uid}/responsibles/{r1.id}", json={}, headers=manager
    ).status_code == 404
    assert (
        c.delete(f"/api/v1/universities/{uid}/responsibles/{r1.id}", headers=manager).status_code
        == 404
    )
    assert c.delete(f"/api/v1/universities/{uid}", headers=manager).status_code == 404


# ================================================================ openapi


def test_openapi_catalog_routes_present(client):
    body = client.get("/openapi.json").json()
    paths = body["paths"]
    expected = [
        "/api/v1/universities",
        "/api/v1/universities/{university_id}",
        "/api/v1/universities/{university_id}/responsibles/{responsible_id}",
        "/api/v1/directions",
        "/api/v1/directions/{direction_id}",
        "/api/v1/programs",
        "/api/v1/programs/{program_id}",
        "/api/v1/products",
        "/api/v1/products/{product_id}",
        "/api/v1/vendors",
        "/api/v1/vendors/{vendor_id}",
        "/api/v1/responsibles",
        "/api/v1/responsibles/{responsible_id}",
    ]
    for p in expected:
        assert p in paths, p
    assert paths["/api/v1/universities"]["get"]["responses"]["200"]
    post = paths["/api/v1/universities"]["post"]
    assert post["responses"]["201"]
    assert "422" in {str(k) for k in post["responses"]}
    assert paths["/api/v1/universities/{university_id}"]["delete"]["responses"]["204"]
    # no duplicate operationIds
    op_ids = [
        op.get("operationId")
        for ops in paths.values()
        for op in ops.values()
        if isinstance(op, dict)
    ]
    assert len(op_ids) == len(set(op_ids))
