"""Comment upload uses the canonical workflow attachment row and storage."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.workflow_instances import WorkflowAttachment, WorkflowComment, WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import LocalStorageBackend


@pytest.fixture()
def setup(tmp_path):
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    storage = LocalStorageBackend(tmp_path / "files")

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage] = lambda: storage
    previous = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    try:
        with Session(engine) as db:
            university = University(name="Attachment test", city="Москва")
            template = WorkflowTemplate(name="Attachment test")
            db.add_all([university, template])
            db.flush()
            instance = WorkflowInstance(university_id=university.id, template_id=template.id, status="active")
            db.add(instance)
            db.commit()
            instance_id = instance.id
        yield TestClient(app, raise_server_exceptions=False), engine, storage, instance_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_storage, None)
        settings.auth_dev_bypass = previous
        engine.dispose()


def test_comment_files_persist_and_download(setup):
    client, engine, _, instance_id = setup
    base = f"/api/v1/workflow/instances/{instance_id}"
    plain = client.post(f"{base}/comments", json={"content": "Только текст"})
    assert plain.status_code == 201, plain.text
    created = client.post(
        f"{base}/comments/with-attachments",
        data={"content": "Два файла"},
        files=[("files", ("one.pdf", b"first", "application/pdf")),
               ("files", ("two.pdf", b"second", "application/pdf"))],
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert len(record["attachments"]) == 2
    assert {item["comment_id"] for item in record["attachments"]} == {record["id"]}
    with Session(engine) as db:
        assert db.get(WorkflowComment, record["id"]).content == "Два файла"
        assert len(db.scalars(select(WorkflowAttachment).where(WorkflowAttachment.comment_id == record["id"])).all()) == 2
    listed = client.get(f"{base}/comments")
    assert listed.status_code == 200
    assert len(next(item for item in listed.json()["items"] if item["id"] == record["id"])["attachments"]) == 2
    edited = client.patch(f"/api/v1/workflow/comments/{record['id']}", json={"content": "Исправленный текст"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["content"] == "Исправленный текст"
    assert {item["id"] for item in edited.json()["attachments"]} == {item["id"] for item in record["attachments"]}
    assert edited.json()["created_at"] == record["created_at"]
    assert edited.json()["author_keycloak_sub"] == record["author_keycloak_sub"]
    with Session(engine) as db:
        assert db.get(WorkflowComment, record["id"]).content == "Исправленный текст"
        assert len(db.scalars(select(WorkflowAttachment).where(WorkflowAttachment.comment_id == record["id"])).all()) == 2
    attachment_id = record["attachments"][0]["id"]
    downloaded = client.get(f"{base}/attachments/{attachment_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"first"
    settings.auth_dev_bypass = False
    forbidden_upload = client.post(
        f"{base}/comments/with-attachments",
        data={"content": "Без доступа"},
        files=[("files", ("denied.pdf", b"denied", "application/pdf"))],
    )
    assert forbidden_upload.status_code == 401


def test_failed_second_file_rolls_back_comment_and_first_file(setup, monkeypatch):
    client, engine, storage, instance_id = setup
    monkeypatch.setattr(settings, "upload_allowed_extensions", "pdf")
    created = client.post(
        f"/api/v1/workflow/instances/{instance_id}/comments/with-attachments",
        data={"content": "Не сохранять"},
        files=[("files", ("one.pdf", b"first", "application/pdf")),
               ("files", ("bad.exe", b"second", "application/octet-stream"))],
    )
    assert created.status_code == 400
    with Session(engine) as db:
        assert db.scalars(select(WorkflowComment).where(WorkflowComment.content == "Не сохранять")).all() == []
        assert db.scalars(select(WorkflowAttachment).where(WorkflowAttachment.instance_id == instance_id)).all() == []
    assert [item for item in storage.root.iterdir() if item.is_file()] == []
