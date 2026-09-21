"""P2-02-04 + P2-11-04: template edit acceptance (rename/add/reorder/disable).

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
DB); the schema always comes from the canonical SQL migrations
(``tests/db_helpers.py``). No SQLite, no ``create_all``. No new migration:
P2-02-04 is application behavior over 000011-000014.

Coverage: rename (template stage renamed, old instance snapshot unchanged,
new instance sees the new name), add (append / insert first / middle / end
with order shift, existing instances untouched, new instances include the
stage), reorder (forward A->4, backward D->2, same-position no-op,
past-end clamp), disable (stays in template history, old instance intact,
new instance excludes it), re-enable (new instance includes it again),
is_required/sla_days snapshot semantics (edits affect future instances
only), different-template isolation, admin-only RBAC (401/403/200),
404 matrix (template / stage / wrong-template leak), transaction rollback
(shift + failed commit -> order intact), dense unique order after edits,
concurrency (FOR UPDATE emission + parallel appends stay dense),
template detail query-count bound (2/14/30 stages), attachment integration
(template edits never break existing attachment rows/download), transition
history RESTRICT regression (referenced stage not deletable, disable is
the retire path).
"""

from __future__ import annotations

import concurrent.futures
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.workflow_templates import service as tmpl_service

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


_KID = "p2-11-04"


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


def _university(db, tag=None):
    u = University(name=f"Edit Uni {tag or _tag()}", city="Москва")
    db.add(u)
    db.commit()
    return u


def _post_instance(client, university_id, template_id):
    r = client.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(university_id), "template_id": str(template_id)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _stage_ids_by_name(detail, *names):
    by_name = {s["name"]: s["id"] for s in detail["stages"]}
    return [by_name[n] for n in names]


# =================================================================== rename


def test_rename_stage_changes_template_only(client, db):
    t = _template(client)
    s = _stage(client, t["id"], name="Original")
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}",
        json={"name": "Renamed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["order_index"] == 1  # rename never moves the stage
    detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    assert [st["name"] for st in detail["stages"]] == ["Renamed"]


def test_rename_old_instance_unchanged_new_instance_changed(client, db):
    t = _template(client)
    _stage(client, t["id"], name="Alpha")
    _stage(client, t["id"], name="Beta")
    u = _university(db)
    old = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in old["stages"]] == ["Alpha", "Beta"]

    sid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "Alpha")[0]
    r = client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{sid}", json={"name": "Alpha-2"})
    assert r.status_code == 200, r.text

    got = client.get(f"/api/v1/workflow/instances/{old['id']}").json()
    assert [s["name"] for s in got["stages"]] == ["Alpha", "Beta"]  # snapshot frozen
    new = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in new["stages"]] == ["Alpha-2", "Beta"]


# ====================================================================== add


def test_append_and_insert_positions(client, db):
    t = _template(client)
    for name in ("A", "B", "C"):
        _stage(client, t["id"], name=name)
    tid = uuid.UUID(t["id"])
    assert _order(db, tid) == [("A", 1), ("B", 2), ("C", 3)]

    appended = _stage(client, t["id"], name="END")
    assert appended["order_index"] == 4
    first = _stage(client, t["id"], name="FIRST", order_index=1)
    assert first["order_index"] == 1
    assert _order(db, tid) == [("FIRST", 1), ("A", 2), ("B", 3), ("C", 4), ("END", 5)]


def test_insert_middle_shifts_only_successors(client, db):
    t = _template(client)
    for name in ("A", "B", "C", "D"):
        _stage(client, t["id"], name=name)
    mid = _stage(client, t["id"], name="X", order_index=3)
    assert mid["order_index"] == 3
    tid = uuid.UUID(t["id"])
    assert _order(db, tid) == [("A", 1), ("B", 2), ("X", 3), ("C", 4), ("D", 5)]


def test_insert_end_explicit_position(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A")
    _stage(client, t["id"], name="B")
    end = _stage(client, t["id"], name="C", order_index=3)
    assert end["order_index"] == 3
    assert _order(db, uuid.UUID(t["id"])) == [("A", 1), ("B", 2), ("C", 3)]


def test_new_stage_visible_only_to_new_instances(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A")
    u = _university(db)
    old = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in old["stages"]] == ["A"]

    _stage(client, t["id"], name="B", order_index=2)
    again = client.get(f"/api/v1/workflow/instances/{old['id']}").json()
    assert [s["name"] for s in again["stages"]] == ["A"]  # no auto-append
    new = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in new["stages"]] == ["A", "B"]


# ================================================================== reorder


def _abcd(client):
    t = _template(client)
    for name in ("A", "B", "C", "D"):
        _stage(client, t["id"], name=name)
    return t


def test_reorder_backward_d_to_2(client, db):
    t = _abcd(client)
    ids = _stage_ids_by_name(
        client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A", "B", "C", "D"
    )
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{ids[3]}", json={"order_index": 2}
    )
    assert r.status_code == 200, r.text
    assert r.json()["order_index"] == 2
    assert _order(db, uuid.UUID(t["id"])) == [("A", 1), ("D", 2), ("B", 3), ("C", 4)]


def test_reorder_forward_a_to_4(client, db):
    t = _abcd(client)
    ids = _stage_ids_by_name(
        client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A", "B", "C", "D"
    )
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{ids[0]}", json={"order_index": 4}
    )
    assert r.status_code == 200, r.text
    assert _order(db, uuid.UUID(t["id"])) == [("B", 1), ("C", 2), ("D", 3), ("A", 4)]


def test_reorder_same_position_is_noop(client, db):
    t = _abcd(client)
    detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    bid = _stage_ids_by_name(detail, "B")[0]
    before = [(s["name"], s["order_index"]) for s in detail["stages"]]
    r = client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{bid}", json={"order_index": 2})
    assert r.status_code == 200, r.text
    assert r.json()["order_index"] == 2
    after = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    assert [(s["name"], s["order_index"]) for s in after["stages"]] == before
    assert _order(db, uuid.UUID(t["id"])) == [("A", 1), ("B", 2), ("C", 3), ("D", 4)]


def test_reorder_past_end_clamps_to_last(client, db):
    t = _abcd(client)
    aid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A")[0]
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{aid}", json={"order_index": 999}
    )
    assert r.status_code == 200, r.text
    assert _order(db, uuid.UUID(t["id"])) == [("B", 1), ("C", 2), ("D", 3), ("A", 4)]


def test_reorder_preserves_is_required_and_sla(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A", is_required=False, sla_days=7)
    _stage(client, t["id"], name="B", is_required=True)
    aid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A")[0]
    r = client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{aid}", json={"order_index": 2})
    assert r.status_code == 200, r.text
    assert r.json()["is_required"] is False  # move must not flip the flag
    assert r.json()["sla_days"] == 7  # move must not touch sla
    assert _order(db, uuid.UUID(t["id"])) == [("B", 1), ("A", 2)]


def test_reorder_does_not_touch_snapshots(client, db):
    t = _abcd(client)
    u = _university(db)
    old = _post_instance(client, u.id, t["id"])
    before = [(s["order_index"], s["name"]) for s in old["stages"]]
    ids = _stage_ids_by_name(
        client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A", "B", "C", "D"
    )
    client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{ids[3]}", json={"order_index": 1})
    got = client.get(f"/api/v1/workflow/instances/{old['id']}").json()
    assert [(s["order_index"], s["name"]) for s in got["stages"]] == before


# ================================================================== disable


def test_disable_stays_in_history_but_excluded_from_new_instances(client, db):
    t = _template(client)
    _stage(client, t["id"], name="Keep")
    gone = _stage(client, t["id"], name="Retire")
    u = _university(db)
    old = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in old["stages"]] == ["Keep", "Retire"]

    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{gone['id']}", json={"is_active": False}
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    assert {s["name"] for s in detail["stages"]} == {"Keep", "Retire"}  # history kept

    kept = client.get(f"/api/v1/workflow/instances/{old['id']}").json()
    assert [s["name"] for s in kept["stages"]] == ["Keep", "Retire"]  # old snapshot intact

    new = _post_instance(client, u.id, t["id"])
    assert [s["name"] for s in new["stages"]] == ["Keep"]  # new snapshot skips inactive


def test_reenable_stage_included_in_new_instances(client, db):
    t = _template(client)
    _stage(client, t["id"], name="Keep")
    flip = _stage(client, t["id"], name="Flip")
    u = _university(db)

    client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{flip['id']}", json={"is_active": False}
    )
    assert [_s["name"] for _s in _post_instance(client, u.id, t["id"])["stages"]] == ["Keep"]

    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{flip['id']}", json={"is_active": True}
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True
    assert [s["name"] for s in _post_instance(client, u.id, t["id"])["stages"]] == ["Keep", "Flip"]


# ==================================================== required / sla snapshot


def test_rename_and_reorder_keep_is_required(client):
    t = _template(client)
    s = _stage(client, t["id"], name="Flagged", is_required=False)
    assert s["is_required"] is False
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}", json={"name": "Flagged-2"}
    )
    assert r.json()["is_required"] is False  # rename must not flip the flag
    _stage(client, t["id"], name="Other")
    m = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}", json={"order_index": 2}
    )
    assert m.json()["is_required"] is False  # reorder must not flip the flag


def test_explicit_is_required_change_is_honored(client):
    t = _template(client)
    s = _stage(client, t["id"], name="Flip")
    assert s["is_required"] is True
    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}", json={"is_required": False}
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_required"] is False


def test_sla_change_affects_only_future_instances(client, db):
    t = _template(client)
    _stage(client, t["id"], name="Timed", sla_days=5)
    _stage(client, t["id"], name="Plain")
    u = _university(db)
    old = _post_instance(client, u.id, t["id"])
    old_due = old["stages"][0]["due_date"]
    assert old_due is not None

    sid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "Timed")[0]
    r = client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{sid}", json={"sla_days": 30})
    assert r.status_code == 200, r.text
    assert r.json()["sla_days"] == 30

    kept = client.get(f"/api/v1/workflow/instances/{old['id']}").json()
    assert kept["stages"][0]["due_date"] == old_due  # existing due_date never recomputed
    new = _post_instance(client, u.id, t["id"])
    assert new["stages"][0]["due_date"] != old_due  # future instances see the new sla


# ================================================================= isolation


def test_edits_are_isolated_per_template(client, db):
    a = _template(client)
    b = _template(client)
    for name in ("A1", "A2", "A3"):
        _stage(client, a["id"], name=name)
    for name in ("B1", "B2"):
        _stage(client, b["id"], name=name)

    aid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{a['id']}").json(), "A3")[0]
    client.patch(f"/api/v1/workflow/templates/{a['id']}/stages/{aid}", json={"order_index": 1})
    assert _order(db, uuid.UUID(a["id"])) == [("A3", 1), ("A1", 2), ("A2", 3)]
    assert _order(db, uuid.UUID(b["id"])) == [("B1", 1), ("B2", 2)]  # untouched


# ====================================================================== RBAC


def test_template_edit_rbac_matrix(auth_client):
    c = auth_client
    admin = _auth(c, ("admin",))
    r = c.post("/api/v1/workflow/templates", json={"name": f"RBAC-{_tag()}"}, headers=admin)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = c.post(f"/api/v1/workflow/templates/{tid}/stages", json={"name": "s1"}, headers=admin)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    stage_url = f"/api/v1/workflow/templates/{tid}/stages/{sid}"
    create_url = f"/api/v1/workflow/templates/{tid}/stages"

    assert c.post(create_url, json={"name": "x"}).status_code == 401
    assert c.patch(stage_url, json={"name": "x"}).status_code == 401
    for roles in (("user",), ("manager",), ("curator",)):
        assert c.post(create_url, json={"name": "x"}, headers=_auth(c, roles)).status_code == 403
        assert c.patch(stage_url, json={"name": "x"}, headers=_auth(c, roles)).status_code == 403
    assert c.post(create_url, json={"name": "ok"}, headers=admin).status_code == 201
    assert c.patch(stage_url, json={"name": "ok2"}, headers=admin).status_code == 200


# ======================================================================= 404


def test_edit_404_matrix(client):
    t = _template(client)
    s = _stage(client, t["id"])
    other = _template(client)
    ghost = str(uuid.uuid4())
    assert client.get(f"/api/v1/workflow/templates/{ghost}").status_code == 404
    assert (
        client.post(f"/api/v1/workflow/templates/{ghost}/stages", json={"name": "x"}).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{ghost}/stages/{s['id']}", json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{ghost}", json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{other['id']}/stages/{s['id']}", json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workflow/templates/{t['id']}/stages", json={"name": "x", "order_index": 0}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}", json={"order_index": 0}
        ).status_code
        == 422
    )


# ======================================================= transaction safety


def test_failed_shift_transaction_rolls_back(db):
    t = WorkflowTemplate(name=f"TX-{_tag()}")
    db.add(t)
    db.flush()
    for i, name in enumerate(("S1", "S2", "S3"), start=1):
        db.add(WorkflowStage(template_id=t.id, name=name, order_index=i))
    db.commit()

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


def test_deferred_unique_still_enforced(db):
    t = WorkflowTemplate(name=f"UQ-{_tag()}")
    db.add(t)
    db.flush()
    db.add(WorkflowStage(template_id=t.id, name="A", order_index=1))
    db.commit()
    db.add(WorkflowStage(template_id=t.id, name="B", order_index=1))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23505"
    db.rollback()
    assert _order(db, t.id) == [("A", 1)]


def test_sequence_stays_dense_after_mixed_edits(client, db):
    t = _template(client)
    for name in ("A", "B", "C", "D", "E"):
        _stage(client, t["id"], name=name)
    detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
    ids = {s["name"]: s["id"] for s in detail["stages"]}
    client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{ids['E']}", json={"order_index": 2})
    client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{ids['A']}", json={"order_index": 5})
    _stage(client, t["id"], name="N", order_index=3)
    rows = _order(db, uuid.UUID(t["id"]))
    assert [o for _, o in rows] == [1, 2, 3, 4, 5, 6]  # dense, no gaps
    assert len({o for _, o in rows}) == 6  # unique
    assert [n for n, _ in rows] == ["E", "B", "N", "C", "D", "A"]


# ================================================================ concurrency


def test_positional_writes_take_for_update_lock(client, engine):
    seen: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _watch(conn, cursor, statement, params, context, executemany):
        if "FOR UPDATE" in statement.upper():
            seen.append(statement)

    try:
        t = _template(client)
        s = _stage(client, t["id"], name="A")
        assert seen, "create_stage must lock the template row (SELECT ... FOR UPDATE)"
        seen.clear()
        r = client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{s['id']}",
            json={"order_index": 1, "name": "A2"},
        )
        assert r.status_code == 200, r.text
        assert seen, "patch_stage must lock the template row (SELECT ... FOR UPDATE)"
    finally:
        event.remove(engine, "before_cursor_execute", _watch)


def test_parallel_appends_stay_dense(engine):
    with Session(engine) as s:
        t = WorkflowTemplate(name=f"Race-{_tag()}")
        s.add(t)
        s.flush()
        for i in range(1, 4):
            s.add(WorkflowStage(template_id=t.id, name=f"S{i}", order_index=i))
        s.commit()
        tid = t.id

    def _append(name):
        with Session(engine) as s:
            return tmpl_service.create_stage(
                s,
                tid,
                name=name,
                description=None,
                order_index=None,
                is_required=True,
                is_active=True,
                sla_days=None,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_append, [f"P{i}" for i in range(4)]))
    assert len(results) == 4
    with Session(engine) as s:
        rows = (
            s.execute(
                select(WorkflowStage.order_index)
                .where(WorkflowStage.template_id == tid)
                .order_by(WorkflowStage.order_index)
            )
            .scalars()
            .all()
        )
    assert rows == [1, 2, 3, 4, 5, 6, 7]  # dense, no duplicates after racing writers


# ===================================================================== N+1


def _make_sized_template(client, db, n):
    t = _template(client)
    for i in range(1, n + 1):
        db.add(WorkflowStage(template_id=uuid.UUID(t["id"]), name=f"S{i}", order_index=i))
    db.commit()
    return t["id"]


def test_detail_query_count_bounded_2_14_30(client, engine, select_counter):
    with Session(engine) as s:
        ids = {n: _make_sized_template(client, s, n) for n in (2, 14, 30)}
    counts = {}
    for n, tid in ids.items():
        with Session(engine):
            select_counter["n"] = 0
            r = client.get(f"/api/v1/workflow/templates/{tid}")
            assert r.status_code == 200, r.text
            assert len(r.json()["stages"]) == n
            counts[n] = select_counter["n"]
    print(f"\nSELECT counts: detail(2)={counts[2]} detail(14)={counts[14]} detail(30)={counts[30]}")
    assert counts[2] <= 4, counts
    assert counts[14] <= 4, counts
    assert counts[30] <= 4, counts  # constant/bounded, no query per stage
    assert counts[2] == counts[14] == counts[30]


# ==================================================== attachment integration


def test_template_edits_keep_attachments_accessible(client, db, tmp_path):
    from app.modules.workflow_attachments.router import get_storage
    from app.modules.workflow_attachments.storage import LocalStorageBackend

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    app.dependency_overrides[get_storage] = lambda: LocalStorageBackend(storage_root)
    try:
        t = _template(client)
        _stage(client, t["id"], name="A")
        _stage(client, t["id"], name="B")
        u = _university(db)
        inst = _post_instance(client, u.id, t["id"])
        payload = b"%PDF-attachment-bytes"
        r = client.post(
            f"/api/v1/workflow/instances/{inst['id']}/attachments",
            files={"file": ("report.pdf", io.BytesIO(payload), "application/pdf")},
        )
        assert r.status_code == 201, r.text
        aid = r.json()["id"]

        detail = client.get(f"/api/v1/workflow/templates/{t['id']}").json()
        ids = {s["name"]: s["id"] for s in detail["stages"]}
        client.patch(f"/api/v1/workflow/templates/{t['id']}/stages/{ids['A']}", json={"name": "A2"})
        client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{ids['B']}", json={"order_index": 1}
        )
        client.patch(
            f"/api/v1/workflow/templates/{t['id']}/stages/{ids['B']}", json={"is_active": False}
        )
        _stage(client, t["id"], name="C", order_index=1)

        meta = client.get(f"/api/v1/workflow/instances/{inst['id']}/attachments/{aid}")
        assert meta.status_code == 200, meta.text
        assert meta.json()["original_filename"] == "report.pdf"
        dl = client.get(f"/api/v1/workflow/instances/{inst['id']}/attachments/{aid}/download")
        assert dl.status_code == 200, dl.text
        assert dl.content == payload
    finally:
        app.dependency_overrides.pop(get_storage, None)


# ================================================= transition history guard


def test_referenced_stage_not_deletable_disable_is_retire_path(client, db):
    t = _template(client)
    _stage(client, t["id"], name="A")
    u = _university(db)
    _post_instance(client, u.id, t["id"])  # creation transition references stage A
    sid = _stage_ids_by_name(client.get(f"/api/v1/workflow/templates/{t['id']}").json(), "A")[0]
    with pytest.raises(IntegrityError) as exc:
        db.delete(db.get(WorkflowStage, uuid.UUID(sid)))
        db.commit()
    assert getattr(exc.value.orig, "sqlstate", None) == "23503"  # RESTRICT (000014)
    db.rollback()

    r = client.patch(
        f"/api/v1/workflow/templates/{t['id']}/stages/{sid}", json={"is_active": False}
    )
    assert r.status_code == 200, r.text  # disable is the normal retire path
    assert [s["name"] for s in _post_instance(client, u.id, t["id"])["stages"]] == []
