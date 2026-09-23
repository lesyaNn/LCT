"""P2-04-01 / P2-05-02 gaps: attachments list, comment DELETE + pagination,
disable-current guard.

* ``GET /api/v1/workflow/instances/{id}/attachments`` — paginated metadata;
* ``DELETE /api/v1/workflow/comments/{id}`` — author-in-window or admin,
  scope checked BEFORE the delete;
* ``GET .../instances/{id}/comments`` — now paginated;
* ``PATCH .../stages/{id} {is_active: false}`` — 409 when the stage is
  current in an active instance.

DB integration tests require PostgreSQL via ``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import io
import os
import uuid
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata on Base)
from app.core.exceptions import Conflict
from app.main import app
from app.models.catalog import University
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _tag() -> str:
    return uuid4().hex[:8]


@pytest.fixture()
def engine():
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
    from app.modules.workflow_attachments.storage import LocalStorageBackend

    return LocalStorageBackend(storage_dir)


@pytest.fixture()
def client(engine, backend):
    from app.config import settings
    from app.db.session import get_db
    from app.modules.workflow_attachments.router import get_storage

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_storage] = lambda: backend
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_storage, None)
        settings.auth_dev_bypass = old


def _universe(db: Session):
    u = University(name=f"Gap Uni {_tag()}", city="Москва")
    t = WorkflowTemplate(name=f"Gap Template {_tag()}")
    db.add_all([u, t])
    db.flush()
    inst = WorkflowInstance(university_id=u.id, template_id=t.id, status="active")
    db.add(inst)
    db.commit()
    return u, t, inst


def _comment(client: TestClient, instance_id: uuid.UUID, content: str = "note") -> dict:
    r = client.post(
        f"/api/v1/workflow/instances/{instance_id}/comments",
        json={"content": content},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ===================================================== attachments list ==


def test_attachments_list_paginated(db: Session, client: TestClient):
    _u, _t, inst = _universe(db)
    for i in range(3):
        r = client.post(
            f"/api/v1/workflow/instances/{inst.id}/attachments",
            files={"file": (f"f{i}.pdf", io.BytesIO(b"x" * 10), "application/pdf")},
        )
        assert r.status_code == 201, r.text
    page = client.get(f"/api/v1/workflow/instances/{inst.id}/attachments")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3 and len(body["items"]) == 3
    assert all("storage_key" not in item for item in body["items"])
    p1 = client.get(
        f"/api/v1/workflow/instances/{inst.id}/attachments",
        params={"page_size": 2},
    )
    assert len(p1.json()["items"]) == 2
    p2 = client.get(
        f"/api/v1/workflow/instances/{inst.id}/attachments",
        params={"page_size": 2, "page": 2},
    )
    assert len(p2.json()["items"]) == 1
    assert client.get(
        f"/api/v1/workflow/instances/{uuid4()}/attachments"
    ).status_code == 404


# ==================================================== comments delete ==


def test_comment_delete_author_and_admin(db: Session, client: TestClient):
    _u, _t, inst = _universe(db)
    own = _comment(client, inst.id, "mine")
    assert (
        client.delete(f"/api/v1/workflow/comments/{own['id']}").status_code == 204
    )
    assert (
        client.get(
            f"/api/v1/workflow/instances/{inst.id}/comments"
        ).json()["total"]
        == 0
    )
    assert client.delete(f"/api/v1/workflow/comments/{own['id']}").status_code == 404
    assert client.delete(f"/api/v1/workflow/comments/{uuid4()}").status_code == 404


def test_comments_list_paginated_shape(db: Session, client: TestClient):
    _u, _t, inst = _universe(db)
    _comment(client, inst.id, "one")
    _comment(client, inst.id, "two")
    r = client.get(
        f"/api/v1/workflow/instances/{inst.id}/comments", params={"page_size": 1}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2 and len(body["items"]) == 1
    assert body["items"][0]["content"] == "one"  # oldest first


def test_comment_delete_window_and_stranger(db: Session):
    from datetime import datetime, timedelta, timezone

    from app.models.workflow_instances import WorkflowComment
    from app.modules.workflow_transitions import service

    _u, _t, inst = _universe(db)
    mine = service.add_comment(
        db, inst.id, _content("old"), actor="author-1"
    )
    mine.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db.commit()
    # expired window for the author
    with pytest.raises(Conflict):
        service.delete_comment(db, mine.id, "author-1", {"manager"})
    # stranger denied
    with pytest.raises(Exception):
        service.delete_comment(db, mine.id, "stranger", {"manager"})
    # admin override works
    service.delete_comment(db, mine.id, "admin-1", {"admin"})
    assert db.get(WorkflowComment, mine.id) is None


def _content(text: str):
    from app.modules.workflow_transitions.schemas import WorkflowCommentCreate

    return WorkflowCommentCreate(content=text)


# ==================================================== disable guard ==


def test_disable_current_stage_blocked(db: Session):
    from app.modules.workflow_templates import service as template_service

    u = University(name=f"Guard Uni {_tag()}", city="Москва")
    t = WorkflowTemplate(name=f"Guard Template {_tag()}")
    db.add_all([u, t])
    db.flush()
    stage = WorkflowStage(
        template_id=t.id, name="Etap", order_index=1, is_required=True
    )
    db.add(stage)
    db.flush()
    inst = WorkflowInstance(
        university_id=u.id,
        template_id=t.id,
        status="active",
        current_stage_id=stage.id,
    )
    db.add(inst)
    db.commit()
    with pytest.raises(Conflict):
        template_service.patch_stage(
            db, t.id, stage.id,
            fields={"is_active"}, name=None, description=None,
            order_index=None, is_required=None, is_active=False, sla_days=None,
        )
    # non-current stage retires fine
    other = WorkflowStage(
        template_id=t.id, name="Other", order_index=2, is_required=False
    )
    db.add(other)
    db.commit()
    out = template_service.patch_stage(
        db, t.id, other.id,
        fields={"is_active"}, name=None, description=None,
        order_index=None, is_required=None, is_active=False, sla_days=None,
    )
    assert out.is_active is False
