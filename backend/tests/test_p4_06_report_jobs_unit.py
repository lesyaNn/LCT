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
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.report_worker import build_worker_user


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
