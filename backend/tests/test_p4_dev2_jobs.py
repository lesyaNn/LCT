from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.report_job import ReportJob
from app.modules.analytics.integration import UnfilteredProvider
from app.modules.report_jobs import service
from app.modules.report_jobs.schemas import ReportRequest
from tests.p4_dev2_data import uid


def job(**kwargs):
    now = service.utcnow()
    values = dict(
        id=uid(1000),
        user_id="owner",
        user_name="Owner",
        scope_ids=[str(uid(1))],
        format="json",
        filters={},
        columns=[],
        status="queued",
        progress=0,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        started_at=None,
        completed_at=None,
        file_size=None,
        error_message=None,
    )
    values.update(kwargs)
    return ReportJob(**values)


@pytest.mark.parametrize(
    "user,code",
    [
        (CurrentUser(id="owner", roles={"user"}, university_ids=(str(uid(1)),)), None),
        (CurrentUser(id="other", roles={"user"}, university_ids=(str(uid(1)),)), 404),
        (CurrentUser(id="owner", roles={"user"}, university_ids=(str(uid(2)),)), 404),
        (CurrentUser(id="manager", roles={"manager"}), None),
        (CurrentUser(id="admin", roles={"admin"}), None),
        (CurrentUser(id="owner", roles={"user"}), 403),
    ],
)
def test_job_owner_roles_and_revoked_scope(user, code):
    db = Mock()
    db.get.return_value = job()
    if code:
        with pytest.raises(HTTPException) as exc:
            service.get_job(db, uid(1000), user)
        assert exc.value.status_code == code
    else:
        assert service.get_job(db, uid(1000), user).user_id == "owner"


def test_expiry_is_gone_and_job_dto_hides_internal_paths():
    db = Mock()
    db.get.return_value = job(expires_at=service.utcnow() - timedelta(seconds=1))
    with pytest.raises(HTTPException) as exc:
        service.get_job(db, uid(1000), CurrentUser(id="admin", roles={"admin"}))
    assert exc.value.status_code == 410
    result = service.describe(job()).model_dump()
    assert "file_path" not in result and "scope_ids" not in result and "filters" not in result
    assert result["download_url"] is None
    assert service.describe(job(status="ready")).download_url.endswith("/download")


def test_submit_is_queued_and_not_rendered_synchronously():
    db, renderer = Mock(), Mock()
    admin = CurrentUser(id="owner", roles={"admin"})
    result = service.submit(db, ReportRequest(format="json"), admin, UnfilteredProvider(), renderer)
    assert result.status == "queued" and result.scope_ids is None
    db.commit.assert_called_once()
    renderer.validate.assert_called_once()
    renderer.render.assert_not_called()


def test_invalid_filter_or_columns_do_not_create_jobs():
    db, renderer = Mock(), Mock()
    admin = CurrentUser(id="owner", roles={"admin"})
    with pytest.raises(HTTPException):
        service.submit(
            db,
            ReportRequest(format="json", filters={"program_ids": [str(uid(1))]}),
            admin,
            UnfilteredProvider(),
            renderer,
        )
    db.add.assert_not_called()
    renderer.validate.side_effect = HTTPException(422, "Unknown columns")
    with pytest.raises(HTTPException):
        service.submit(db, ReportRequest(format="json"), admin, UnfilteredProvider(), renderer)
    db.add.assert_not_called()
    with pytest.raises(ValidationError):
        ReportRequest(format="exe")


def test_missing_renderer_is_explicit(monkeypatch):
    monkeypatch.delenv("P4_REPORT_RENDERER", raising=False)
    with pytest.raises(HTTPException) as exc:
        service.get_renderer()
    assert exc.value.status_code == 503


def test_download_checks_actual_size_and_readiness(tmp_path, monkeypatch):
    monkeypatch.setenv("P4_REPORT_DIRECTORY", str(tmp_path))
    pending = job()
    with pytest.raises(HTTPException) as exc:
        service.downloadable(pending)
    assert exc.value.status_code == 409
    ready = job(status="ready", file_size=2)
    path = service.artifact_path(ready)
    path.write_bytes(b"{}")
    assert service.downloadable(ready) == path
    ready.file_path = "/arbitrary/untrusted/path"  # ignored; recomputed from UUID
    assert service.downloadable(ready) == path
    ready.file_size = 3
    with pytest.raises(HTTPException) as exc:
        service.downloadable(ready)
    assert exc.value.status_code == 410


def test_worker_duplicate_delivery_never_renders():
    db = Mock()
    db.__enter__ = Mock(return_value=db)
    db.__exit__ = Mock(return_value=False)
    db.execute.return_value = SimpleNamespace(rowcount=0)
    renderer = Mock()
    assert not service.run_job(uid(1), session_factory=lambda: db, renderer=renderer)
    renderer.render.assert_not_called()


def test_polling_and_download_http(tmp_path, monkeypatch):
    monkeypatch.setenv("P4_REPORT_DIRECTORY", str(tmp_path))
    db = Mock()
    record = job()
    db.get.return_value = record
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.update(
        {get_db: lambda: db, get_current_user: lambda: CurrentUser(id="admin", roles={"admin"})}
    )
    try:
        with TestClient(app) as client:
            poll = client.get(f"/api/v1/reports/{record.id}")
            assert poll.status_code == 200
            assert poll.headers["retry-after"] == "3"
            assert poll.headers["cache-control"] == "no-store"
            record.status = "ready"
            record.file_size = 2
            service.artifact_path(record).write_bytes(b"{}")
            response = client.get(f"/api/v1/reports/{record.id}/download")
            assert response.status_code == 200 and response.content == b"{}"
            assert response.headers["content-type"].startswith("application/json")
            assert "attachment" in response.headers["content-disposition"]
            assert "retry-after" not in client.get(f"/api/v1/reports/{record.id}").headers
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
