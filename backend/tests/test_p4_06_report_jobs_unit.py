"""P4-06-01 unit tests: job helpers without a database.

Covers the traversal-safe path layer, server-generated filenames, error
sanitation and the security-context rehydration (never ``user=None``).
Persistence/lifecycle/expiry stay in ``test_p4_06_report_jobs_pg.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.report_job import (
    REPORT_JOB_STATUSES,
    STATUS_BUILDING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
    ReportJob,
)
from app.core.security import CurrentUser
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.report_worker import build_worker_user
from app.schemas.common import ReportFormat


def test_status_contract_is_single_source():
    assert REPORT_JOB_STATUSES == ("queued", "building", "ready", "failed")
    assert (STATUS_QUEUED, STATUS_BUILDING, STATUS_READY, STATUS_FAILED) == REPORT_JOB_STATUSES


def test_job_filename_is_server_generated():
    job_id = uuid.uuid4()
    assert jobs.job_filename(job_id, "xlsx") == f"report_{job_id}.xlsx"
    assert jobs.job_filename(str(job_id), "pdf") == f"report_{job_id}.pdf"


def test_reports_root_defaults_outside_public(tmp_path, monkeypatch):
    monkeypatch.delenv("REPORTS_DIR", raising=False)
    monkeypatch.setattr("app.modules.analytics.report_jobs.settings.reports_root", "/app/reports")
    root = jobs.reports_root()
    assert root.as_posix() == "/app/reports"
    _ = tmp_path


def test_contained_job_path_accepts_own_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    job_id = uuid.uuid4()
    target = tmp_path / f"report_{job_id}.xlsx"
    target.write_bytes(b"x")
    assert jobs.contained_job_path(str(target)) == target.resolve()


def test_every_report_format_is_storable_and_downloadable(tmp_path, monkeypatch):
    """Adding a ReportFormat must not need a matching hand-written edit.

    Regression: XLS was added to the enum and the worker's generator table, but
    two hard-coded format lists were missed, so an XLS report was rejected at
    creation (422) and its already-written artifact was not downloadable
    (404 FILE_NOT_FOUND) — both with no failing test.
    """
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    formats = [f.value for f in ReportFormat]
    assert set(formats) == set(jobs.SUPPORTED_JOB_FORMATS)

    job_id = uuid.uuid4()
    for fmt in formats:
        artifact = tmp_path / f"report_{job_id}.{fmt}"
        artifact.write_bytes(b"x")
        assert jobs.contained_job_path(str(artifact)) == artifact.resolve(), (
            f"artifact of format {fmt!r} is not downloadable"
        )


def test_contained_job_path_rejects_traversal_and_foreign_files(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    outside = tmp_path.parent / "evil.xlsx"
    assert jobs.contained_job_path(str(outside)) is None
    assert jobs.contained_job_path(str(tmp_path / ".." / "evil.xlsx")) is None
    assert jobs.contained_job_path(str(tmp_path / "notes.xlsx")) is None
    assert jobs.contained_job_path(str(tmp_path / "report_x.xlsx")) is None
    assert jobs.contained_job_path("") is None
    assert jobs.contained_job_path(None) is None


def test_sanitize_error_message_strips_secrets_and_tracebacks():
    err = RuntimeError(
        "boom password=supersecret token: abc123\nTraceback (most recent call last):\n  File x, line 1"
    )
    text = jobs.sanitize_error_message(err)
    assert "\n" not in text
    assert "supersecret" not in text and "abc123" not in text
    assert "Traceback" not in text
    assert text.startswith("RuntimeError:")


def test_sanitize_error_message_truncates_long_errors():
    text = jobs.sanitize_error_message(ValueError("x" * 2000))
    assert len(text) == 500


def _job(**overrides) -> ReportJob:
    now = datetime.now(timezone.utc)
    base = dict(
        format="xlsx",
        filters={},
        columns=["university"],
        actor_sub="scoped-1",
        actor_name="Scoped",
        actor_roles=["manager"],
        effective_university_ids=None,
        status="queued",
        progress=0,
        created_at=now,
        expires_at=now,
    )
    base.update(overrides)
    return ReportJob(**base)


def test_build_worker_user_rehydrates_scope_never_none():
    beta = str(uuid.uuid4())
    user = build_worker_user(
        _job(actor_sub="scoped-1", actor_roles=["manager"],
             effective_university_ids=[beta])
    )
    assert user.id == "scoped-1"
    assert user.roles == {"manager"}
    assert user.university_ids == (beta,)


def test_build_worker_user_global_scope_only_from_explicit_snapshot():
    user = build_worker_user(_job(actor_sub="a", actor_roles=["admin"]))
    assert user.university_ids is None
    empty = build_worker_user(
        _job(actor_sub="s", actor_roles=["manager"], effective_university_ids=[])
    )
    assert tuple(empty.university_ids or ()) == ()  # fail-closed empty scope


def test_build_worker_user_drops_unknown_roles():
    user = build_worker_user(_job(actor_roles=["superuser"]))
    assert user.roles == set()


def test_expiry_window_is_24h_tz_aware():
    from datetime import timedelta

    assert timedelta(hours=jobs.REPORT_EXPIRY_HOURS) == timedelta(hours=24)
    assert datetime.now(timezone.utc).tzinfo is not None


def test_job_visible_to_manager_and_admin_see_all():
    job = ReportJob(actor_sub="owner", status=STATUS_QUEUED)
    owner = CurrentUser(id="owner", roles={"user"})
    other_user = CurrentUser(id="stranger", roles={"user"})
    manager = CurrentUser(id="mgr", roles={"manager"})
    admin = CurrentUser(id="adm", roles={"admin"})
    assert jobs.job_visible_to(job, owner) is True
    assert jobs.job_visible_to(job, other_user) is False
    assert jobs.job_visible_to(job, manager) is True
    assert jobs.job_visible_to(job, admin, is_admin=True) is True


def _sqlite_job_db():
    """Single-table sqlite DB for the claim state machine (no PG needed)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base  # noqa: F401  (metadata registered via models)
    import app.models  # noqa: F401

    eng = create_engine("sqlite://")
    ReportJob.__table__.create(eng)
    return eng, Session


def _queued_job(db, **kw):
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    job = ReportJob(
        format="xlsx", filters={}, columns=[],
        actor_sub="u1", status=STATUS_QUEUED, progress=0,
        created_at=now, expires_at=now + timedelta(hours=24),
        **kw,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_claim_job_is_atomic_single_winner(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    eng, Session = _sqlite_job_db()
    with Session(eng) as db:
        job = _queued_job(db)
        first = jobs.claim_job(db, job.id)
        assert first is not None and first.status == STATUS_BUILDING
        assert first.attempts == 1
        assert jobs.claim_job(db, job.id) is None  # second claimant loses
        assert jobs.claim_job(db, "not-a-uuid") is None


def test_claim_next_job_oldest_first_empty_none(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    eng, Session = _sqlite_job_db()
    with Session(eng) as db:
        assert jobs.claim_next_job(db) is None
        a = _queued_job(db)
        b = _queued_job(db)
        claimed = jobs.claim_next_job(db)
        assert claimed is not None and claimed.id == a.id
        assert jobs.claim_next_job(db).id == b.id
        assert jobs.claim_next_job(db) is None


def test_requeue_or_fail_retries_then_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    eng, Session = _sqlite_job_db()
    with Session(eng) as db:
        job = _queued_job(db)
        jobs.claim_job(db, job.id)  # attempts -> 1
        assert jobs.requeue_or_fail(db, job, ValueError("boom")) == "requeued"
        assert job.status == STATUS_QUEUED
        jobs.claim_job(db, job.id)  # attempts -> 2
        assert jobs.requeue_or_fail(db, job, ValueError("boom")) == "requeued"
        jobs.claim_job(db, job.id)  # attempts -> 3 == MAX
        assert jobs.requeue_or_fail(db, job, ValueError("boom")) == "failed"
        assert job.status == STATUS_FAILED
        assert "boom" in (job.error_message or "")
