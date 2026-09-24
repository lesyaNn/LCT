"""The production worker drains the audit outbox alongside report jobs."""

from datetime import datetime, timezone

from app.modules.analytics import report_worker


class Midday(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 24, 12, tzinfo=tz or timezone.utc)


def test_worker_once_runs_relay_and_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(report_worker, "datetime", Midday)
    monkeypatch.setattr(report_worker, "run_audit_relay_once", lambda: calls.append("audit"))
    monkeypatch.setattr(report_worker, "run_worker_once", lambda: calls.append("jobs"))

    assert report_worker.main(["--once"]) == 0
    assert calls == ["audit", "jobs"]


def test_relay_failure_does_not_block_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(report_worker, "datetime", Midday)

    def failed_relay():
        raise RuntimeError("audit sink unavailable")

    monkeypatch.setattr(report_worker, "run_audit_relay_once", failed_relay)
    monkeypatch.setattr(report_worker, "run_worker_once", lambda: calls.append("jobs"))

    assert report_worker.main(["--once"]) == 0
    assert calls == ["jobs"]
