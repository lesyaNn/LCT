"""P2 Backend 1: workflow templates + stages (P2-01-01/02-01/02-02/01-04).

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
DB); the schema always comes from the canonical SQL migrations
(``tests/db_helpers.py``). No SQLite, no ``create_all``.

Coverage: schema tables/FK/cascade/UNIQUE/CHECK (+SQLSTATE), templates API
(workflow-role list, admin POST/detail/PATCH, 401/403/404, pagination, ordering, timestamps
not client-settable, exclude_unset PATCH), stages API (append/insert
first/middle/end, order shift, template isolation, PATCH incl. moves, 404s,
position bounds, admin-only RBAC), reorder transaction rollback, seed of the
14 ТЗ stages (source + idempotency), N+1 query-count bounds, OpenAPI
inventory (new routes, unique operationIds, P1 routes intact).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.config import settings
from app.db.seed_workflow import STAGES_14, TEMPLATE_NAME, seed_workflow_templates
from app.db.session import get_db
from app.main import app
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

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
    """Bypass-auth HTTP client bound to the PG engine (acts as admin)."""

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


_KID = "p2-wf-1"


def _b64url(num: int) -> str:
    import base64

    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def auth_client(engine, monkeypatch):
    """Real JWT validation (local RSA ~ JWKS), dev bypass OFF, real app+DB."""
    import app.core.security as sec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwt as _jwt

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


def _template(client, name=None, **kw):
    payload = {"name": name or f"Template-{_tag()}"}
    payload.update(kw)
    r = client.post("/api/v1/workflow/templates", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _stage(client, template_id, name=None, **kw):
    payload = {"name": name or f"Stage-{_tag()}"}
    payload.update(kw)
    r = client.post(f"/api/v1/workflow/templates/{template_id}/stages", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _order(db, template_id):
    return db.execute(
        select(WorkflowStage.name, WorkflowStage.order_index)
        .where(WorkflowStage.template_id == template_id)
        .order_by(WorkflowStage.order_index)
    ).all()


def test_stage_default_tasks_persist_and_patch_is_scoped(client):
    template = _template(client)
    stage = _stage(client, template["id"], default_tasks=["  Проверить документы  ", "Позвонить"])
    url = f'/api/v1/workflow/templates/{template["id"]}/stages/{stage["id"]}'
    assert stage["default_tasks"] == ["Проверить документы", "Позвонить"]
    renamed = client.patch(url, json={"name": "Новое название"})
    assert renamed.status_code == 200
    assert renamed.json()["default_tasks"] == stage["default_tasks"]
    updated = client.patch(url, json={"default_tasks": ["Новая задача"]})
    assert updated.status_code == 200
    detail = client.get(f'/api/v1/workflow/templates/{template["id"]}').json()
    assert detail["stages"][0]["default_tasks"] == ["Новая задача"]
    other = _template(client)
    assert client.patch(
        f'/api/v1/workflow/templates/{other["id"]}/stages/{stage["id"]}',
        json={"default_tasks": []},
    ).status_code == 404
    assert client.patch(url, json={"default_tasks": None}).status_code == 422
    cleared = client.patch(url, json={"default_tasks": []})
    assert cleared.status_code == 200
    assert cleared.json()["default_tasks"] == []


def test_default_tasks_are_copied_for_all_active_stages_only_on_launch(client, db):
    from app.models.catalog import University

    template = _template(client)
    first = _stage(client, template["id"], default_tasks=["Документы", "Звонок"])
    second = _stage(client, template["id"], default_tasks=["Согласование"])
    _stage(client, template["id"], is_active=False, default_tasks=["Не копировать"])
    _stage(client, template["id"])
    university = University(name=f"Default tasks {_tag()}", city="Москва")
    db.add(university)
    db.commit()

    def launch():
        response = client.post('/api/v1/workflow/instances', json={
            "university_id": str(university.id), "template_id": template["id"],
        })
        assert response.status_code == 201, response.text
        return response.json()

    def tasks(instance_id):
        response = client.get(f'/api/v1/workflow/instances/{instance_id}/tasks')
        assert response.status_code == 200, response.text
        return response.json()["items"]

    running = launch()
    assert [stage["tasks_total"] for stage in running["stages"]] == [2, 1, 0]
    original = tasks(running["id"])
    assert {(task["stage_id"], task["title"], task["status"]) for task in original} == {
        (first["id"], "Документы", "open"), (first["id"], "Звонок", "open"),
        (second["id"], "Согласование", "open"),
    }
    task = next(task for task in original if task["stage_id"] == first["id"])
    changed = client.patch(f'/api/v1/workflow/instances/{running["id"]}/tasks/{task["id"]}',
                           json={"title": "Выполнено в процессе", "status": "done"})
    assert changed.status_code == 200, changed.text
    stage_url = f'/api/v1/workflow/templates/{template["id"]}/stages/{first["id"]}'
    assert client.patch(stage_url, json={"default_tasks": ["Новая задача"]}).status_code == 200
    existing = tasks(running["id"])
    assert len(existing) == 3
    assert any(task["title"] == "Выполнено в процессе" and task["status"] == "done" for task in existing)
    new_running = launch()
    new_tasks = tasks(new_running["id"])
    assert {task["title"] for task in new_tasks} == {"Новая задача", "Согласование"}
    assert all(task["status"] == "open" for task in new_tasks)
    assert {task["id"] for task in new_tasks}.isdisjoint(task["id"] for task in original)
    assert client.patch(stage_url, json={"default_tasks": []}).status_code == 200
    assert [task["title"] for task in tasks(launch()["id"])] == ["Согласование"]


# ================================================================== schema


def test_workflow_tables_exist(engine):
    from sqlalchemy import inspect

    tables = set(inspect(engine).get_table_names())
    assert {"workflow_templates", "workflow_stages"} <= tables


def test_stage_fk_violation_sqlstate_23503(db):
    db.add(WorkflowStage(template_id=uuid.uuid4(), name="Ghost", order_index=1))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23503"
    db.rollback()


def test_stage_unique_position_sqlstate_23505(db):
    t = WorkflowTemplate(name=f"T-{_tag()}")
    db.add(t)
    db.flush()
    db.add(WorkflowStage(template_id=t.id, name="A", order_index=1))
    db.commit()
    db.add(WorkflowStage(template_id=t.id, name="B", order_index=1))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23505"
    db.rollback()


def test_stage_order_check_sqlstate_23514(db):
    t = WorkflowTemplate(name=f"T-{_tag()}")
    db.add(t)
    db.flush()
    db.add(WorkflowStage(template_id=t.id, name="Zero", order_index=0))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23514"
    db.rollback()


def test_template_delete_cascades_stages(db):
    t = WorkflowTemplate(name=f"T-{_tag()}")
    db.add(t)
    db.flush()
    db.add(WorkflowStage(template_id=t.id, name="A", order_index=1))
    db.add(WorkflowStage(template_id=t.id, name="B", order_index=2))
    db.commit()
    tid = t.id
    db.delete(t)
    db.commit()
    left = db.execute(
        select(func.count()).select_from(WorkflowStage).where(WorkflowStage.template_id == tid)
    ).scalar()
    assert left == 0


def test_unique_positions_scoped_per_template(db):
    a = WorkflowTemplate(name=f"TA-{_tag()}")
    b = WorkflowTemplate(name=f"TB-{_tag()}")
    db.add_all([a, b])
    db.flush()
    db.add(WorkflowStage(template_id=a.id, name="A1", order_index=1))
    db.add(WorkflowStage(template_id=b.id, name="B1", order_index=1))  # same pos, other template
    db.commit()  # must NOT collide


def test_template_name_unique(db):
    db.add(WorkflowTemplate(name="Same"))
    db.commit()
    db.add(WorkflowTemplate(name="Same"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ============================================================ templates API


def test_template_crud_happy_path(client):
    created = _template(client, description="d1")
    assert uuid.UUID(created["id"])
    assert created["description"] == "d1"
    assert created["is_active"] is True
    assert created["stages"] == []
    assert created["created_at"] and created["updated_at"]
    tid = created["id"]

    got = client.get(f"/api/v1/workflow/templates/{tid}")
    assert got.status_code == 200, got.text
    assert got.json()["name"] == created["name"]

    patched = client.patch(f"/api/v1/workflow/templates/{tid}", json={"name": "Renamed"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["description"] == "d1"  # partial update preserves the rest


def test_template_delete_returns_json_and_removes_unused_template(client):
    created = _template(client)
    response = client.delete(f"/api/v1/workflow/templates/{created['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "deleted"}
    assert client.get(f"/api/v1/workflow/templates/{created['id']}").status_code == 404


def test_template_patch_exclude_unset_and_explicit_null(client):
    created = _template(client, description="keep me")
    tid = created["id"]

    cleared = client.patch(f"/api/v1/workflow/templates/{tid}", json={"description": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["description"] is None  # explicit null clears a nullable field

    untouched = client.patch(f"/api/v1/workflow/templates/{tid}", json={})
    assert untouched.status_code == 200
    assert untouched.json()["description"] is None
    assert untouched.json()["name"] == created["name"]  # absent field leaves value alone


def test_template_create_returns_201_and_ignores_system_fields(client):
    r = client.post(
        "/api/v1/workflow/templates",
        json={
            "name": f"T-{_tag()}",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2020-01-01T00:00:00Z",
            "id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert not body["created_at"].startswith("2020-01-01")


def test_template_duplicate_name_409(client):
    _template(client, name="Dup-T")
    r = client.post("/api/v1/workflow/templates", json={"name": "Dup-T"})
    assert r.status_code == 409, r.text


def test_template_404s_and_validation(client):
    assert client.get(f"/api/v1/workflow/templates/{uuid.uuid4()}").status_code == 404
    assert (
        client.patch(f"/api/v1/workflow/templates/{uuid.uuid4()}", json={"name": "x"}).status_code
        == 404
    )
    assert client.post("/api/v1/workflow/templates", json={}).status_code == 422
    assert client.post("/api/v1/workflow/templates", json={"name": ""}).status_code == 422
    assert client.get("/api/v1/workflow/templates/not-a-uuid").status_code == 422
    assert client.get("/api/v1/workflow/templates?page=0").status_code == 422


def test_template_list_pagination_stable_ordering(client):
    ids = [_template(client, name=f"LT-{i:02d}")["id"] for i in range(5)]
    p1 = client.get("/api/v1/workflow/templates?page=1&page_size=2").json()
    p2 = client.get("/api/v1/workflow/templates?page=2&page_size=2").json()
    p3 = client.get("/api/v1/workflow/templates?page=3&page_size=2").json()
    assert set(p1) == {"items", "page", "page_size", "total"}
    assert (p1["total"], p2["total"], p3["total"]) == (5, 5, 5)
    assert [len(p["items"]) for p in (p1, p2, p3)] == [2, 2, 1]
    got = [it["id"] for it in p1["items"] + p2["items"] + p3["items"]]
    assert sorted(got) == sorted(ids) and len(set(got)) == 5
    again = client.get("/api/v1/workflow/templates?page=1&page_size=2").json()
    assert [it["id"] for it in again["items"]] == [it["id"] for it in p1["items"]]
    empty = client.get("/api/v1/workflow/templates?page=99&page_size=2").json()
    assert empty["items"] == [] and empty["total"] == 5


def test_template_detail_returns_stages_in_order(client):
    t = _template(client)
    _stage(client, t["id"], name="third")
    _stage(client, t["id"], name="first", order_index=1)
    _stage(client, t["id"], name="second", order_index=2)
    detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    assert [s["name"] for s in detail["stages"]] == ["first", "second", "third"]
    assert [s["order_index"] for s in detail["stages"]] == [1, 2, 3]


# ================================================================= stages API


def test_stage_append_without_position(client, db):
    t = _template(client)
    a = _stage(client, t["id"], name="A")
    b = _stage(client, t["id"], name="B")
    assert (a["order_index"], b["order_index"]) == (1, 2)
    assert [n for n, _ in _order(db, uuid.UUID(t["id"]))] == ["A", "B"]


def test_stage_insert_first_shifts(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A")
    _stage(client, t["id"], name="B")
    _stage(client, t["id"], name="C")
    first = _stage(client, t["id"], name="NEW", order_index=1)
    assert first["order_index"] == 1
    assert _order(db, uuid.UUID(t["id"])) == [("NEW", 1), ("A", 2), ("B", 3), ("C", 4)]


def test_stage_insert_middle_shifts(client, db):
    t = _template(client)
    for name in ("A", "B", "C"):
        _stage(client, t["id"], name=name)
    mid = _stage(client, t["id"], name="NEW", order_index=2)
    assert mid["order_index"] == 2
    # 1,2(new),3(old2),4(old3): deterministic, no duplicates
    assert _order(db, uuid.UUID(t["id"])) == [("A", 1), ("NEW", 2), ("B", 3), ("C", 4)]


def test_stage_insert_past_end_appends(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A")
    end = _stage(client, t["id"], name="END", order_index=999)
    assert end["order_index"] == 2  # clamped to append, pinned behavior
    assert _order(db, uuid.UUID(t["id"])) == [("A", 1), ("END", 2)]


def test_stage_insert_invalid_position_422(client):
    t = _template(client)
    assert (
        client.post(
            f"/api/v1/workflow/templates/{t['id']}/stages",
            json={"name": "Bad", "order_index": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/workflow/templates/{t['id']}/stages",
            json={"name": "Bad", "order_index": -3},
        ).status_code
        == 422
    )


def test_stage_templates_isolation(client, db):
    a = _template(client)
    b = _template(client)
    _stage(client, a["id"], name="A1")
    _stage(client, a["id"], name="A2")
    _stage(client, b["id"], name="B1", order_index=1)
    assert _order(db, uuid.UUID(a["id"])) == [("A1", 1), ("A2", 2)]
    assert _order(db, uuid.UUID(b["id"])) == [("B1", 1)]


def test_stage_patch_fields_and_move(client, db):
    t = _template(client)
    s1 = _stage(client, t["id"], name="One")
    s2 = _stage(client, t["id"], name="Two")
    s3 = _stage(client, t["id"], name="Three")

    patched = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s2['id']}",
        json={"name": "Two-renamed", "is_required": False, "sla_days": 10},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Two-renamed"
    assert patched.json()["is_required"] is False
    assert patched.json()["sla_days"] == 10
    assert patched.json()["order_index"] == 2  # ordinary PATCH keeps position

    moved = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s3['id']}",
        json={"order_index": 1},
    )
    assert moved.status_code == 200, moved.text
    assert _order(db, uuid.UUID(t["id"])) == [
        ("Three", 1),
        ("One", 2),
        ("Two-renamed", 3),
    ]
    assert s1["id"] != s2["id"]  # ids stable across the move


def test_stage_404s(client):
    t = _template(client)
    s = _stage(client, t["id"])
    other = _template(client)
    missing = str(uuid.uuid4())
    assert (
        client.post(f"/api/v1/workflow/templates/{missing}/stages", json={"name": "x"}).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{missing}", json={"name": "x"}
        ).status_code
        == 404
    )
    # stage of another template addressed under this one -> 404 (no leak)
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{other['id']}/stages/{s['id']}", json={"name": "x"}
        ).status_code
        == 404
    )


# ============================================================ transaction safety


def test_failed_reorder_transaction_rolls_back(db):
    t = WorkflowTemplate(name=f"RB-{_tag()}")
    db.add(t)
    db.flush()
    for i, name in enumerate(("S1", "S2", "S3"), start=1):
        db.add(WorkflowStage(template_id=t.id, name=name, order_index=i))
    db.commit()

    # Shift like create_stage does, then fail the commit with an unrelated
    # UNIQUE violation: the whole transaction (shift included) must roll back.
    db.execute(
        update(WorkflowStage)
        .where(WorkflowStage.template_id == t.id, WorkflowStage.order_index >= 2)
        .values(order_index=WorkflowStage.order_index + 1)
    )
    db.add(WorkflowTemplate(name=t.name))  # duplicate name -> 23505 at COMMIT
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert [(n, o) for n, o in _order(db, t.id)] == [("S1", 1), ("S2", 2), ("S3", 3)]


# ======================================================================= RBAC


def test_templates_rbac_read_for_workflow_roles_admin_writes(auth_client):
    c = auth_client
    assert c.get("/api/v1/workflow/templates").status_code == 401
    assert c.post("/api/v1/workflow/templates", json={"name": "x"}).status_code == 401
    assert c.get("/api/v1/workflow/templates").status_code == 401

    assert c.get("/api/v1/workflow/templates", headers=_auth(c, ("guest",))).status_code == 403
    for roles in (("user",), ("manager",)):
        assert c.get("/api/v1/workflow/templates", headers=_auth(c, roles)).status_code == 200, (
            roles
        )
        r = c.post(
            "/api/v1/workflow/templates", json={"name": f"RBAC-{_tag()}"}, headers=_auth(c, roles)
        )
        assert r.status_code == 403, (roles, r.text)

    admin = _auth(c, ("admin",))
    assert c.get("/api/v1/workflow/templates", headers=admin).status_code == 200
    r = c.post("/api/v1/workflow/templates", json={"name": f"RBAC-{_tag()}"}, headers=admin)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    assert c.get(f"/api/v1/workflow/templates/{tid}").status_code == 401
    assert (
        c.get(f"/api/v1/workflow/templates/{tid}", headers=_auth(c, ("user",))).status_code == 403
    )
    assert c.get(f"/api/v1/workflow/templates/{tid}", headers=admin).status_code == 200
    assert c.patch(f"/api/v1/workflow/templates/{tid}", json={"name": "z"}).status_code == 401
    assert (
        c.patch(
            f"/api/v1/workflow/templates/{tid}", json={"name": "z"}, headers=_auth(c, ("manager",))
        ).status_code
        == 403
    )
    assert (
        c.patch(f"/api/v1/workflow/templates/{tid}", json={"name": "z"}, headers=admin).status_code
        == 200
    )

    assert c.post(f"/api/v1/workflow/templates/{tid}/stages", json={"name": "s"}).status_code == 401
    assert (
        c.post(
            f"/api/v1/workflow/templates/{tid}/stages",
            json={"name": "s"},
            headers=_auth(c, ("user",)),
        ).status_code
        == 403
    )
    r = c.post(f"/api/v1/workflow/templates/{tid}/stages", json={"name": "s"}, headers=admin)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (
        c.patch(f"/api/v1/workflow/templates/{tid}/stages/{sid}", json={"name": "s2"}).status_code
        == 401
    )
    assert (
        c.patch(
            f"/api/v1/workflow/templates/{tid}/stages/{sid}",
            json={"name": "s2"},
            headers=_auth(c, ("user",)),
        ).status_code
        == 403
    )
    assert (
        c.patch(
            f"/api/v1/workflow/templates/{tid}/stages/{sid}", json={"name": "s2"}, headers=admin
        ).status_code
        == 200
    )


# ================================================================= seed (P2-01-04)


def test_seed_14_stages_source_and_idempotency(db):
    assert len(STAGES_14) == 14
    first = seed_workflow_templates(db)
    assert first == {"workflow_templates": 1, "workflow_stages": 14}
    second = seed_workflow_templates(db)
    assert second == {"workflow_templates": 1, "workflow_stages": 14}  # no duplicates

    rows = db.execute(
        select(WorkflowStage.name, WorkflowStage.order_index, WorkflowStage.is_required)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowStage.template_id)
        .where(WorkflowTemplate.name == TEMPLATE_NAME)
        .order_by(WorkflowStage.order_index)
    ).all()
    assert [o for _, o, _ in rows] == list(range(1, 15))
    assert rows[0][0] == "Поиск контактов ответственного в вузе"
    assert rows[4][0].startswith("Опционально:")
    assert rows[4][2] is False  # the ТЗ-optional stage
    assert all(r[2] is True for i, r in enumerate(rows) if i != 4)
    assert rows[-1][0] == "Контроль за исполнением каждого этапа"


# ========================================================================= N+1


def test_detail_query_count_bounded(client, engine, select_counter):
    t = _template(client)
    _stage(client, t["id"], name="A")
    _stage(client, t["id"], name="B")

    with Session(engine) as s:
        s.expire_all()
        select_counter["n"] = 0
        r = client.get(f"/api/v1/workflow/templates/{t['id']}")
        assert r.status_code == 200
        n_two = select_counter["n"]

    with Session(engine) as s:
        seed_workflow_templates(s)
        tid = s.execute(
            select(WorkflowTemplate.id).where(WorkflowTemplate.name == TEMPLATE_NAME)
        ).scalar_one()
        s.expire_all()
        select_counter["n"] = 0
        r = client.get(f"/api/v1/workflow/templates/{tid}")
        assert r.status_code == 200
        assert len(r.json()["stages"]) == 14
        n_fourteen = select_counter["n"]

    print(f"\nSELECT counts: detail(2 stages)={n_two} detail(14 stages)={n_fourteen}")
    assert n_two <= 4, n_two
    assert n_fourteen <= 4, n_fourteen  # constant/bounded, no query per stage
    assert n_fourteen == n_two  # identical shape regardless of stage count


def test_list_query_count_bounded(client, select_counter):
    for i in range(3):
        _template(client, name=f"QC-{i}-{_tag()}")
    select_counter["n"] = 0
    r = client.get("/api/v1/workflow/templates?page=1&page_size=10")
    assert r.status_code == 200
    assert select_counter["n"] <= 3, select_counter["n"]  # COUNT + page, no per-row query


# ===================================================================== openapi


def test_openapi_workflow_routes_present_and_p1_intact(client):
    body = client.get("/openapi.json").json()
    paths = body["paths"]
    for p in (
        "/api/v1/workflow/templates",
        "/api/v1/workflow/templates/{template_id}",
        "/api/v1/workflow/templates/{template_id}/stages",
        "/api/v1/workflow/templates/{template_id}/stages/{stage_id}",
    ):
        assert p in paths, p
    post = paths["/api/v1/workflow/templates"]["post"]
    assert post["responses"]["201"]
    assert paths["/api/v1/workflow/templates"]["get"]["responses"]["200"]
    # P1 contract intact
    for p in (
        "/api/v1/universities",
        "/api/v1/directions",
        "/api/v1/catalog/overview",
        "/health",
        "/ready",
    ):
        assert p in paths, p
    op_ids = [
        op.get("operationId")
        for ops in paths.values()
        for op in ops.values()
        if isinstance(op, dict)
    ]
    assert len(op_ids) == len(set(op_ids))
