"""P4-10-01: XLSX import — staging, preview, execute, idempotency."""

import io
import os

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.imports import service
from app.modules.imports.service import ImportValidationError
from app.modules.analytics.report_worker import generate_report_task

HEADERS = ["ВУЗ", "Вендор", "ПО", "Номер договора", "Подписание лицензии",
           "Срок лицензии", "Статус передачи", "ФИО менеджера",
           "Ответственные от ВУЗа", "Комментарий"]

MAPPING = {
    "ВУЗ": "university.name",
    "Вендор": "vendor.name",
    "ПО": "product.name",
    "Номер договора": "contract.contract_number",
    "Подписание лицензии": "license.signed_at",
    "Срок лицензии": "license.expires_at",
    "Статус передачи": "license.transfer_status",
    "ФИО менеджера": "responsible.full_name",
    "Ответственные от ВУЗа": "university_responsibles",
    "Комментарий": "license.comment",
}

GOOD_ROWS = [
    ["МГУ им. М.В. Ломоносова", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-01",
     "2026-01-15", "2027-01-15", "accepted", "Менеджеров Менеджер 1",
     "Иванов Иван; Петрова Анна", "первый импорт"],
    ["Новый ВУЗ", "Астра", "Astra Linux", "DOG-IMP-02",
     "15.02.2026", "15.02.2027", "transferred", "",
     "", ""],
]


def make_xlsx(headers, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def staging(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "STAGING_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def db(tmp_path):
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    with Session(eng) as session:
        yield session
    eng.dispose()


def _stage(content: bytes, filename: str = "import.xlsx") -> str:
    return service.stage_upload(filename, content)


# ------------------------------------------------------------------ preview


def test_preview_returns_headers_and_rows(staging, db):
    from app.models.catalog import University

    db.add(University(name="МГУ им. М.В. Ломоносова", city="Москва"))
    db.commit()
    file_id = _stage(make_xlsx(HEADERS, GOOD_ROWS))
    parsed = service.parse_preview(file_id)
    assert parsed["headers"] == HEADERS
    assert parsed["row_count"] == 2
    assert len(parsed["preview"]) == 2
    assert parsed["preview"][0]["ВУЗ"] == "МГУ им. М.В. Ломоносова"
    assert parsed["detected_sheet"]


def test_stage_rejects_non_xlsx(staging):
    with pytest.raises(ImportValidationError):
        _stage(b"data", "import.csv")
    with pytest.raises(ImportValidationError):
        _stage(b"", "import.xlsx")


# ------------------------------------------------------------------ execute


def test_execute_inserts_everything(staging, db):
    from app.models.catalog import Contract, License, University, Vendor

    file_id = _stage(make_xlsx(HEADERS, GOOD_ROWS))
    summary = service.execute_import(db, file_id, MAPPING)
    assert summary["inserted"] == 2, summary
    assert summary["errors"] == []
    assert db.execute(select(func.count()).select_from(University)).scalar() == 2
    assert db.execute(select(func.count()).select_from(Vendor)).scalar() == 2
    assert db.execute(select(func.count()).select_from(License)).scalar() == 2
    lic = db.execute(select(License)).scalars().first()
    assert lic.transfer_status_raw == "accepted"
    assert db.execute(
        select(Contract).filter_by(contract_number="DOG-IMP-01")
    ).scalar_one() is not None


def test_execute_fuzzy_matches_university(staging, db):
    from app.models.catalog import University

    db.add(University(name="МГУ им. М.В. Ломоносова", city="Москва"))
    db.commit()
    rows = [["МГУ", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-10",
             "2026-01-15", "2027-01-15", "accepted", "", "", ""]]
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, rows)), MAPPING)
    assert summary["inserted"] == 1, summary
    assert db.execute(select(func.count()).select_from(University)).scalar() == 1


def test_bad_rows_skipped_with_errors(staging, db):
    rows = [
        ["МГУ", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-20",
         "2026-01-15", "не дата", "accepted", "", "", ""],      # bad date
        ["МГУ", "РЕД СОФТ", "РЕД ОС", "",                      # no contract no
         "2026-01-15", "2027-01-15", "accepted", "", "", ""],
        ["МГУ", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-21",
         "2026-01-15", "2027-01-15", "flying", "", "", ""],     # bad status
        ["МГУ", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-22",
         "2026-01-15", "2027-01-15", "accepted", "", "", ""],   # good
    ]
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, rows)), MAPPING)
    assert summary["inserted"] == 1, summary
    assert len(summary["errors"]) == 3, summary
    assert {e["row"] for e in summary["errors"]} == {2, 3, 4}
    assert all(e["field"] and e["message"] and e["code"] for e in summary["errors"])
    assert {(e["field"], e["code"]) for e in summary["errors"]} == {
        ("license.expires_at", "INVALID_FORMAT"),
        ("contract.contract_number", "REQUIRED"),
        ("license.transfer_status", "INVALID_FORMAT"),
    }


def test_rerun_updates_instead_of_duplicating(staging, db):
    from app.models.catalog import License

    file_id = _stage(make_xlsx(HEADERS, GOOD_ROWS))
    first = service.execute_import(db, file_id, MAPPING)
    assert first["inserted"] == 2
    second = service.execute_import(db, file_id, MAPPING, update_existing=True)
    assert second["updated"] == 2 and second["inserted"] == 0, second
    assert db.execute(select(func.count()).select_from(License)).scalar() == 2


def test_dry_run_changes_nothing(staging, db):
    from app.models.catalog import University

    file_id = _stage(make_xlsx(HEADERS, GOOD_ROWS))
    summary = service.execute_import(db, file_id, MAPPING, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["inserted"] == 2
    assert db.execute(select(func.count()).select_from(University)).scalar() == 0


def test_unknown_mapping_rejected(staging, db):
    file_id = _stage(make_xlsx(HEADERS, GOOD_ROWS))
    with pytest.raises(ImportValidationError):
        service.execute_import(db, file_id, {**MAPPING, "ВУЗ2": "nope.field"})


# ------------------------------------------------------------------ API level


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "STAGING_DIR", str(tmp_path / "staging"))
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))

    from app.main import app
    from app.db import session as db_session
    old_bind = db_session.SessionLocal.kw["bind"]
    db_session.SessionLocal.configure(bind=eng)

    def _override_db():
        with Session(eng) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test", roles={"admin"})
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        db_session.SessionLocal.configure(bind=old_bind)
        eng.dispose()


def test_api_preview_execute_job_flow(client):
    content = make_xlsx(HEADERS, GOOD_ROWS)
    resp = client.post(
        "/api/v1/import/preview",
        files={"file": ("import.xlsx", content,
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["headers"] == HEADERS
    assert preview["row_count"] == 2
    assert preview["file_id"]

    resp = client.post("/api/v1/import/execute", json={
        "file_id": preview["file_id"],
        "mapping": MAPPING,
        "options": {"update_existing": True, "dry_run": False},
    })
    # P4-06-02: submit отвечает 202 + {job_id}, итог — polling GET jobs/{id}.
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert job_id

    resp = client.get(f"/api/v1/import/jobs/{job_id}")
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["type"] == "xlsx_import"
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["result"] is None

    # The HTTP request only enqueues.  The worker performs the business
    # import and then publishes the terminal status.
    assert generate_report_task(job_id) == "ready"
    job = client.get(f"/api/v1/import/jobs/{job_id}").json()
    assert job["status"] == "ready"
    assert job["progress"] == 100
    assert job["error"] is None
    assert job["result"]["inserted"] == 2, job["result"]
    assert job["result"]["errors"] == []

    # P4-10-02: скачиваемый XLSX-отчёт (Итог + Ошибки).
    resp = client.get(f"/api/v1/import/jobs/{job_id}/report")
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml.sheet" in resp.headers["content-type"]
    assert len(resp.content) > 0


def test_api_execute_idempotent_replay(client):
    """Повторный POST с тем же file+mapping+options — тот же job_id."""
    content = make_xlsx(HEADERS, GOOD_ROWS)
    resp = client.post(
        "/api/v1/import/preview",
        files={"file": ("import.xlsx", content,
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = {
        "file_id": resp.json()["file_id"],
        "mapping": MAPPING,
        "options": {"update_existing": True, "dry_run": False},
    }
    first = client.post("/api/v1/import/execute", json=body)
    second = client.post("/api/v1/import/execute", json=body)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]

    # Чужой job: curator имеет import.read, но job создан другим user_id.
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="stranger", roles={"curator"})
    try:
        resp = client.get(f"/api/v1/import/jobs/{first.json()['job_id']}")
        assert resp.status_code == 403, resp.text
        resp = client.get(f"/api/v1/import/jobs/{first.json()['job_id']}/report")
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id="test", roles={"admin"})


def test_api_job_status_not_found(client):
    resp = client.get("/api/v1/import/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    resp = client.get("/api/v1/import/jobs/not-a-uuid")
    assert resp.status_code == 404


def test_api_preview_rejects_csv(client):
    resp = client.post(
        "/api/v1/import/preview",
        files={"file": ("import.csv", b"a,b\n1,2", "text/csv")},
    )
    assert resp.status_code == 400


def test_openapi_contains_import_endpoints():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/import/preview" in paths
    assert "/api/v1/import/execute" in paths
    assert "/api/v1/import/jobs/{job_id}" in paths
    assert "/api/v1/import/jobs/{job_id}/report" in paths
