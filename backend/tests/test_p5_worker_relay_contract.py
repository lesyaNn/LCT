"""The production worker drains the audit outbox alongside report jobs.

The daily health-score snapshot that used to sit in front of the job loop was
removed with the health-score entity (migration 000029). Its import raised
``ModuleNotFoundError`` and, being inside the same ``try``, it skipped a whole
iteration of report processing between 00:00 and 00:04. The last test here
pins that a failure of the surrounding bookkeeping can no longer stop jobs.
"""

from app.modules.analytics import report_worker


def test_worker_once_runs_relay_and_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(report_worker, "run_audit_relay_once", lambda: calls.append("audit"))
    monkeypatch.setattr(report_worker, "run_worker_once", lambda: calls.append("jobs"))

    assert report_worker.main(["--once"]) == 0
    assert calls == ["audit", "jobs"]


def test_relay_failure_does_not_block_jobs(monkeypatch):
    calls = []

    def failed_relay():
        raise RuntimeError("audit sink unavailable")

    monkeypatch.setattr(report_worker, "run_audit_relay_once", failed_relay)
    monkeypatch.setattr(report_worker, "run_worker_once", lambda: calls.append("jobs"))

    assert report_worker.main(["--once"]) == 0
    assert calls == ["jobs"]


def test_job_iteration_always_runs_even_when_bookkeeping_fails(monkeypatch):
    """No stray import or side task may swallow a whole worker iteration.

    The bug this pins: the daily health-score snapshot import sat in the same
    ``try`` as the job loop, so its ``ModuleNotFoundError`` between 00:00 and
    00:04 skipped report processing entirely.
    """
    calls = []
    monkeypatch.setattr(report_worker, "run_audit_relay_once", lambda: None)
    monkeypatch.setattr(report_worker, "run_worker_once", lambda: calls.append("jobs"))

    source = (report_worker.__file__ or "")
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    # Comments may name the removed entity; code may not import it.
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "health_score.materialization" not in code
    assert "run_daily_snapshot_once" not in code

    assert report_worker.main(["--once"]) == 0
    assert calls == ["jobs"], "the job loop must run on every iteration"
