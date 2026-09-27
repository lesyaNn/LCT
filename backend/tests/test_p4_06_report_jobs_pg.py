"""P4-06-01 + P4-03-01 PostgreSQL E2E: jobs, worker, lifecycle, security.

Full flow per format (xlsx/pdf/json)::

    POST -> 202 {job_id, queued} -> poll GET -> ready -> download -> valid file

plus: real persisted ids (never fake), fresh-session worker, scope
surviving the background boundary, ownership RBAC, expiry (410),
path-tamper denial, failed-job sanitation, 24h cleanup, 10-way parallel
submit over a real HTTP server, and the 000018 down/up migration cycle.

Requires ``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped
otherwise). ``REPORTS_DIR`` points at ``tmp_path``; the canonical
``SessionLocal`` is patched to the test engine so the worker's fresh
session hits the same database (same-process wiring, real sessions).
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 (register ReportJob metadata)
from app.core.errors import register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.models.catalog import Contract, ITProduct, License, Responsible, University, UniversityResponsible, Vendor
from app.models.report_job import ReportJob
from app.modules.analytics import report_jobs as jobs
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.reports_router import router as reports_router
from app.modules.analytics.report_service import create_report_job
from app.modules.analytics.report_worker import generate_report_task
from app.schemas.common import ReportFormat

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def _admin() -> CurrentUser:
    return CurrentUser(id="admin-1", roles={"admin"})


@pytest.fixture()
def pg(tmp_path, monkeypatch):
    """Fresh PG schema (canonical migrations) + patched session factory."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    factory = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.db.session.SessionLocal", factory)
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    with Session(eng) as session:
        _seed(session)
        session.commit()
    yield eng, tmp_path
    eng.dispose()


def _seed(s: Session) -> dict:
    vendor = Vendor(id=uuid4(), name="Вендор Р")
    prod = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО Репортёр")
    uni_a = University(id=uuid4(), name="Альфа", created_at=_utc(2026, 2, 1))
    uni_b = University(id=uuid4(), name="Бета", created_at=_utc(2026, 3, 1))
    s.add_all([vendor, prod, uni_a, uni_b])
    s.flush()
    s.add_all(
        [
            License(
                id=uuid4(),
                university_id=uni_a.id,
                product_id=prod.id,
                contract_id=None,
                program_id=None,
                direction_id=None,
                license_number="RA-1",
                signed_at=date(2026, 2, 10),
                expires_at=date(2027, 2, 10),
                transfer_status_raw="accepted",
                comment="Комментарий Альфы",
            ),
            License(
                id=uuid4(),
                university_id=uni_b.id,
                product_id=prod.id,
                contract_id=None,
                program_id=None,
                direction_id=None,
                license_number="RB-1",
                signed_at=date(2026, 3, 10),
                expires_at=date(2027, 3, 10),
                transfer_status_raw="transferred",
                comment="Комментарий Беты",
            ),
        ]
    )
    return {"a": uni_a.id, "b": uni_b.id}


def _client(user: CurrentUser | None) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(reports_router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _session(eng) -> Session:
    return Session(eng)


def _poll_ready(client: TestClient, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        resp = client.get(f"/reports/{job_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} never finished: {last}")


def _ids(pg) -> dict:
    eng, _ = pg
    with _session(eng) as s:
        rows = s.execute(select(University)).scalars().all()
        return {u.name: u.id for u in rows}


# ------------------------------------------------------- P4-03-01 creation


def test_post_persists_real_queued_job_before_worker_runs(pg):
    eng, _ = pg
    req = ReportRequest(format="xlsx", columns=["university", "product"])
    admin = _admin()

    from app.modules.analytics.reports_router import create_report

    with _session(eng) as s:
        queued = create_report(req, db=s, user=admin)
    assert queued.status == "queued"
    job_id = queued.job_id
    uuid4_valid = str(job_id)
    assert len(uuid4_valid) == 36
    # P4-06-01: API only creates (no BackgroundTasks) — a FRESH session
    # still sees queued; the worker container owns execution.
    with _session(eng) as fresh:
        job = jobs.get_job(fresh, job_id)
        assert job is not None and job.id is not None
        assert str(job.id) == job_id
        assert job.status == "queued" and job.progress == 0
        assert job.format == "xlsx"
        assert job.columns == ["university", "product"]
        assert job.actor_sub == "admin-1" and job.actor_roles == ["admin"]
        assert job.effective_university_ids is None  # explicit global snapshot
        assert job.created_at.tzinfo is not None
        delta = job.expires_at - job.created_at
        assert timedelta(hours=23) < delta < timedelta(hours=25)
        assert job.expires_at.tzinfo is not None


def test_post_xlsx_returns_202_with_persisted_id(pg):
    eng, tmp = pg
    client = _client(_admin())
    resp = client.post(
        "/reports",
        json={"format": "xlsx", "columns": ["university", "product"]},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    with _session(eng) as s:
        assert jobs.get_job(s, body["job_id"]) is not None


# ------------------------------------------------------- full lifecycle per format


def test_xlsx_e2e_ready_download_valid_workbook(pg):
    eng, tmp = pg
    ids = _ids(pg)
    client = _client(_admin())
    resp = client.post(
        "/reports",
        json={
            "format": "xlsx",
            "filters": {"university_ids": [str(ids["Альфа"])]},
            "columns": ["university", "product"],
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    # P4-06-01: API only creates; drive the worker explicitly.
    assert generate_report_task(job_id) == "ready"

    status = _poll_ready(client, job_id)
    assert status["status"] == "ready"
    assert status["progress"] == 100
    assert status["file_size"] and status["file_size"] > 0
    assert "file_path" not in status
    assert status["started_at"] and status["completed_at"]

    dl = client.get(f"/reports/{job_id}/download")
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert dl.headers["content-disposition"].startswith("attachment")
    assert f"report_{job_id}.xlsx" in dl.headers["content-disposition"]

    from openpyxl import load_workbook

    path = tmp / "reports" / f"report_{job_id}.xlsx"
    path.write_bytes(dl.content)
    ws = load_workbook(path)["Отчёт"]
    assert ws.cell(row=6, column=1).value == "Наименование ВУЗа"
    data = [
        (ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value)
        for r in (7, 8)
        if ws.cell(row=r, column=1).value is not None
    ]
    assert data == [("Альфа", "ПО Репортёр")]  # filter + scope respected


def test_xlsx_file_contains_linked_business_fields(pg):
    eng, tmp = pg
    ids = _ids(pg)
    with _session(eng) as s:
        license_row = s.scalar(select(License).where(License.university_id == ids["Альфа"]))
        contract = Contract(id=uuid4(), university_id=ids["Альфа"],
                            contract_number="C-REPORT-1", signed_at=date(2026, 2, 9),
                            product_id=license_row.product_id)
        person = Responsible(id=uuid4(), full_name="Менеджер Альфа",
                             email="report-manager@example.test", role="manager")
        s.add_all([contract, person])
        s.flush()
        license_row.contract_id = contract.id
        s.add(UniversityResponsible(id=uuid4(), university_id=ids["Альфа"],
                                    responsible_id=person.id, is_primary=True))
        s.commit()
    columns = ["university", "vendor", "contract_number",
               "license_signed", "license_expires", "transfer_status", "responsible", "comment"]
    client = _client(_admin())
    response = client.post("/reports", json={"format": "xlsx", "columns": columns,
                                           "filters": {"university_ids": [str(ids["Альфа"])]}})
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert generate_report_task(job_id) == "ready"
    from openpyxl import load_workbook

    path = tmp / "linked-business-report.xlsx"
    path.write_bytes(client.get(f"/reports/{job_id}/download").content)
    row = next(load_workbook(path, read_only=True)["Отчёт"].iter_rows(min_row=7, max_row=7, values_only=True))
    assert row[:4] == ("Альфа", "Вендор Р", "ПО Репортёр", "C-REPORT-1")
    assert (row[4].date(), row[5].date()) == (date(2026, 2, 10), date(2027, 2, 10))
    assert row[6:] == ("accepted", "Менеджер Альфа", "Комментарий Альфы")


def test_pdf_e2e_ready_download(pg):
    client = _client(_admin())
    resp = client.post("/reports", json={"format": "pdf", "columns": ["university"]})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    # P4-06-01: API only creates; drive the worker explicitly.
    assert generate_report_task(job_id) == "ready"
    status = _poll_ready(client, job_id)
    assert status["status"] == "ready"
    dl = client.get(f"/reports/{job_id}/download")
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"] == "application/pdf"
    assert dl.content[:5] == b"%PDF-"
    assert len(dl.content) > 0


def test_json_e2e_ready_download(pg):
    client = _client(_admin())
    resp = client.post(
        "/reports",
        json={"format": "json", "columns": ["university", "product"]},
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    # P4-06-01: API only creates; drive the worker explicitly.
    assert generate_report_task(job_id) == "ready"
    status = _poll_ready(client, job_id)
    assert status["status"] == "ready"
    dl = client.get(f"/reports/{job_id}/download")
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"] == "application/json"
    doc = json.loads(dl.content.decode("utf-8"))
    assert set(doc) == {"metadata", "filters", "columns", "rows", "totals"}
    assert [c["key"] for c in doc["columns"]] == ["university", "product"]
    assert doc["totals"]["row_count"] == 2 and len(doc["rows"]) == 2


# ------------------------------------------------------- worker lifecycle details


def test_worker_lifecycle_queued_building_ready(pg):
    eng, _ = pg
    with _session(eng) as s:
        job = create_report_job(
            s, ReportRequest(format="json"), _admin()
        )
        job_id = job.job_id
    with _session(eng) as s:
        assert jobs.get_job(s, job_id).status == "queued"
    assert generate_report_task(job_id) == "ready"
    with _session(eng) as s:
        done = jobs.get_job(s, job_id)
        assert done.status == "ready" and done.progress == 100
        assert done.file_size and done.file_size > 0
        assert done.started_at is not None and done.completed_at is not None
    # Idempotency: ready jobs are never regenerated.
    assert generate_report_task(job_id) == "already-ready"


def test_worker_never_restarts_building_job(pg):
    eng, _ = pg
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="json"), _admin()).job_id
        assert jobs.mark_building(s, jobs.get_job(s, job_id)) is True
    assert generate_report_task(job_id) == "already-building"
    with _session(eng) as s:
        assert jobs.get_job(s, job_id).status == "building"


def test_failed_job_sanitized_and_denied(pg, monkeypatch):
    eng, _ = pg
    from app.modules.analytics import report_service

    def _boom(db, filters, columns, output_path, **kw):
        raise RuntimeError("export exploded password=hunter2 token: abc")

    monkeypatch.setitem(
        report_service.FORMAT_GENERATORS, ReportFormat.XLSX, _boom
    )
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="xlsx"), _admin()).job_id
    assert generate_report_task(job_id) == "requeued"
    assert generate_report_task(job_id) == "requeued"
    assert generate_report_task(job_id) == "failed"
    with _session(eng) as s:
        job = jobs.get_job(s, job_id)
        assert job.status == "failed" and job.completed_at is not None
        assert "hunter2" not in (job.error_message or "")
        assert "Traceback" not in (job.error_message or "")
        assert job.error_message
    client = _client(_admin())
    assert client.get(f"/reports/{job_id}").json()["status"] == "failed"
    dl = client.get(f"/reports/{job_id}/download")
    assert dl.status_code == 400
    assert dl.json()["error"]["code"] == "REPORT_NOT_READY"


# ------------------------------------------------------- security snapshot


def test_scope_survives_background_boundary(pg):
    eng, tmp = pg
    ids = _ids(pg)
    scoped = CurrentUser(
        id="mgr-b", roles={"manager"}, university_ids=(str(ids["Бета"]),)
    )
    client = _client(scoped)
    resp = client.post(
        "/reports",
        json={
            "format": "xlsx",
            "filters": {
                "university_ids": [str(ids["Альфа"]), str(ids["Бета"])]
            },
            "columns": ["university"],
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    with _session(eng) as s:
        job = jobs.get_job(s, job_id)
        assert job.effective_university_ids == [str(ids["Бета"])]
    # P4-06-01: API only creates; drive the worker explicitly.
    assert generate_report_task(job_id) == "ready"
    status = _poll_ready(client, job_id)
    assert status["status"] == "ready"

    from openpyxl import load_workbook

    path = tmp / "reports" / f"report_{job_id}.xlsx"
    assert path.is_file()
    ws = load_workbook(path)["Отчёт"]
    names = [
        ws.cell(row=r, column=1).value
        for r in range(7, 12)
        if ws.cell(row=r, column=1).value is not None
    ]
    assert names == ["Бета"]  # foreign Альфа filtered by the saved scope


def test_empty_scope_fails_closed(pg):
    eng, tmp = pg
    scoped = CurrentUser(id="mgr-e", roles={"manager"}, university_ids=())
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="json"), scoped).job_id
    with _session(eng) as s:
        assert jobs.get_job(s, job_id).effective_university_ids == []
    assert generate_report_task(job_id) == "ready"
    doc = json.loads(
        (tmp / "reports" / f"report_{job_id}.json").read_text(encoding="utf-8")
    )
    assert doc["totals"]["row_count"] == 0 and doc["rows"] == []  # P4 JSON contract
    # The unscoped baseline really has data (the scope did the filtering).
    from app.modules.analytics.dataset import ReportDatasetService

    with _session(eng) as s:
        ds = ReportDatasetService.fetch_rows(s, UnifiedFilter(), ["university"])
        assert ds.total == 2


# ------------------------------------------------------- visibility RBAC


def test_own_job_access_matrix(pg):
    eng, _ = pg
    owner = CurrentUser(id="mgr-a", roles={"manager"})
    other_manager = CurrentUser(id="mgr-b", roles={"manager"})
    stranger = CurrentUser(id="user-c", roles={"user"})
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="xlsx"), owner).job_id
    assert _client(owner).get(f"/reports/{job_id}").status_code == 200
    # P4-06-01 RBAC: manager/admin видят все jobs, остальные — только свои.
    assert _client(other_manager).get(f"/reports/{job_id}").status_code == 200
    assert _client(stranger).get(f"/reports/{job_id}").status_code == 403
    assert _client(_admin()).get(f"/reports/{job_id}").status_code == 200
    assert _client(owner).get(f"/reports/{uuid4()}").status_code == 404
    assert _client(owner).get("/reports/not-a-uuid").status_code == 404
    pending = _client(owner).get(f"/reports/{job_id}/download")
    assert pending.status_code == 400
    assert pending.json()["error"]["code"] == "REPORT_NOT_READY"


def test_list_jobs_is_paged_and_excludes_imports(pg):
    eng, _ = pg
    owner = CurrentUser(id="mgr-a", roles={"manager"})
    stranger = CurrentUser(id="user-c", roles={"user"})
    with _session(eng) as s:
        first = create_report_job(s, ReportRequest(format="xlsx"), owner).job_id
        second = create_report_job(s, ReportRequest(format="pdf"), owner).job_id
        foreign = create_report_job(s, ReportRequest(format="json"), stranger).job_id
        import_job = s.get(ReportJob, first)
        import_job.job_type = "xlsx_import"
        s.commit()
    manager_result = _client(owner).get("/reports?page=1&page_size=1")
    assert manager_result.status_code == 200, manager_result.text
    assert manager_result.json()["total"] == 2
    assert len(manager_result.json()["items"]) == 1
    assert _client(owner).get("/reports?page=2&page_size=1").json()["items"][0]["id"] in {second, foreign}
    user_result = _client(stranger).get("/reports")
    assert user_result.status_code == 200
    assert [item["id"] for item in user_result.json()["items"]] == [foreign]
    assert _client(_admin()).get("/reports").json()["total"] == 2
    assert _client(owner).get("/reports?page_size=101").status_code == 422


# ------------------------------------------------------- download states


def test_download_not_ready_is_controlled(pg):
    eng, _ = pg
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="xlsx"), _admin()).job_id
    client = _client(_admin())
    queued = client.get(f"/reports/{job_id}/download")
    assert queued.status_code == 400
    assert queued.json()["error"]["code"] == "REPORT_NOT_READY"
    with _session(eng) as s:
        job = jobs.get_job(s, job_id)
        assert jobs.mark_building(s, job) is True
    building = client.get(f"/reports/{job_id}/download")
    assert building.status_code == 400
    assert building.json()["error"]["code"] == "REPORT_NOT_READY"


def test_download_expired_is_gone(pg):
    eng, _ = pg
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="xlsx"), _admin()).job_id
    assert generate_report_task(job_id) == "ready"
    with _session(eng) as s:
        job = jobs.get_job(s, job_id)
        job.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.add(job)
        s.commit()
    client = _client(_admin())
    assert client.get(f"/reports/{job_id}").status_code == 200
    assert client.get(f"/reports/{job_id}/download").status_code == 410


def test_download_path_tamper_denied(pg, tmp_path):
    eng, _ = pg
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="xlsx"), _admin()).job_id
    assert generate_report_task(job_id) == "ready"
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"top-secret")
    client = _client(_admin())
    with _session(eng) as s:
        job = jobs.get_job(s, job_id)
        for evil in (
            "/etc/passwd",
            str(secret),
            str(tmp_path / "reports" / ".." / "secret.txt"),
        ):
            job.file_path = evil
            s.add(job)
            s.commit()
            resp = client.get(f"/reports/{job_id}/download")
            assert resp.status_code == 404, evil
            assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"
            assert b"top-secret" not in resp.content


# ------------------------------------------------------- 24h cleanup


def test_cleanup_expired_report_jobs(pg):
    eng, tmp = pg
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with _session(eng) as s:
        ready_id = create_report_job(s, ReportRequest(format="xlsx"), _admin()).job_id
    assert generate_report_task(ready_id) == "ready"
    with _session(eng) as s:
        fresh_id = create_report_job(s, ReportRequest(format="json"), _admin()).job_id
        stale_queued_id = create_report_job(
            s, ReportRequest(format="json"), _admin()
        ).job_id
        for jid, exp in ((ready_id, past), (stale_queued_id, past)):
            job = jobs.get_job(s, jid)
            job.expires_at = exp
            s.add(job)
        s.commit()
    reports_dir = tmp / "reports"
    assert (reports_dir / f"report_{ready_id}.xlsx").is_file()
    with _session(eng) as s:
        result = jobs.cleanup_expired_report_jobs(s)
    assert result["files_removed"] >= 1
    assert result["jobs_failed"] == 1
    assert not (reports_dir / f"report_{ready_id}.xlsx").exists()
    with _session(eng) as s:
        ready = jobs.get_job(s, ready_id)
        assert ready.status == "ready" and ready.file_path is None
        stale = jobs.get_job(s, stale_queued_id)
        assert stale.status == "failed"
        fresh = jobs.get_job(s, fresh_id)
        assert fresh.status == "queued" and fresh.file_path is None
    # Deployment entry (own session) works too.
    with _session(eng) as s:
        assert jobs.run_cleanup_once() == {
            "files_removed": 0,
            "jobs_failed": 0,
            "jobs_cleared": 0,
        }


def test_cleanup_never_touches_foreign_paths(pg, tmp_path):
    eng, _ = pg
    outside = tmp_path / "foreign.txt"
    outside.write_bytes(b"not-ours")
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with _session(eng) as s:
        job_id = create_report_job(s, ReportRequest(format="json"), _admin()).job_id
        job = jobs.get_job(s, job_id)
        job.status = "ready"
        job.file_path = str(outside)
        job.expires_at = past
        s.add(job)
        s.commit()
    with _session(eng) as s:
        jobs.cleanup_expired_report_jobs(s)
    assert outside.read_bytes() == b"not-ours"  # чужой файл нетронут


# ------------------------------------------------------- parallel submit


def test_parallel_submit_does_not_wait_for_generation(pg, monkeypatch):
    # P4-06-01: API only creates jobs — no BackgroundTasks scheduling at
    # all, so every submit is fast by construction (no slow-worker mock
    # needed); the worker container owns execution.
    import httpx
    import uvicorn

    eng, _ = pg

    import socket as _socket

    # L16: ephemeral port instead of fixed 18001 (parallel runs / CI
    # workers must not collide on a hardcoded port).
    with _socket.socket() as _s:
        _s.bind(("127.0.0.1", 0))
        _port = _s.getsockname()[1]
    _base = f"http://127.0.0.1:{_port}"
    app = FastAPI()
    app.include_router(reports_router)
    app.dependency_overrides[get_current_user] = _admin
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=_port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                httpx.get(f"{_base}/openapi.json", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        latencies: list[float] = []
        statuses: list[int] = []
        bodies: list[dict] = []

        def _one() -> None:
            started = time.monotonic()
            resp = httpx.post(
                f"{_base}/reports",
                json={"format": "xlsx", "columns": ["university"]},
                timeout=20,
            )
            latencies.append(time.monotonic() - started)
            statuses.append(resp.status_code)
            bodies.append(resp.json())

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda _: _one(), range(10)))
    finally:
        server.should_exit = True
        thread.join(timeout=15)

    assert statuses == [202] * 10  # every submit accepted immediately
    assert max(latencies) < 2.5, latencies  # nobody waited for the 3s worker
    ids = [b["job_id"] for b in bodies]
    assert len(set(ids)) == 10
    with _session(eng) as s:
        for job_id in ids:
            job = jobs.get_job(s, job_id)
            assert job is not None and job.status == "queued"


# ------------------------------------------------------- migration cycle


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL=postgresql..."
)
def test_report_jobs_migration_down_up_cycle(pg):
    import subprocess

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    eng, _ = pg
    down = subprocess.run(
        ["python", "scripts/migrate.py", "down", "--to", "000017_tasks_priority", "--yes"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert down.returncode == 0, down.stdout + down.stderr
    check = create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        assert "report_jobs" not in inspect(check).get_table_names()
    finally:
        check.dispose()
    up = subprocess.run(
        ["python", "scripts/migrate.py", "up"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert up.returncode == 0, up.stdout + up.stderr
    verify = create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        assert "report_jobs" in inspect(verify).get_table_names()
        cols = {c["name"] for c in inspect(verify).get_columns("report_jobs")}
        assert {
            "id",
            "format",
            "filters",
            "columns",
            "actor_sub",
            "actor_roles",
            "effective_university_ids",
            "status",
            "progress",
            "file_path",
            "file_size",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
            "expires_at",
        } <= cols
    finally:
        verify.dispose()


def test_migration_chain_latest_is_report_jobs():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sql_migrate",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts",
            "migrate.py",
        ),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    versions = [v for v, _, _ in module._discover()]
    assert versions[-1] == "000034_report_templates_xls_format"
    assert "000033_product_program" in versions
    assert len(versions) == 34
    assert "report_jobs" in module.EXPECTED_TABLES
    assert module.EXPECTED_TABLES[-1] == "report_templates"


def test_report_job_model_matches_migration_columns():
    # 000018 core + 000019 Dev-3 import extension + 000020 attempts.
    assert set(ReportJob.__table__.columns.keys()) == {        "id",
        "format",
        "filters",
        "columns",
        "actor_sub",
        "actor_name",
        "actor_roles",
        "effective_university_ids",
        "status",
        "progress",
        "attempts",
        "job_type",
        "payload",
        "result",
        "idempotency_key",
        "file_path",
        "file_size",
        "error_message",
        "created_at",
        "started_at",
        "completed_at",
        "expires_at",
    }


def test_export_row_count_matches_preview_for_the_whole_column_registry(pg):
    """A report must contain every row the preview counts, for ANY column set.

    Regression: with the full registry the export came back with zero data rows
    while the preview for the very same request reported 6 — the discrepancy
    only appeared once ``overdue_tasks`` (and the other ``needs_university_maps``
    columns) joined the selection, so no test that used the 5-column default
    could see it.
    """
    from openpyxl import load_workbook

    from app.modules.analytics.columns import COLUMN_REGISTRY

    eng, tmp = pg
    client = _client(_admin())
    columns = sorted(COLUMN_REGISTRY)
    filters = {}

    preview = client.post(
        "/reports/preview", json={"format": "xlsx", "filters": filters, "columns": columns}
    )
    assert preview.status_code == 200, preview.text
    expected = preview.json()["total"]
    assert expected > 0, "seed should produce report rows"

    resp = client.post(
        "/reports",
        json={"format": "xlsx", "filters": filters, "columns": columns},
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert generate_report_task(job_id) == "ready"

    dl = client.get(f"/reports/{job_id}/download")
    assert dl.status_code == 200, dl.text
    ws = load_workbook(tmp / "reports" / f"report_{job_id}.xlsx")["Отчёт"]
    data_rows = [
        r
        for r in range(7, ws.max_row + 1)
        if any(ws.cell(row=r, column=c).value not in (None, "") for c in range(1, ws.max_column + 1))
    ]
    assert len(data_rows) == expected, (
        f"preview counted {expected} rows, export wrote {len(data_rows)}"
    )


def test_artifact_stamped_with_an_older_cache_version_is_not_reused(pg):
    """A ready artifact from older code must not be served to a new job.

    Regression: ``REPORT_CACHE_VERSION`` was not bumped after the analytics
    rework, so a 0-row workbook generated by the previous code stayed eligible
    and was copied onto fresh jobs for up to 24h — the preview showed 6 rows
    while the download was empty.

    The lookup mirrors ``report_worker`` exactly (normalized filters + resolved
    columns + ``exclude_id``), so the *only* reason for the final miss is the
    version stamp.
    """
    from app.modules.analytics.filters import UnifiedFilter
    from app.modules.analytics.report_request import ReportRequest

    eng, tmp = pg
    client = _client(_admin())
    filters = {"university_ids": [str(_ids(pg)["Альфа"])]}
    columns = ["university", "product"]
    body = {"format": "xlsx", "filters": filters, "columns": columns}

    donor = client.post("/reports", json=body).json()["job_id"]
    assert generate_report_task(donor) == "ready"
    consumer = client.post("/reports", json=body).json()["job_id"]

    with _session(eng) as s:
        c = s.get(ReportJob, UUID(consumer))
        lookup = dict(
            format=c.format,
            filters=UnifiedFilter.model_validate(c.filters or {}).model_dump(mode="json"),
            columns=ReportRequest(
                format=c.format,
                filters=UnifiedFilter.model_validate(c.filters or {}),
                columns=c.columns,
            ).resolved_columns,
            actor_sub=c.actor_sub or "",
            exclude_id=c.id,
        )
        d = s.get(ReportJob, UUID(donor))
        assert d.result.get("cache_version") == jobs.REPORT_CACHE_VERSION
        # Sanity: identical params + current version => the donor is reusable.
        assert jobs.find_ready_reusable(_session(eng), **lookup) is not None
        # Now pretend the donor was produced by an older generator.
        d.result = {**d.result, "cache_version": jobs.REPORT_CACHE_VERSION - 1}
        s.commit()

    assert jobs.find_ready_reusable(_session(eng), **lookup) is None
