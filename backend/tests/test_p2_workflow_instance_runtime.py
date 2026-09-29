"""P2-02-03/06-01: workflow instance runtime (creation + snapshot + overdue).

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
DB); the schema always comes from the canonical SQL migrations
(``tests/db_helpers.py``). No SQLite, no ``create_all``.

Pure-unit checks (migration pair shape, SQL conventions, overdue boundary
math, due-cascade math) run everywhere without a database.

Coverage: 000013/000014 up/down pairs + chain order, SQL conventions,
POST instance (happy path, 404 university/template/responsible, atomic
snapshot of ACTIVE stages only, current pointers, creation transition),
GET instance (stable stage order, no N+1, 404), snapshot immunity (template
edited after creation -> old instance unchanged), due-date cascade
(cumulative sla_days, NULL sla -> NULL due, instance due = last dated
stage), overdue boundaries (yesterday/today/tomorrow, completed
before/on/after, shared helper only), RBAC (401/403/allowed/admin on frozen
permissions), university isolation (scoped curator, admin bypass), Files
interoperability (upload to a runtime-created instance), OpenAPI (new routes
present, operationIds unique, P1 routes intact).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import Responsible, University
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowStageTransition,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.workflow_instances.overdue import compute_overdue, today_utc
from app.modules.workflow_instances.service import stage_due_dates

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "migrations")


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


_KID = "p2-wf-inst"


def _b64url(num: int) -> str:
    import base64

    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def auth_client(engine, monkeypatch, tmp_path):
    """Real JWT validation (local RSA ~ JWKS), dev bypass OFF, real app+DB."""
    import app.core.security as sec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwt as _jwt

    from app.modules.workflow_attachments.router import get_storage
    from app.modules.workflow_attachments.storage import LocalStorageBackend

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

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_storage] = lambda: LocalStorageBackend(storage_root)

    def mint(roles, university_ids=None):
        now = datetime.now(timezone.utc)
        claims = {
            "sub": f"user-{_tag()}",
            "preferred_username": roles[0],
            "realm_access": {"roles": list(roles)},
            "iss": settings.keycloak_issuer,
            "aud": settings.keycloak_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        if university_ids is not None:
            claims["university_ids"] = list(university_ids)
        return _jwt.encode(claims, priv, algorithm="RS256", headers={"kid": _KID})

    with TestClient(app) as c:
        c._mint = mint  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)
    settings.auth_dev_bypass = old_bypass
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})


def _auth(c, roles, university_ids=None):
    return {"Authorization": f"Bearer {c._mint(roles, university_ids)}"}


# ---------------------------------------------------------------- helpers


def _universe(db: Session, n_stages: int = 3, sla: list[int | None] | None = None):
    """University + template with ordered stages (ORM-level setup)."""
    tag = _tag()
    u = University(name=f"Inst Uni {tag}", city="Москва")
    t = WorkflowTemplate(name=f"Inst Template {tag}")
    db.add_all([u, t])
    db.flush()
    for i in range(1, n_stages + 1):
        db.add(
            WorkflowStage(
                template_id=t.id,
                name=f"Stage {i}",
                order_index=i,
                sla_days=(sla[i - 1] if sla is not None else None),
            )
        )
    db.commit()
    return {"university": u, "template": t}


def _post_instance(client, university_id, template_id, **kw):
    payload = {"university_id": str(university_id), "template_id": str(template_id)}
    payload.update(kw)
    return client.post("/api/v1/workflow/instances", json=payload)


# ==================================================== pure-unit: migrations


def test_migration_000013_pair_and_conventions():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sql_migrate",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "migrate.py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module._discover()
    versions = [v for v, _, _ in plan]
    assert "000013_instance_stages" in versions
    assert "000014_transition_history_restrict" in versions
    assert "instance_stages" in module.EXPECTED_TABLES

    raw = open(os.path.join(MIGRATIONS_DIR, "000013_instance_stages.up.sql"), encoding="utf-8").read()
    sql = "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("--"))
    assert "CREATE TABLE instance_stages (" in sql
    assert "IF NOT EXISTS" not in sql
    assert "gen_random_uuid()" not in sql
    down = open(
        os.path.join(MIGRATIONS_DIR, "000013_instance_stages.down.sql"), encoding="utf-8"
    ).read()
    assert "DROP TABLE instance_stages;" in down

    raw14 = open(
        os.path.join(MIGRATIONS_DIR, "000014_transition_history_restrict.up.sql"),
        encoding="utf-8",
    ).read()
    assert "ON DELETE RESTRICT" in raw14
    assert "CREATE TABLE" not in "\n".join(
        ln for ln in raw14.splitlines() if not ln.strip().startswith("--")
    )
    assert "fk_workflow_stage_transitions_from_stage_id_workflow_stages" in raw14
    assert "fk_workflow_stage_transitions_to_stage_id_workflow_stages" in raw14
    down14 = open(
        os.path.join(MIGRATIONS_DIR, "000014_transition_history_restrict.down.sql"),
        encoding="utf-8",
    ).read()
    assert "ON DELETE SET NULL" in down14


def test_000011_000012_untouched_by_this_change():
    """000011/000012 were fixed before this change: no snapshot/RESTRICT text in them."""
    expectations = {
        "000011_workflow_templates.up.sql": ["CREATE TABLE workflow_templates (", "CREATE TABLE workflow_stages ("],
        "000011_workflow_templates.down.sql": ["DROP TABLE workflow_stages;", "DROP TABLE workflow_templates;"],
        "000012_workflow_instances.up.sql": ["CREATE TABLE workflow_instances (", "ON DELETE SET NULL"],
        "000012_workflow_instances.down.sql": ["DROP TABLE workflow_instances;"],
    }
    for name, markers in expectations.items():
        text = open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8").read()
        assert "instance_stages" not in text, name
        assert "current_instance_stage_id" not in text, name
        for marker in markers:
            assert marker in text, (name, marker)


# ==================================================== pure-unit: overdue math


def test_today_utc_is_utc_calendar_day():
    assert today_utc() == datetime.now(timezone.utc).date()


@pytest.mark.parametrize(
    ("due", "completed", "today", "expected"),
    [
        # No deadline -> never overdue.
        (None, None, date(2026, 9, 20), (False, 0)),
        (None, datetime(2026, 9, 25, tzinfo=timezone.utc), date(2026, 9, 20), (False, 0)),
        # Open boundaries.
        (date(2026, 9, 19), None, date(2026, 9, 20), (True, 1)),  # due yesterday
        (date(2026, 9, 20), None, date(2026, 9, 20), (False, 0)),  # due today
        (date(2026, 9, 21), None, date(2026, 9, 20), (False, 0)),  # due tomorrow
        (date(2026, 9, 10), None, date(2026, 9, 20), (True, 10)),
        # Completed boundaries (completed_at as datetime and as date).
        (date(2026, 9, 20), datetime(2026, 9, 19, 12, tzinfo=timezone.utc), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc), date(2026, 9, 30), (True, 1)),
        (date(2026, 9, 20), date(2026, 9, 18), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), date(2026, 9, 20), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), date(2026, 9, 23), date(2026, 9, 30), (True, 3)),
        # Completion freezes the score: far-past due but done on time.
        (date(2026, 9, 1), datetime(2026, 9, 1, 8, tzinfo=timezone.utc), date(2026, 12, 31), (False, 0)),
    ],
)
def test_compute_overdue_boundaries(due, completed, today, expected):
    assert compute_overdue(due, completed, today) == expected


def test_stage_due_dates_cascade_and_nulls():
    day = date(2026, 9, 20)
    rows = [
        WorkflowStage(template_id=uuid.uuid4(), name="A", order_index=1, sla_days=2),
        WorkflowStage(template_id=uuid.uuid4(), name="B", order_index=2, sla_days=3),
        WorkflowStage(template_id=uuid.uuid4(), name="C", order_index=3, sla_days=None),
        WorkflowStage(template_id=uuid.uuid4(), name="D", order_index=4, sla_days=5),
    ]
    assert stage_due_dates(rows, day) == [
        day + timedelta(days=2),
        day + timedelta(days=5),
        None,
        day + timedelta(days=10),
    ]
    assert stage_due_dates(
        [WorkflowStage(template_id=uuid.uuid4(), name="X", order_index=1, sla_days=None)], day
    ) == [None]


# ==================================================== PG: POST + GET


def test_post_creates_snapshot_pointers_and_transition(client, db):
    g = _universe(db, n_stages=3, sla=[2, 3, None])
    r = _post_instance(client, g["university"].id, g["template"].id)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["university_id"] == str(g["university"].id)
    assert body["template_id"] == str(g["template"].id)
    assert body["status"] == "active"
    assert body["completed_at"] is None
    assert body["is_overdue"] is False and body["days_overdue"] == 0

    stages = body["stages"]
    assert [s["order_index"] for s in stages] == [1, 2, 3]
    assert [s["name"] for s in stages] == ["Stage 1", "Stage 2", "Stage 3"]
    assert [s["status"] for s in stages] == ["pending"] * 3
    assert stages[0]["started_at"] is not None
    assert all(s["started_at"] is None for s in stages[1:])
    assert all(s["completed_at"] is None for s in stages)

    today = today_utc()
    assert stages[0]["due_date"] == (today + timedelta(days=2)).isoformat()
    assert stages[1]["due_date"] == (today + timedelta(days=5)).isoformat()
    assert stages[2]["due_date"] is None
    assert body["due_date"] == (today + timedelta(days=5)).isoformat()

    # Current pointers: runtime snapshot + compat template pointer.
    assert body["current_instance_stage_id"] == stages[0]["id"]
    first_template_stage = db.execute(
        select(WorkflowStage.id)
        .where(WorkflowStage.template_id == g["template"].id)
        .order_by(WorkflowStage.order_index)
    ).scalars().first()
    assert body["current_stage_id"] == str(first_template_stage)

    # Creation transition recorded (NULL from, first stage to, actor set).
    moves = db.execute(
        select(WorkflowStageTransition).where(
            WorkflowStageTransition.instance_id == uuid.UUID(body["id"])
        )
    ).scalars().all()
    assert len(moves) == 1
    assert moves[0].from_stage_id is None
    assert moves[0].to_stage_id == first_template_stage
    assert moves[0].actor_keycloak_sub


def test_post_snapshots_only_active_stages(db, client):
    g = _universe(db, n_stages=2)
    db.add(WorkflowStage(template_id=g["template"].id, name="Retired", order_index=3, is_active=False))
    db.commit()
    r = _post_instance(client, g["university"].id, g["template"].id)
    assert r.status_code == 201, r.text
    assert [s["name"] for s in r.json()["stages"]] == ["Stage 1", "Stage 2"]


def test_post_404s_and_atomicity(client, db):
    g = _universe(db, n_stages=1)
    ghost = uuid.uuid4()
    before = db.execute(select(func.count()).select_from(WorkflowInstance)).scalar()

    assert _post_instance(client, ghost, g["template"].id).status_code == 404
    assert _post_instance(client, g["university"].id, ghost).status_code == 404
    assert _post_instance(client, g["university"].id, g["template"].id, responsible_id=str(ghost)).status_code == 404
    assert _post_instance(client, "not-a-uuid", g["template"].id).status_code == 422

    after = db.execute(select(func.count()).select_from(WorkflowInstance)).scalar()
    assert after == before  # failed validations create nothing
    assert db.execute(select(func.count()).select_from(InstanceStage)).scalar() == 0


def test_post_copies_responsible_and_actor(client, db):
    tag = _tag()
    g = _universe(db, n_stages=1)
    resp = Responsible(full_name="Отв О.О.", email=f"resp-{tag}@example.local", role="manager")
    db.add(resp)
    db.commit()
    r = _post_instance(client, g["university"].id, g["template"].id, responsible_id=str(resp.id))
    assert r.status_code == 201, r.text
    assert r.json()["responsible_id"] == str(resp.id)


def test_get_returns_stages_in_stable_order(client, db):
    g = _universe(db, n_stages=4)
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    got = client.get(f"/api/v1/workflow/instances/{created['id']}")
    assert got.status_code == 200, got.text
    assert got.json() == created
    assert [s["order_index"] for s in got.json()["stages"]] == [1, 2, 3, 4]
    assert got.json()["current_instance_stage_id"] == got.json()["stages"][0]["id"]


def test_get_404s(client):
    ghost = uuid.uuid4()
    assert client.get(f"/api/v1/workflow/instances/{ghost}").status_code == 404
    assert client.get("/api/v1/workflow/instances/not-a-uuid").status_code == 422


def test_snapshot_immune_to_later_template_edits(client, db):
    """create template -> create instance -> edit template -> old instance intact."""
    g = _universe(db, n_stages=2, sla=[1, 1])
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    before = [(s["order_index"], s["name"], s["due_date"]) for s in created["stages"]]

    # Mutate the template: rename stage 1, deactivate stage 2, append stage 3.
    s1, s2 = (
        db.execute(
            select(WorkflowStage)
            .where(WorkflowStage.template_id == g["template"].id)
            .order_by(WorkflowStage.order_index)
        )
        .scalars()
        .all()
    )
    s1.name = "Renamed after creation"
    s1.sla_days = 99
    s2.is_active = False
    db.add(WorkflowStage(template_id=g["template"].id, name="Brand new", order_index=3))
    db.commit()

    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    assert [(s["order_index"], s["name"], s["due_date"]) for s in got["stages"]] == before
    assert [s["template_stage_id"] for s in got["stages"]] == [str(s1.id), str(s2.id)]
    # New instances DO see the edited template (snapshot is per-instance).
    again = _post_instance(client, g["university"].id, g["template"].id).json()
    assert [s["name"] for s in again["stages"]] == ["Renamed after creation", "Brand new"]


def test_template_stage_delete_nulls_snapshot_anchor_keeps_row(db, client):
    """Deleting a template stage NULLs instance_stages.template_stage_id (SET NULL)
    while the snapshot row (name/order/due) survives for history."""
    g = _universe(db, n_stages=1)
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    snap_id = created["stages"][0]["id"]
    stage_id = created["stages"][0]["template_stage_id"]
    # No transition history references this path beyond creation... creation
    # transition DOES reference it (RESTRICT). Remove it first to isolate the
    # snapshot-anchor policy under test.
    db.execute(
        WorkflowStageTransition.__table__.delete().where(
            WorkflowStageTransition.instance_id == uuid.UUID(created["id"])
        )
    )
    db.commit()
    db.delete(db.get(WorkflowStage, uuid.UUID(stage_id)))
    db.commit()
    row = db.get(InstanceStage, uuid.UUID(snap_id))
    assert row is not None and row.template_stage_id is None
    assert row.name == "Stage 1" and row.order_index == 1
    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    assert got["stages"][0]["template_stage_id"] is None
    assert got["stages"][0]["name"] == "Stage 1"


def test_get_query_count_bounded(client, engine, select_counter):
    g_ids = []
    with Session(engine) as s:
        tag = _tag()
        u = University(name=f"QC Uni {tag}", city="Москва")
        t = WorkflowTemplate(name=f"QC Template {tag}")
        s.add_all([u, t])
        s.flush()
        for i in range(1, 15):
            s.add(WorkflowStage(template_id=t.id, name=f"S{i}", order_index=i))
        s.commit()
        g_ids = (str(u.id), str(t.id))
    small = _post_instance(client, g_ids[0], g_ids[1]).json()
    assert len(small["stages"]) == 14

    with Session(engine) as s:
        tag = _tag()
        u = University(name=f"QC2 Uni {tag}", city="Москва")
        t = WorkflowTemplate(name=f"QC2 Template {tag}")
        s.add_all([u, t])
        s.flush()
        s.add(WorkflowStage(template_id=t.id, name="Only", order_index=1))
        s.commit()
        tiny_ids = (str(u.id), str(t.id))
    tiny = _post_instance(client, *tiny_ids).json()
    assert len(tiny["stages"]) == 1

    select_counter["n"] = 0
    r = client.get(f"/api/v1/workflow/instances/{tiny['id']}")
    assert r.status_code == 200
    n_one = select_counter["n"]

    select_counter["n"] = 0
    r = client.get(f"/api/v1/workflow/instances/{small['id']}")
    assert r.status_code == 200
    n_fourteen = select_counter["n"]

    print(f"\nSELECT counts: instance(1 stage)={n_one} instance(14 stages)={n_fourteen}")
    # 1 instance SELECT + 5 selectin collection loads (transitions/comments/
    # attachments/tasks/instance_stages): constant shape, no query per stage.
    assert n_one <= 6, n_one
    assert n_fourteen <= 6, n_fourteen
    assert n_fourteen == n_one


# ==================================================== PG: overdue via API


def test_overdue_derived_on_get_for_stage_and_instance(client, db):
    g = _universe(db, n_stages=2, sla=[5, 5])
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    iid = uuid.UUID(created["id"])
    snap_ids = [uuid.UUID(s["id"]) for s in created["stages"]]

    yesterday = today_utc() - timedelta(days=1)
    db.get(InstanceStage, snap_ids[0]).due_date = yesterday
    db.get(WorkflowInstance, iid).due_date = yesterday
    db.commit()

    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    assert got["is_overdue"] is True and got["days_overdue"] == 1
    first = [s for s in got["stages"] if s["id"] == str(snap_ids[0])][0]
    assert first["is_overdue"] is True and first["days_overdue"] == 1

    # Completing the overdue stage on its due date clears the flag (helper).
    db.get(InstanceStage, snap_ids[0]).completed_at = datetime.combine(
        yesterday, datetime.min.time(), tzinfo=timezone.utc
    )
    db.commit()
    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    first = [s for s in got["stages"] if s["id"] == str(snap_ids[0])][0]
    assert first["is_overdue"] is False and first["days_overdue"] == 0


def test_no_deadline_never_overdue(client, db):
    g = _universe(db, n_stages=1)  # sla NULL everywhere
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    assert created["due_date"] is None
    assert created["is_overdue"] is False and created["days_overdue"] == 0
    assert created["stages"][0]["due_date"] is None
    assert created["stages"][0]["is_overdue"] is False


# ==================================================== PG: RBAC (frozen names)


def test_instances_rbac_matrix(auth_client, db):
    g = _universe(db, n_stages=1)
    # Seed one instance with a full-access admin token.
    admin = _auth(auth_client, ["admin"])
    r = auth_client.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(g["university"].id), "template_id": str(g["template"].id)},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    url = f"/api/v1/workflow/instances/{iid}"

    assert auth_client.get(url).status_code == 401
    assert (
        auth_client.post(
            "/api/v1/workflow/instances",
            json={"university_id": str(g["university"].id), "template_id": str(g["template"].id)},
        ).status_code
        == 401
    )

    user_h = _auth(auth_client, ["user"])
    assert auth_client.get(url, headers=user_h).status_code == 403
    assert (
        auth_client.post(
            "/api/v1/workflow/instances",
            json={"university_id": str(g["university"].id), "template_id": str(g["template"].id)},
            headers=user_h,
        ).status_code
        == 403
    )

    mgr_h = _auth(auth_client, ["manager"], [str(g["university"].id)])
    assert auth_client.get(url, headers=mgr_h).status_code == 200
    assert (
        auth_client.post(
            "/api/v1/workflow/instances",
            json={"university_id": str(g["university"].id), "template_id": str(g["template"].id)},
            headers=mgr_h,
        ).status_code
        == 201
    )

    cur_h = _auth(auth_client, ["curator"])
    assert auth_client.get(url, headers=cur_h).status_code == 403
    rc = auth_client.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(g["university"].id), "template_id": str(g["template"].id)},
        headers=cur_h,
    )
    assert rc.status_code == 403, rc.text
    assert auth_client.get(url, headers=admin).status_code == 200


# ==================================================== PG: isolation


def test_cross_university_isolation(auth_client, db):
    tag = _tag()
    ua = University(name=f"Iso Uni A {tag}", city="Москва")
    ub = University(name=f"Iso Uni B {tag}", city="Казань")
    t = WorkflowTemplate(name=f"Iso Template {tag}")
    db.add_all([ua, ub, t])
    db.flush()
    db.add(WorkflowStage(template_id=t.id, name="S1", order_index=1))
    db.commit()

    a_h = _auth(auth_client, ["manager"], [str(ua.id)])
    b_h = _auth(auth_client, ["manager"], [str(ub.id)])
    admin_h = _auth(auth_client, ["admin"])

    ra = auth_client.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(ua.id), "template_id": str(t.id)},
        headers=a_h,
    )
    assert ra.status_code == 201, ra.text
    rb = auth_client.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(ub.id), "template_id": str(t.id)},
        headers=b_h,
    )
    assert rb.status_code == 201, rb.text

    # Scoped user A cannot create for B nor read B's instance (and vice versa).
    assert (
        auth_client.post(
            "/api/v1/workflow/instances",
            json={"university_id": str(ub.id), "template_id": str(t.id)},
            headers=a_h,
        ).status_code
        == 403
    )
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{rb.json()['id']}", headers=a_h).status_code
        == 403
    )
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{ra.json()['id']}", headers=b_h).status_code
        == 403
    )
    # Same-university access works; admin (no scope) reaches both.
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{ra.json()['id']}", headers=a_h).status_code
        == 200
    )
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{ra.json()['id']}", headers=admin_h).status_code
        == 200
    )
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{rb.json()['id']}", headers=admin_h).status_code
        == 200
    )


# ==================================================== PG: Files interop


def test_runtime_instance_accepts_attachments(client, db, tmp_path):
    """B1 Files flow keys off workflow_instances.id: runtime-created instances work."""
    from app.modules.workflow_attachments.router import get_storage
    from app.modules.workflow_attachments.storage import LocalStorageBackend

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    app.dependency_overrides[get_storage] = lambda: LocalStorageBackend(storage_root)
    try:
        g = _universe(db, n_stages=1)
        created = _post_instance(client, g["university"].id, g["template"].id).json()
        r = client.post(
            f"/api/v1/workflow/instances/{created['id']}/attachments",
            files={"file": ("report.pdf", io.BytesIO(b"hello-bytes"), "application/pdf")},
        )
        assert r.status_code == 201, r.text
        assert r.json()["instance_id"] == created["id"]
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_cascade_delete_instance_removes_snapshots(db, client):
    g = _universe(db, n_stages=2)
    created = _post_instance(client, g["university"].id, g["template"].id).json()
    iid = uuid.UUID(created["id"])
    assert (
        db.execute(select(func.count()).select_from(InstanceStage).where(InstanceStage.instance_id == iid)).scalar()
        == 2
    )
    db.delete(db.get(WorkflowInstance, iid))
    db.commit()
    assert (
        db.execute(select(func.count()).select_from(InstanceStage).where(InstanceStage.instance_id == iid)).scalar()
        == 0
    )


def test_snapshot_unique_position_and_order_check(db):
    g = _universe(db, n_stages=1)
    inst = WorkflowInstance(university_id=g["university"].id, template_id=g["template"].id)
    db.add(inst)
    db.flush()
    db.add(InstanceStage(instance_id=inst.id, name="A", order_index=1))
    db.commit()
    db.add(InstanceStage(instance_id=inst.id, name="B", order_index=1))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23505"
    db.rollback()
    db.add(InstanceStage(instance_id=inst.id, name="Zero", order_index=0))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23514"
    db.rollback()


# ==================================================== OpenAPI


def test_openapi_instance_routes_present_and_ids_unique(client):
    body = client.get("/openapi.json").json()
    paths = body["paths"]
    assert "/api/v1/workflow/instances" in paths
    assert "/api/v1/workflow/instances/{instance_id}" in paths
    # Existing contracts intact.
    for p in (
        "/api/v1/workflow/templates",
        "/api/v1/workflow/instances/{instance_id}/attachments",
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
    post = paths["/api/v1/workflow/instances"]["post"]
    assert post["responses"]["201"]
    assert paths["/api/v1/workflow/instances/{instance_id}"]["get"]["responses"]["200"]
