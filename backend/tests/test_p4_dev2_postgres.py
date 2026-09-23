"""Real PostgreSQL job/query/concurrency tests; no SQLite/create_all fallback.

Only a dedicated disposable TEST_DATABASE_URL may be used: the shared test
helper resets its public schema. Not run against development/production data.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProduct, ITProgram, License, University, Vendor
from app.models.health_score import HealthScoreSnapshot
from app.models.interactions import UniversityProgram
from app.models.report_job import ReportJob
from app.modules.analytics import repository
from app.modules.analytics.integration import Selection, UnfilteredProvider, get_filter_provider
from app.modules.report_jobs import service
from app.modules.report_jobs.schemas import ReportRequest
from tests.p4_dev2_data import TODAY


@pytest.fixture()
def factory(tmp_path, monkeypatch):
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    monkeypatch.setenv("P4_REPORT_DIRECTORY", str(tmp_path / "reports"))
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


class TestRenderer:
    __test__ = False

    def validate(self, request):
        pass

    def render(self, db, request, selection, destination):
        # Transport fixture, NOT the JSON report exporter owned by Dev-1.
        destination.write_bytes(b'{"job_transport_fixture":true}')


def submit(factory, renderer=None):
    with factory() as db:
        return service.submit(
            db,
            ReportRequest(format="json"),
            CurrentUser(id="owner", roles={"admin"}),
            UnfilteredProvider(),
            renderer or TestRenderer(),
        ).id


def test_job_lifecycle_and_atomic_duplicate_claim(factory):
    job_id = submit(factory)
    runner = partial(
        service.run_job,
        session_factory=factory,
        provider=UnfilteredProvider(),
        renderer=TestRenderer(),
    )
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(runner, [job_id] * 10)) == 1
    with factory() as db:
        job = db.get(ReportJob, job_id)
        assert job.status == "ready" and job.progress == 100
        assert service.downloadable(job).read_bytes() == b'{"job_transport_fixture":true}'
        assert job.file_size > 0 and job.completed_at is not None
        assert (job.expires_at - job.completed_at).total_seconds() == 86400


def test_render_failure_rollback_sanitization_cleanup(factory):
    class Broken(TestRenderer):
        def render(self, db, request, selection, destination):
            destination.write_bytes(b"partial")
            raise RuntimeError("SECRET token and internal filesystem path")

    job_id = submit(factory)
    service.run_job(
        job_id, session_factory=factory, provider=UnfilteredProvider(), renderer=Broken()
    )
    with factory() as db:
        job = db.get(ReportJob, job_id)
        assert job.status == "failed"
        assert "SECRET" not in job.error_message
        assert not service.artifact_path(job, temporary=True).exists()
        assert service.describe(job).download_url is None


def test_expired_files_only_and_queue_recovery(factory):
    expired, retained = submit(factory), submit(factory)
    for job_id in (expired, retained):
        service.run_job(
            job_id, session_factory=factory, provider=UnfilteredProvider(), renderer=TestRenderer()
        )
    with factory() as db:
        job = db.get(ReportJob, expired)
        job.expires_at = service.utcnow() - timedelta(seconds=1)
        db.commit()
    assert service.cleanup_expired(session_factory=factory) == 1
    with factory() as db:
        assert not service.artifact_path(db.get(ReportJob, expired)).exists()
        assert service.downloadable(db.get(ReportJob, retained)).exists()


def test_repository_child_scope_and_last_snapshot_per_day(factory, monkeypatch):
    with factory() as db:
        uni, other = University(name="P4 test A"), University(name="P4 test B")
        direction, vendor = ITDirection(code="p4", name="ИТ"), Vendor(name="P4 Vendor")
        db.add_all([uni, other, direction, vendor])
        db.flush()
        program = ITProgram(direction_id=direction.id, name="P4 Program")
        product = ITProduct(vendor_id=vendor.id, name="P4 Product", version="1")
        db.add_all([program, product])
        db.flush()
        link = UniversityProgram(university_id=uni.id, program_id=program.id, status="active")
        allowed = License(
            university_id=uni.id,
            product_id=product.id,
            program_id=program.id,
            license_number="P4-A",
            signed_at=TODAY,
            expires_at=TODAY,
        )
        forbidden = License(
            university_id=other.id,
            product_id=product.id,
            program_id=program.id,
            license_number="P4-B",
            signed_at=TODAY,
            expires_at=TODAY,
        )
        db.add_all([link, allowed, forbidden])
        for university, score, hour in ((uni, 20, 1), (uni, 80, 2), (other, 10, 3)):
            db.add(
                HealthScoreSnapshot(
                    university_id=university.id,
                    score=score,
                    status="yellow",
                    calculated_at=datetime(2026, 9, 23, hour, tzinfo=timezone.utc),
                    period_day=TODAY,
                    trigger_event=f"test-{hour}",
                    breakdown={},
                    reasons=[],
                )
            )
        db.commit()
        monkeypatch.setattr(
            repository.health_cache,
            "get_cached",
            lambda uid: SimpleNamespace(score=80, status="yellow"),
        )
        selected = Selection(
            university_ids=[uni.id],
            program_ids=[program.id],
            university_program_ids=[],
            license_ids=[forbidden.id],
        )
        data = repository.load_data(db, selected, today=TODAY)
        assert data.links == [] and data.licenses == []
        assert data.existing_pairs == {(uni.id, program.id)}
        assert data.trend == [{"date": TODAY, "avg_score": 80.0}]
        selected.university_program_ids = [link.id]
        selected.license_ids = [allowed.id, forbidden.id]
        data = repository.load_data(db, selected, today=TODAY)
        assert [item.id for item in data.licenses] == [allowed.id]


def test_ten_report_requests_leave_api_responsive(factory, monkeypatch):
    release = threading.Event()
    started = threading.Condition()
    calls = []

    class BlockingRenderer(TestRenderer):
        def render(self, *args):
            with started:
                calls.append(1)
                started.notify_all()
            assert release.wait(20), "Test did not release renderer"
            super().render(*args)

    renderer = BlockingRenderer()
    real_runner = service.run_job
    monkeypatch.setattr(service, "run_job", partial(real_runner, session_factory=factory))
    saved = app.dependency_overrides.copy()

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides.update(
        {
            get_db: session,
            get_current_user: lambda: CurrentUser(id="admin", roles={"admin"}),
            get_filter_provider: UnfilteredProvider,
            service.get_renderer: lambda: renderer,
        }
    )
    try:
        with TestClient(app) as client, ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(client.post, "/api/v1/reports", json={"format": "json"})
                for _ in range(10)
            ]
            try:
                with started:
                    assert started.wait_for(lambda: len(calls) == 10, timeout=15)
                begin = time.perf_counter()
                assert client.get("/health").status_code == 200
                latency = time.perf_counter() - begin
                assert latency < 1, f"API blocked by report workers: {latency:.3f}s"
            finally:
                release.set()
            responses = [future.result() for future in futures]
            assert all(response.status_code == 202 for response in responses)
            ids = [response.json()["job_id"] for response in responses]
            assert len(set(ids)) == 10
            for job_id in ids:
                assert client.get(f"/api/v1/reports/{job_id}").json()["status"] == "ready"
    finally:
        release.set()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
