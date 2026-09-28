"""P2-05-01..04: secure workflow file storage (attachments of instances).

Canonical table ONLY: ``workflow_attachments`` (migration 000012, no new
migration). Access chain: attachment -> instance -> university.

PostgreSQL integration tests (``TEST_DATABASE_URL``) use the canonical SQL
migrations; pure-unit storage/policy/contract tests run everywhere.

Coverage: small upload, chunked streaming (read-size proof), metadata
(no path leak), download exact bytes + headers, delete (object + row),
duplicate filename (distinct storage_key), unicode filename, path
traversal, 401/403, cross-university A/B isolation, 404s (instance,
attachment, cross-instance binding), missing physical object (controlled
error), storage failure (no false 204), size boundaries 49 MiB / 50 MiB /
50 MiB+1 (generated files, no giant bytes objects), Local backend contract
(save/exists/open/delete/missing/duplicate/traversal key), S3 seam
(unconfigured -> StorageNotConfigured), allowlist single-point status.
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.modules.audit.models import AuditEvent
from app.models.catalog import University
from app.models.workflow_instances import WorkflowAttachment, WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.workflow_attachments import service as attach_service
from app.modules.workflow_attachments.policy import (
    MAX_FILE_SIZE_BYTES,
    UPLOAD_CHUNK_SIZE_BYTES,
    content_disposition,
    sanitize_filename,
)
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import (
    LocalStorageBackend,
    S3StorageBackend,
    StorageError,
    StorageObjectNotFound,
    build_storage_backend,
    new_storage_key,
)

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


_KID = "p2-wf-attach"


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
    """Two universities, one template, one instance per university."""
    tag = tag or _tag()
    ua = University(name=f"Attach Uni A {tag}", city="Москва")
    ub = University(name=f"Attach Uni B {tag}", city="Казань")
    t = WorkflowTemplate(name=f"Attach Template {tag}")
    db.add_all([ua, ub, t])
    db.flush()
    ia = WorkflowInstance(university_id=ua.id, template_id=t.id)
    ib = WorkflowInstance(university_id=ub.id, template_id=t.id)
    db.add_all([ia, ib])
    db.commit()
    return {"ua": ua, "ub": ub, "template": t, "ia": ia, "ib": ib}


def _upload(c, instance_id, name="report.pdf", data=b"hello-bytes", mime="application/pdf"):
    return c.post(
        f"/api/v1/workflow/instances/{instance_id}/attachments",
        files={"file": (name, io.BytesIO(data), mime)},
    )


def _stored_files(storage_dir: Path) -> list[str]:
    return sorted(p.name for p in storage_dir.iterdir() if p.is_file())


def test_comment_attachment_write_permission(auth_client, db):
    graph = _seed_universe(db)
    url = f"/api/v1/workflow/instances/{graph['ia'].id}/comments/with-attachments"
    payload = {"content": "Разрешённое вложение"}
    files = [("files", ("note.pdf", b"bytes", "application/pdf"))]
    assert auth_client.post(url, data=payload, files=files).status_code == 401
    assert auth_client.post(url, data=payload, files=files, headers=_auth(auth_client, ["user"])).status_code == 403
    permitted = auth_client.post(
        url, data=payload, files=files,
        headers=_auth(auth_client, ["manager"], [str(graph['ua'].id)]),
    )
    assert permitted.status_code == 201, permitted.text
    assert len(permitted.json()["attachments"]) == 1


# ============================================================ pure-unit ==
# These run everywhere (no database): policy, backend contract, S3 seam.


def test_limits_and_chunk_constants():
    assert MAX_FILE_SIZE_BYTES == 50 * 1024 * 1024
    assert UPLOAD_CHUNK_SIZE_BYTES == 256 * 1024


def test_file_type_contract_blocked_not_invented(monkeypatch):
    from app.config import settings
    from app.modules.workflow_attachments import policy
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "upload_allowed_extensions", "")
    assert policy.get_allowed_extensions() is None
    # Without a contract the declared type is recorded, never rejected.
    assert policy.check_file_type("report.pdf", "application/pdf") == "application/pdf"
    assert policy.check_file_type("weird.bin", None) == "application/octet-stream"
    monkeypatch.setattr(settings, "upload_allowed_extensions", "pdf")
    with pytest.raises(HTTPException) as ei:
        policy.check_file_type("run.exe", "application/octet-stream")
    assert ei.value.status_code == 400


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../evil.txt", "evil.txt"),
        ("..\\evil.txt", "evil.txt"),
        ("/abs/path.txt", "path.txt"),
        ("C:\\evil.txt", "evil.txt"),
        ("C:/evil.txt", "evil.txt"),
        ("a/b/c.txt", "c.txt"),
        ("..", "file"),
        (".", "file"),
        ("", "file"),
        (None, "file"),
        ("  spaced .pdf ", "spaced .pdf"),
        ("отчёт_финал.pdf", "отчёт_финал.pdf"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_strips_control_and_crlf():
    assert sanitize_filename("a\x00b.pdf") == "ab.pdf"
    out = sanitize_filename("evil\r\nHeader: x.pdf")
    assert "\r" not in out and "\n" not in out and "\x00" not in out
    assert "/" not in out and "\\" not in out


def test_content_disposition_ascii_and_rfc5987():
    header = content_disposition("отчёт.pdf")
    assert header.startswith("attachment; ")
    assert 'filename="' in header and "filename*=UTF-8''" in header
    assert "\r" not in header and "\n" not in header
    plain = content_disposition("report.pdf")
    assert 'filename="report.pdf"' in plain


def test_local_backend_contract_save_exists_open_delete(backend, storage_dir):
    key = new_storage_key()
    assert backend.exists(key) is False
    assert backend.save_stream(key, [b"ab", b"cd", b""]) == 4
    assert backend.exists(key) is True
    with backend.open_stream(key) as fh:
        assert fh.read() == b"abcd"
    backend.delete(key)
    assert backend.exists(key) is False


def test_local_backend_missing_object_errors(backend):
    key = new_storage_key()
    with pytest.raises(StorageObjectNotFound):
        with backend.open_stream(key):
            pass
    with pytest.raises(StorageObjectNotFound):
        backend.delete(key)


def test_local_backend_duplicate_keys_isolated(backend):
    k1, k2 = new_storage_key(), new_storage_key()
    assert k1 != k2
    backend.save_stream(k1, [b"one"])
    backend.save_stream(k2, [b"two"])
    with backend.open_stream(k1) as fh:
        assert fh.read() == b"one"
    with backend.open_stream(k2) as fh:
        assert fh.read() == b"two"


def test_local_backend_rejects_path_like_keys(backend, storage_dir):
    for bad in ("../evil", "a/b", "C:\\x", "..", "", "key with space"):
        with pytest.raises(StorageError):
            backend.save_stream(bad, [b"x"])
    assert _stored_files(storage_dir) == []


def test_local_backend_physical_name_has_no_original_filename(backend, storage_dir):
    backend.save_stream(new_storage_key(), [b"data"])
    names = _stored_files(storage_dir)
    assert len(names) == 1
    assert "report" not in names[0] and "/" not in names[0]


def test_storage_factory_defaults_to_local(tmp_path):
    backend = build_storage_backend(root=tmp_path / "r")
    assert isinstance(backend, LocalStorageBackend)


def test_s3_seam_unconfigured_raises_not_obscure():
    seam = S3StorageBackend(endpoint="", access_key="", secret_key="", bucket="")
    with pytest.raises(StorageError):
        seam.save_stream(new_storage_key(), [b"x"])
    assert seam.exists(new_storage_key()) is False


def test_s3_seam_passes_http_control_flow_through(monkeypatch):
    """413 from the chunk generator must not be wrapped into StorageError."""
    from fastapi import HTTPException

    seam = S3StorageBackend(
        endpoint="http://minio:9000", access_key="k", secret_key="s", bucket="b"
    )

    class _FakeClient:
        def fput_object(self, *a, **k):
            raise AssertionError("must not upload after 413")

    monkeypatch.setattr(seam, "_connect", lambda: _FakeClient())

    def _boom():
        yield b"prefix"
        raise HTTPException(status_code=413, detail="File too large")

    with pytest.raises(HTTPException) as exc:
        seam.save_stream(new_storage_key(), _boom())
    assert exc.value.status_code == 413


# ============================================================ PG: CRUD ==


def test_small_upload_metadata_download_delete(client, db, backend, storage_dir):
    g = _seed_universe(db)
    payload = b"%PDF-bytes-" * 100

    r = _upload(client, g["ia"].id, name="report.pdf", data=payload)
    assert r.status_code == 201, r.text
    meta = r.json()

    assert meta["instance_id"] == str(g["ia"].id)
    assert meta["original_filename"] == "report.pdf"
    assert meta["mime_type"] == "application/pdf"
    assert meta["file_size"] == len(payload)
    assert meta["uploaded_by_keycloak_sub"]
    assert meta["created_at"] and meta["updated_at"] and meta["id"]
    # No storage internals leak into the response.
    blob = r.text
    assert "storage_key" not in blob
    assert "/app/storage" not in blob and str(storage_dir) not in blob

    row = db.execute(
        select(WorkflowAttachment).where(WorkflowAttachment.id == meta["id"])
    ).scalar_one()
    assert row.storage_key and "/" not in row.storage_key
    assert row.instance_id == g["ia"].id
    created_audit = db.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "document",
            AuditEvent.entity_id == row.id,
            AuditEvent.action == "CREATE",
        )
    ).scalar_one()
    assert created_audit.university_id == g["ua"].id

    listed = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments")
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == meta["id"] for item in listed.json()["items"])

    # --- metadata endpoint mirrors the upload response, still no leak
    m = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{meta['id']}")
    assert m.status_code == 200, m.text
    assert m.json() == meta

    # --- download: exact bytes + headers
    d = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{meta['id']}/download")
    assert d.status_code == 200, d.text
    assert d.content == payload
    assert d.headers["Content-Type"] == "application/pdf"
    assert d.headers["Content-Length"] == str(len(payload))
    assert d.headers["Content-Disposition"].startswith("attachment; ")

    # --- delete: row + object gone
    assert len(_stored_files(storage_dir)) == 1
    dl = client.delete(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{meta['id']}")
    assert dl.status_code == 204, dl.text
    assert db.get(WorkflowAttachment, meta["id"]) is None
    assert _stored_files(storage_dir) == []
    assert (
        client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{meta['id']}").status_code
        == 404
    )


def test_service_streams_in_chunks_not_whole_file(db, backend):
    """The service reads the stream in 256 KiB pieces (no full read)."""
    g = _seed_universe(db)
    calls: list[int] = []

    class ChunkedStream(io.RawIOBase):
        def __init__(self, size: int):
            self._left = size

        def readable(self):
            return True

        def read(self, n=-1):
            calls.append(n)
            if self._left <= 0:
                return b""
            piece = b"q" * min(n if n and n > 0 else self._left, self._left)
            self._left -= len(piece)
            return piece

    stream = ChunkedStream(UPLOAD_CHUNK_SIZE_BYTES * 2 + 7)
    row = attach_service.upload_attachment(
        db,
        backend,
        instance_id=g["ia"].id,
        filename="big.bin",
        content_type="application/octet-stream",
        stream=stream,
        actor_sub="uploader-1",
    )
    assert row.file_size == UPLOAD_CHUNK_SIZE_BYTES * 2 + 7
    assert calls, "stream was never read"
    assert all(n == UPLOAD_CHUNK_SIZE_BYTES for n in calls)


def test_duplicate_filenames_get_distinct_keys(client, db):
    g = _seed_universe(db)
    r1 = _upload(client, g["ia"].id, name="report.pdf", data=b"v1")
    r2 = _upload(client, g["ia"].id, name="report.pdf", data=b"v2")
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    keys = {
        db.execute(
            select(WorkflowAttachment.storage_key).where(WorkflowAttachment.id == r1.json()["id"])
        ).scalar_one(),
        db.execute(
            select(WorkflowAttachment.storage_key).where(WorkflowAttachment.id == r2.json()["id"])
        ).scalar_one(),
    }
    assert len(keys) == 2
    d1 = client.get(
        f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{r1.json()['id']}/download"
    )
    d2 = client.get(
        f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{r2.json()['id']}/download"
    )
    assert d1.content == b"v1" and d2.content == b"v2"


def test_unicode_filename_roundtrip(client, db):
    g = _seed_universe(db)
    name = "отчёт_финал_№1.pdf"
    r = _upload(client, g["ia"].id, name=name, data=b"unicode")
    assert r.status_code == 201, r.text
    assert r.json()["original_filename"] == name
    d = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{r.json()['id']}/download")
    assert d.status_code == 200 and d.content == b"unicode"
    assert "filename*=" in d.headers["Content-Disposition"]


@pytest.mark.parametrize(
    "evil",
    ["../evil.txt", "..\\evil.txt", "/abs.txt", "C:\\evil.txt", "a/b/c.txt"],
)
def test_path_traversal_names_stay_metadata_only(client, db, storage_dir, evil):
    g = _seed_universe(db)
    r = _upload(client, g["ia"].id, name=evil, data=b"x")
    assert r.status_code == 201, (evil, r.text)
    stored = r.json()["original_filename"]
    assert "/" not in stored and "\\" not in stored and ".." not in stored
    names = _stored_files(storage_dir)
    assert len(names) == 1 and evil not in names[0]
    # No escape from the storage root.
    assert (storage_dir / evil).exists() is False
    d = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{r.json()['id']}/download")
    assert d.status_code == 200 and d.content == b"x"
    assert "\r" not in d.headers["Content-Disposition"]
    assert "\n" not in d.headers["Content-Disposition"]


def test_404_matrix(client, db):
    g = _seed_universe(db)
    ghost_instance = uuid.uuid4()
    ghost_attachment = uuid.uuid4()

    assert _upload(client, ghost_instance, data=b"x").status_code == 404
    assert (
        client.get(
            f"/api/v1/workflow/instances/{ghost_instance}/attachments/{ghost_attachment}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workflow/instances/{ghost_instance}/attachments/{ghost_attachment}/download"
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/workflow/instances/{ghost_instance}/attachments/{ghost_attachment}"
        ).status_code
        == 404
    )

    # Existing attachment addressed under the WRONG instance -> 404 (no leak).
    r = _upload(client, g["ia"].id, data=b"secret-a")
    aid = r.json()["id"]
    assert (
        client.get(f"/api/v1/workflow/instances/{g['ib'].id}/attachments/{aid}").status_code == 404
    )
    assert (
        client.get(
            f"/api/v1/workflow/instances/{g['ib'].id}/attachments/{aid}/download"
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/workflow/instances/{g['ib'].id}/attachments/{aid}").status_code
        == 404
    )
    # Still intact under the owning instance.
    assert (
        client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}").status_code == 200
    )


def test_401_without_token(auth_client, db):
    g = _seed_universe(db)
    iid = str(g["ia"].id)
    assert (
        auth_client.get(f"/api/v1/workflow/instances/{iid}/attachments/{uuid.uuid4()}").status_code
        == 401
    )
    assert (
        auth_client.post(
            f"/api/v1/workflow/instances/{iid}/attachments",
            files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
        ).status_code
        == 401
    )


def test_rbac_allowed_denied_and_admin(auth_client, db):
    g = _seed_universe(db)
    iid = str(g["ia"].id)

    # Seed one attachment with a full-access admin token.
    admin_headers = _auth(auth_client, ["admin"])
    r = auth_client.post(
        f"/api/v1/workflow/instances/{iid}/attachments",
        files={"file": ("seed.pdf", io.BytesIO(b"seed"), "application/pdf")},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    meta_url = f"/api/v1/workflow/instances/{iid}/attachments/{aid}"
    dl_url = meta_url + "/download"

    # No university assignment: the user has no visible data scope.
    user_h = _auth(auth_client, ["user"])
    assert auth_client.get(meta_url, headers=user_h).status_code == 403
    assert auth_client.get(dl_url, headers=user_h).status_code == 403
    assert (
        auth_client.post(
            f"/api/v1/workflow/instances/{iid}/attachments",
            files={"file": ("u.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers=user_h,
        ).status_code
        == 403
    )
    assert auth_client.delete(meta_url, headers=user_h).status_code == 403

    # Assigned manager has read/create/delete permissions in the P5 matrix.
    mgr_h = _auth(auth_client, ["manager"], [str(g["ua"].id)])
    assert auth_client.get(meta_url, headers=mgr_h).status_code == 200
    assert auth_client.get(dl_url, headers=mgr_h).status_code == 200
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

    # Unknown legacy role grants nothing, even where old permissions allowed a verb.
    cur_h = _auth(auth_client, ["curator"])
    assert auth_client.get(meta_url, headers=cur_h).status_code == 403
    up = auth_client.post(
        f"/api/v1/workflow/instances/{iid}/attachments",
        files={"file": ("c.pdf", io.BytesIO(b"c"), "application/pdf")},
        headers=cur_h,
    )
    assert up.status_code == 403, up.text

    # admin: full access (already demonstrated by the seed upload above).
    assert auth_client.delete(meta_url, headers=admin_headers).status_code == 204


def test_cross_university_isolation(auth_client, db):
    g = _seed_universe(db)
    a_headers = _auth(auth_client, ["manager"], [str(g["ua"].id)])
    b_headers = _auth(auth_client, ["manager"], [str(g["ub"].id)])

    ra = auth_client.post(
        f"/api/v1/workflow/instances/{g['ia'].id}/attachments",
        files={"file": ("a.pdf", io.BytesIO(b"AAA"), "application/pdf")},
        headers=a_headers,
    )
    rb = auth_client.post(
        f"/api/v1/workflow/instances/{g['ib'].id}/attachments",
        files={"file": ("b.pdf", io.BytesIO(b"BBB"), "application/pdf")},
        headers=b_headers,
    )
    assert ra.status_code == 201 and rb.status_code == 201
    aid, bid = ra.json()["id"], rb.json()["id"]

    # User A cannot touch B in any way (and vice versa).
    for headers, iid, other in (
        (a_headers, g["ib"].id, bid),
        (b_headers, g["ia"].id, aid),
    ):
        base = f"/api/v1/workflow/instances/{iid}/attachments"
        assert auth_client.get(f"{base}/{other}", headers=headers).status_code == 403
        assert auth_client.get(f"{base}/{other}/download", headers=headers).status_code == 403
        assert auth_client.delete(f"{base}/{other}", headers=headers).status_code == 403
        assert (
            auth_client.post(
                base,
                files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
                headers=headers,
            ).status_code
            == 403
        )

    # Same-university access still works for both.
    assert (
        auth_client.get(
            f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}",
            headers=a_headers,
        ).status_code
        == 200
    )
    assert (
        auth_client.get(
            f"/api/v1/workflow/instances/{g['ib'].id}/attachments/{bid}",
            headers=b_headers,
        ).status_code
        == 200
    )

    # Admin (no scope) reaches both.
    admin_h = _auth(auth_client, ["admin"])
    assert (
        auth_client.get(
            f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}",
            headers=admin_h,
        ).status_code
        == 200
    )
    assert (
        auth_client.get(
            f"/api/v1/workflow/instances/{g['ib'].id}/attachments/{bid}",
            headers=admin_h,
        ).status_code
        == 200
    )


def test_missing_physical_object_is_controlled(client, db, backend, storage_dir):
    g = _seed_universe(db)
    r = _upload(client, g["ia"].id, data=b"doomed")
    aid = r.json()["id"]
    row = db.get(WorkflowAttachment, aid)
    (storage_dir / row.storage_key).unlink()

    d = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}/download")
    assert d.status_code == 404  # P2-05-02: missing object is 404, not 500
    body = d.text
    assert "Traceback" not in body
    assert "/app/storage" not in body and str(storage_dir) not in body

    # Idempotent delete still cleans the orphaned row -> 204, no false error.
    assert (
        client.delete(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}").status_code
        == 204
    )
    assert db.get(WorkflowAttachment, aid) is None


def test_storage_failure_never_false_204(client, db, backend, storage_dir):
    g = _seed_universe(db)
    r = _upload(client, g["ia"].id, data=b"fragile")
    assert r.status_code == 201
    aid = r.json()["id"]

    class FailingBackend(LocalStorageBackend):
        def delete(self, key: str) -> None:
            raise StorageError("disk gone")

    app.dependency_overrides[get_storage] = lambda: FailingBackend(storage_dir)
    try:
        resp = client.delete(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{aid}")
    finally:
        app.dependency_overrides[get_storage] = lambda: backend
    assert resp.status_code in (500, 503)
    # Row kept: no false 204, retry still possible.
    db.expire_all()
    assert db.get(WorkflowAttachment, aid) is not None


def _write_sized_file(path: Path, size: int) -> None:
    block = bytes([i % 251 for i in range(MiB)])  # 1 MiB buffer, reused
    with open(path, "wb") as fh:
        left = size
        while left > 0:
            piece = block[: min(len(block), left)]
            fh.write(piece)
            left -= len(piece)


def _upload_path(c, instance_id, path: Path, name="big.bin"):
    with open(path, "rb") as fh:
        return c.post(
            f"/api/v1/workflow/instances/{instance_id}/attachments",
            files={"file": (name, fh, "application/octet-stream")},
        )


def test_size_49mib_accepted(client, db, tmp_path):
    g = _seed_universe(db)
    path = tmp_path / "f49.bin"
    _write_sized_file(path, 49 * MiB)
    r = _upload_path(client, g["ia"].id, path)
    assert r.status_code == 201, r.text[:500]
    assert r.json()["file_size"] == 49 * MiB


def test_size_50mib_exact_accepted(client, db, tmp_path):
    g = _seed_universe(db)
    path = tmp_path / "f50.bin"
    _write_sized_file(path, 50 * MiB)
    r = _upload_path(client, g["ia"].id, path)
    assert r.status_code == 201, r.text[:500]
    assert r.json()["file_size"] == 50 * MiB
    d = client.get(f"/api/v1/workflow/instances/{g['ia'].id}/attachments/{r.json()['id']}/download")
    assert d.status_code == 200
    assert int(d.headers["Content-Length"]) == 50 * MiB
    assert len(d.content) == 50 * MiB


def test_size_50mib_plus_one_rejected_413_no_leftovers(client, db, storage_dir, tmp_path):
    g = _seed_universe(db)
    before_rows = db.execute(select(WorkflowAttachment.id)).scalars().all()
    path = tmp_path / "f51.bin"
    _write_sized_file(path, 50 * MiB + 1)
    r = _upload_path(client, g["ia"].id, path)
    assert r.status_code == 413, r.text[:500]
    after_rows = db.execute(select(WorkflowAttachment.id)).scalars().all()
    assert after_rows == before_rows  # no metadata row
    assert _stored_files(storage_dir) == []  # no final file
    tmp_left = list((storage_dir / ".tmp").iterdir())
    assert tmp_left == []  # no temp file


def test_db_failure_after_write_removes_object(client, db, backend, monkeypatch):
    """Commit crash -> physical object cleaned up, client sees an error."""
    g = _seed_universe(db)

    import sqlalchemy.orm

    orig_commit = sqlalchemy.orm.Session.commit

    def _boom(self, *a, **k):
        raise RuntimeError("commit crashed")

    monkeypatch.setattr(sqlalchemy.orm.Session, "commit", _boom)
    try:
        r = _upload(client, g["ia"].id, data=b"orphan?")
    finally:
        monkeypatch.setattr(sqlalchemy.orm.Session, "commit", orig_commit)
    assert r.status_code in (500, 409)
    assert _stored_files(backend.root) == []


def test_openapi_mounts_new_routes_without_losing_old(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec["paths"]
    assert "/api/v1/workflow/instances/{instance_id}/attachments" in paths
    assert "/api/v1/workflow/instances/{instance_id}/attachments/{attachment_id}" in paths
    assert "/api/v1/workflow/instances/{instance_id}/attachments/{attachment_id}/download" in paths
    # Old routes intact.
    assert "/api/v1/workflow/templates" in paths
    assert "/api/v1/catalog/overview" in paths
    # New operations carry summaries + tags; operationIds stay unique.
    seen: set[str] = set()
    for path, item in paths.items():
        for method, op in item.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            assert op.get("summary"), (method, path)
            assert op.get("tags"), (method, path)
            oid = op.get("operation_id")
            if oid:
                assert oid not in seen, oid
                seen.add(oid)
