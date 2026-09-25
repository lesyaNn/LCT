"""P2-11-02: upload + overdue final acceptance (end-to-end behavior).

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
DB); the schema always comes from the canonical SQL migrations
(``tests/db_helpers.py``). No SQLite, no ``create_all``.

This is the acceptance layer over the frozen low-level suites — it does
NOT duplicate all 45 attachment unit tests, it pins end-to-end behavior:

upload: streaming upload -> metadata (no storage internals leaked) ->
download (exact bytes + headers) -> delete (row + object gone);
authorization (401/403 matrix on frozen permissions); 50 MiB exact
accepted; 50 MiB + 1 -> 413 with no metadata row / file / temp leftovers;
path traversal names stay metadata-only; duplicate filenames get distinct
keys; missing object -> controlled error + idempotent delete; cleanup.

10 file types: the source of truth is still missing — the suite pins
``P2-05-01 = PARTIAL (MISSING_10_FILE_TYPE_CONTRACT)`` and asserts no
invented allowlist is enforced.

overdue: uses ONLY the shared
``app.modules.workflow_instances.overdue.compute_overdue`` (no local
formula — pinned by symbol identity); boundaries (None / yesterday /
today / tomorrow / completed before / on / after due); completion freeze
(days_overdue fixed by completed_at date, independent of today);
instance-level and stage-level values via GET.
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowAttachment,
    WorkflowInstance,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.workflow_attachments.policy import (
    MAX_FILE_SIZE_BYTES,
    content_disposition,
)
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import LocalStorageBackend
from app.modules.workflow_instances import service as instance_service
from app.modules.workflow_instances.overdue import compute_overdue, today_utc

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")

MiB = 1024 * 1024


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
def storage_dir(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    return root


@pytest.fixture()
def backend(storage_dir):
    return LocalStorageBackend(storage_dir)


@pytest.fixture()
def client(engine, backend):
    """Bypass-auth HTTP client (acts as admin) with isolated storage."""

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_storage] = lambda: backend
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    c = TestClient(app, raise_server_exceptions=False)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_storage, None)
        settings.auth_dev_bypass = old


_KID = "p2-11-02"


def _b64url(num: int) -> str:
    import base64

    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def auth_client(engine, backend, monkeypatch):
    """Real JWT validation (local RSA ~ JWKS), dev bypass OFF."""
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

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_storage] = lambda: backend

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

    with TestClient(app, raise_server_exceptions=False) as c:
        c._mint = mint  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)
    settings.auth_dev_bypass = old_bypass
    sec._jwks_cache.update({"keys": [], "fetched_at": 0.0})


def _auth(c, roles, university_ids=None):
    return {"Authorization": f"Bearer {c._mint(roles, university_ids)}"}


# ---------------------------------------------------------------- helpers


def _seed_universe(db: Session, tag: str | None = None):
    tag = tag or _tag()
    u = University(name=f"Acc Uni {tag}", city="Москва")
    t = WorkflowTemplate(name=f"Acc Template {tag}")
    db.add_all([u, t])
    db.flush()
    inst = WorkflowInstance(university_id=u.id, template_id=t.id)
    db.add(inst)
    db.commit()
    return {"university": u, "template": t, "instance": inst}


def _seed_staged_universe(db: Session, n_stages=2, sla=None, tag=None):
    tag = tag or _tag()
    u = University(name=f"Due Uni {tag}", city="Москва")
    t = WorkflowTemplate(name=f"Due Template {tag}")
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


def _upload(c, instance_id, name="report.pdf", data=b"hello-bytes", mime="application/pdf"):
    return c.post(
        f"/api/v1/workflow/instances/{instance_id}/attachments",
        files={"file": (name, io.BytesIO(data), mime)},
    )


def _post_instance(c, university_id, template_id):
    r = c.post(
        "/api/v1/workflow/instances",
        json={"university_id": str(university_id), "template_id": str(template_id)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _stored_files(storage_dir: Path) -> list[str]:
    return sorted(p.name for p in storage_dir.iterdir() if p.is_file())


# ==================================================== upload acceptance ==


def test_acceptance_upload_metadata_download_delete(client, db, storage_dir):
    g = _seed_universe(db)
    payload = b"%PDF-acceptance-" * 64

    r = _upload(client, g["instance"].id, name="report.pdf", data=payload)
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["instance_id"] == str(g["instance"].id)
    assert meta["original_filename"] == "report.pdf"
    assert meta["mime_type"] == "application/pdf"
    assert meta["file_size"] == len(payload)
    assert meta["uploaded_by_keycloak_sub"]
    assert "storage_key" not in r.text  # no storage internals leaked
    assert "/app/storage" not in r.text and str(storage_dir) not in r.text

    m = client.get(f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{meta['id']}")
    assert m.status_code == 200, m.text
    assert m.json() == meta

    d = client.get(
        f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{meta['id']}/download"
    )
    assert d.status_code == 200, d.text
    assert d.content == payload
    assert d.headers["Content-Type"] == "application/pdf"
    assert d.headers["Content-Length"] == str(len(payload))
    assert d.headers["Content-Disposition"].startswith("attachment; ")

    assert len(_stored_files(storage_dir)) == 1
    assert (
        client.delete(
            f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{meta['id']}"
        ).status_code
        == 204
    )
    assert db.get(WorkflowAttachment, meta["id"]) is None
    assert _stored_files(storage_dir) == []  # cleanup: object removed


def test_acceptance_path_traversal_and_duplicate_names(client, db, storage_dir):
    g = _seed_universe(db)
    evil = _upload(client, g["instance"].id, name="../evil.txt", data=b"x")
    assert evil.status_code == 201, evil.text
    stored = evil.json()["original_filename"]
    assert "/" not in stored and "\\" not in stored and ".." not in stored
    assert (storage_dir / "../evil.txt").exists() is False

    r1 = _upload(client, g["instance"].id, name="report.pdf", data=b"v1")
    r2 = _upload(client, g["instance"].id, name="report.pdf", data=b"v2")
    assert r1.status_code == 201 and r2.status_code == 201
    keys = {
        db.execute(
            select(WorkflowAttachment.storage_key).where(WorkflowAttachment.id == r1.json()["id"])
        ).scalar_one(),
        db.execute(
            select(WorkflowAttachment.storage_key).where(WorkflowAttachment.id == r2.json()["id"])
        ).scalar_one(),
    }
    assert len(keys) == 2  # duplicate filename -> distinct objects
    d1 = client.get(
        f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{r1.json()['id']}/download"
    )
    d2 = client.get(
        f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{r2.json()['id']}/download"
    )
    assert d1.content == b"v1" and d2.content == b"v2"
    assert content_disposition("report.pdf").startswith("attachment; ")


def test_acceptance_missing_object_controlled_and_idempotent_delete(client, db, storage_dir):
    g = _seed_universe(db)
    r = _upload(client, g["instance"].id, data=b"doomed")
    aid = r.json()["id"]
    (storage_dir / db.get(WorkflowAttachment, aid).storage_key).unlink()

    d = client.get(f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{aid}/download")
    assert d.status_code == 404  # P2-05-02: missing object is 404, not 500
    assert "Traceback" not in d.text  # controlled error, no leak
    assert (
        client.delete(
            f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{aid}"
        ).status_code
        == 204
    )  # orphaned row still cleaned
    assert db.get(WorkflowAttachment, aid) is None


def test_acceptance_auth_matrix(auth_client, db):
    g = _seed_universe(db)
    iid = str(g["instance"].id)
    admin_h = _auth(auth_client, ["admin"])
    r = auth_client.post(
        f"/api/v1/workflow/instances/{iid}/attachments",
        files={"file": ("seed.pdf", io.BytesIO(b"seed"), "application/pdf")},
        headers=admin_h,
    )
    assert r.status_code == 201, r.text
    meta_url = f"/api/v1/workflow/instances/{iid}/attachments/{r.json()['id']}"

    assert auth_client.get(meta_url).status_code == 401  # no token
    user_h = _auth(auth_client, ["user"])
    assert auth_client.get(meta_url, headers=user_h).status_code == 403
    assert auth_client.get(meta_url + "/download", headers=user_h).status_code == 403
    assert (
        auth_client.post(
            f"/api/v1/workflow/instances/{iid}/attachments",
            files={"file": ("u.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers=user_h,
        ).status_code
        == 403
    )

    mgr_h = _auth(auth_client, ["manager"], [str(g["university"].id)])
    assert auth_client.get(meta_url, headers=mgr_h).status_code == 200  # read OK
    mgr_upload = auth_client.post(
        f"/api/v1/workflow/instances/{iid}/attachments",
        files={"file": ("m.pdf", io.BytesIO(b"x"), "application/pdf")},
        headers=mgr_h,
    )
    assert mgr_upload.status_code == 201, mgr_upload.text
    assert auth_client.delete(
        f"/api/v1/workflow/instances/{iid}/attachments/{mgr_upload.json()['id']}",
        headers=mgr_h,
    ).status_code == 204

    cur_h = _auth(auth_client, ["curator"])
    up = auth_client.post(
        f"/api/v1/workflow/instances/{iid}/attachments",
        files={"file": ("c.pdf", io.BytesIO(b"c"), "application/pdf")},
        headers=cur_h,
    )
    assert up.status_code == 403, up.text
    assert auth_client.delete(meta_url, headers=admin_h).status_code == 204


def _write_sized_file(path: Path, size: int) -> None:
    block = bytes([i % 251 for i in range(MiB)])
    with open(path, "wb") as fh:
        left = size
        while left > 0:
            piece = block[: min(len(block), left)]
            fh.write(piece)
            left -= len(piece)


def test_acceptance_50mib_exact_accepted(client, db, tmp_path):
    assert MAX_FILE_SIZE_BYTES == 50 * MiB
    g = _seed_universe(db)
    path = tmp_path / "exact50.bin"
    _write_sized_file(path, 50 * MiB)
    with open(path, "rb") as fh:
        r = client.post(
            f"/api/v1/workflow/instances/{g['instance'].id}/attachments",
            files={"file": ("big.bin", fh, "application/octet-stream")},
        )
    assert r.status_code == 201, r.text[:500]
    assert r.json()["file_size"] == 50 * MiB
    d = client.get(
        f"/api/v1/workflow/instances/{g['instance'].id}/attachments/{r.json()['id']}/download"
    )
    assert d.status_code == 200
    assert int(d.headers["Content-Length"]) == 50 * MiB


def test_acceptance_50mib_plus_one_413_no_leftovers(client, db, storage_dir, tmp_path):
    g = _seed_universe(db)
    before = db.execute(select(WorkflowAttachment.id)).scalars().all()
    path = tmp_path / "over51.bin"
    _write_sized_file(path, 50 * MiB + 1)
    with open(path, "rb") as fh:
        r = client.post(
            f"/api/v1/workflow/instances/{g['instance'].id}/attachments",
            files={"file": ("big.bin", fh, "application/octet-stream")},
        )
    assert r.status_code == 413, r.text[:500]
    assert db.execute(select(WorkflowAttachment.id)).scalars().all() == before
    assert _stored_files(storage_dir) == []
    assert list((storage_dir / ".tmp").iterdir()) == []


def test_acceptance_10_type_contract_is_partial_not_invented(monkeypatch):
    """P2-05-01: allowlist is env-configured, open by default (no invention).

    Default (no env): the declared type is recorded, never rejected.
    With ``UPLOAD_ALLOWED_EXTENSIONS`` set: other extensions -> 415.
    """

    from app.config import settings
    from app.modules.workflow_attachments import policy
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "upload_allowed_extensions", "")
    assert policy.get_allowed_extensions() is None
    assert policy.check_file_type("report.pdf", "application/pdf") == "application/pdf"
    assert policy.check_file_type("weird.bin", None) == "application/octet-stream"

    monkeypatch.setattr(settings, "upload_allowed_extensions", "pdf,docx")
    assert policy.get_allowed_extensions() == frozenset({"pdf", "docx"})
    assert policy.check_file_type("report.PDF", "application/pdf") == "application/pdf"
    with pytest.raises(HTTPException) as ei:
        policy.check_file_type("run.exe", "application/octet-stream")
        assert ei.value.status_code == 400


# =================================================== overdue acceptance ==


def test_acceptance_uses_canonical_overdue_helper_only():
    """Only the shared helper computes overdue — no second formula."""
    from app.modules.workflow_instances import overdue

    assert instance_service.compute_overdue is overdue.compute_overdue
    import inspect

    source = inspect.getsource(instance_service)
    assert "compute_overdue" in source
    # No date arithmetic on due/completion dates outside the DTO mapping:
    # the service never subtracts dates itself.
    assert " - due_date" not in source and "due_date - " not in source


@pytest.mark.parametrize(
    ("due", "completed", "today", "expected"),
    [
        (None, None, date(2026, 9, 20), (False, 0)),
        (None, datetime(2026, 9, 25, tzinfo=timezone.utc), date(2026, 9, 20), (False, 0)),
        (date(2026, 9, 19), None, date(2026, 9, 20), (True, 1)),  # due yesterday
        (date(2026, 9, 20), None, date(2026, 9, 20), (False, 0)),  # due today
        (date(2026, 9, 21), None, date(2026, 9, 20), (False, 0)),  # due tomorrow
        (
            date(2026, 9, 20),
            datetime(2026, 9, 19, 12, tzinfo=timezone.utc),
            date(2026, 9, 30),
            (False, 0),
        ),
        (
            date(2026, 9, 20),
            datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc),
            date(2026, 9, 30),
            (False, 0),
        ),
        (
            date(2026, 9, 20),
            datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
            date(2026, 9, 30),
            (True, 1),
        ),
        (date(2026, 9, 20), date(2026, 9, 18), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), date(2026, 9, 20), date(2026, 9, 30), (False, 0)),
        (date(2026, 9, 20), date(2026, 9, 23), date(2026, 9, 30), (True, 3)),
    ],
)
def test_acceptance_overdue_boundaries(due, completed, today, expected):
    assert compute_overdue(due, completed, today) == expected


def test_acceptance_completed_freeze_across_today():
    """Late completion freezes days_overdue: today no longer matters."""
    due = date(2026, 9, 20)
    done = datetime(2026, 9, 23, 10, tzinfo=timezone.utc)
    for today in (date(2026, 9, 23), date(2026, 9, 30), date(2027, 1, 1)):
        assert compute_overdue(due, done, today) == (True, 3)
    on_time = datetime(2026, 9, 20, 8, tzinfo=timezone.utc)
    for today in (date(2026, 9, 20), date(2026, 12, 31)):
        assert compute_overdue(due, on_time, today) == (False, 0)


def test_acceptance_instance_overdue_via_get(client, db):
    g = _seed_staged_universe(db, n_stages=2, sla=[5, 5])
    created = _post_instance(client, g["university"].id, g["template"].id)
    iid = uuid.UUID(created["id"])
    assert created["is_overdue"] is False and created["days_overdue"] == 0

    yesterday = today_utc() - timedelta(days=1)
    db.get(WorkflowInstance, iid).due_date = yesterday
    db.commit()
    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    assert got["is_overdue"] is True and got["days_overdue"] == 1

    # Completed on the due date: flag clears and stays cleared (freeze).
    db.get(WorkflowInstance, iid).completed_at = datetime.combine(
        yesterday, datetime.min.time(), tzinfo=timezone.utc
    )
    db.commit()
    done = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    assert done["is_overdue"] is False and done["days_overdue"] == 0


def test_acceptance_stage_overdue_boundaries_via_get(client, db):
    g = _seed_staged_universe(db, n_stages=3, sla=[5, 5, 5])
    created = _post_instance(client, g["university"].id, g["template"].id)
    snaps = {s["order_index"]: uuid.UUID(s["id"]) for s in created["stages"]}
    today = today_utc()

    db.get(InstanceStage, snaps[1]).due_date = today - timedelta(days=2)  # overdue open
    db.get(InstanceStage, snaps[2]).due_date = today  # due today -> not overdue
    db.get(InstanceStage, snaps[3]).due_date = None  # no deadline -> never overdue
    db.commit()
    got = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    by_order = {s["order_index"]: s for s in got["stages"]}
    assert (by_order[1]["is_overdue"], by_order[1]["days_overdue"]) == (True, 2)
    assert (by_order[2]["is_overdue"], by_order[2]["days_overdue"]) == (False, 0)
    assert (by_order[3]["is_overdue"], by_order[3]["days_overdue"]) == (False, 0)

    # Completed late freezes the score at completed_date - due_date.
    db.get(InstanceStage, snaps[1]).completed_at = datetime.combine(
        today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    db.commit()
    frozen = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    first = {s["order_index"]: s for s in frozen["stages"]}[1]
    assert (first["is_overdue"], first["days_overdue"]) == (True, 1)

    # Completed before due -> not overdue.
    db.get(InstanceStage, snaps[2]).completed_at = datetime.combine(
        today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    db.commit()
    cleared = client.get(f"/api/v1/workflow/instances/{created['id']}").json()
    second = {s["order_index"]: s for s in cleared["stages"]}[2]
    assert (second["is_overdue"], second["days_overdue"]) == (False, 0)
