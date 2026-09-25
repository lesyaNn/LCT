"""P4-10-01: XLSX import — staging, preview, execute, idempotency."""

import io
import os
from pathlib import Path

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
     "2026-01-15", "2027-01-15", "accepted", "",
     "", "первый импорт"],
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


def test_execute_does_not_fuzzy_merge_different_universities(staging, db):
    from app.models.catalog import University

    db.add(University(name="МГУ им. М.В. Ломоносова", city="Москва"))
    db.commit()
    rows = [["МГУ", "РЕД СОФТ", "РЕД ОС", "DOG-IMP-10",
             "2026-01-15", "2027-01-15", "accepted", "", "", ""]]
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, rows)), MAPPING)
    assert summary["inserted"] == 1, summary
    assert db.execute(select(func.count()).select_from(University)).scalar() == 2


def test_mapping_contract_uses_backend_fields_and_aliases():
    contract = service.mapping_contract(["\ufeff Название ВУЗа ", "Вендор", "ПО", "Неизвестно"], "products")
    assert contract["suggested_mapping"] == {"Вендор": "vendor.name", "ПО": "product.name"}
    assert {field["id"] for field in contract["target_fields"]} == set(service.IMPORT_FIELDS_BY_TYPE["products"])
    with pytest.raises(ImportValidationError):
        service.validate_mapping(["Вендор", "ПО"], {"Вендор": "vendor.name", "ПО": "vendor.name"}, "products")


def test_repository_example_headers_map_without_inventing_license_dates(staging, db):
    example = Path(__file__).resolve().parents[2] / "docs" / "import-example-20.xlsx"
    file_id = _stage(example.read_bytes())
    preview = service.parse_preview(file_id)
    assert preview["row_count"] == 20
    mapping = service.mapping_contract(preview["headers"], "licenses")["suggested_mapping"]
    assert mapping["Срок действия лицензии (год)"] == "license.expires_at"
    assert mapping["Статус по передачи"] == "license.transfer_status"
    summary = service.execute_import(db, file_id, mapping, dry_run=True, catalog_type="licenses")
    assert summary["total_rows"] == 20
    assert summary["errors_total"] == 20
    assert all(item["field"] == "license.expires_at" for item in summary["errors"])


def test_year_only_license_date_is_unresolved_not_invented(staging, db):
    row = list(GOOD_ROWS[0])
    row[5] = "2027"
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, [row])), MAPPING)
    assert summary["inserted"] == 0
    assert summary["errors"][0]["field"] == "license.expires_at"
    assert summary["errors"][0]["source_field"] == "Срок лицензии"
    assert "полную дату" in summary["errors"][0]["message"]


def test_blank_optional_cells_preserve_existing_data(staging, db):
    from app.models.catalog import Contract, License, Responsible

    first = service.execute_import(db, _stage(make_xlsx(HEADERS, [GOOD_ROWS[0]])), MAPPING)
    assert first["inserted"] == 1
    update_row = list(GOOD_ROWS[0])
    update_row[6] = ""
    update_row[9] = ""
    second = service.execute_import(db, _stage(make_xlsx(HEADERS, [update_row])), MAPPING)
    assert second["updated"] == 1
    assert db.scalar(select(License)).comment == "первый импорт"
    assert db.scalar(select(License)).transfer_status_raw == "accepted"
    assert db.scalar(select(Contract)).comment == "первый импорт"

    fields = ["ФИО", "Почта", "Телефон", "Роль"]
    mapping = {"ФИО": "responsible.full_name", "Почта": "responsible.email", "Телефон": "responsible.phone", "Роль": "responsible.role"}
    file_id = _stage(make_xlsx(fields, [["Иван Иванов", "ivan@example.test", "89001234567", "Менеджер"]]))
    assert service.execute_import(db, file_id, mapping, catalog_type="responsibles")["inserted"] == 1
    blank_id = _stage(make_xlsx(fields, [["Иван Петров", "ivan@example.test", "", ""]]))
    assert service.execute_import(db, blank_id, mapping, catalog_type="responsibles")["updated"] == 1
    person = db.scalar(select(Responsible))
    assert (person.full_name, person.phone, person.role) == ("Иван Петров", "+79001234567", "Менеджер")


def test_upload_rejects_spoofed_xlsx_and_duplicate_headers(staging):
    with pytest.raises(ImportValidationError, match="не соответствует XLSX"):
        _stage(b"not an Excel archive", "spoof.xlsx")
    file_id = _stage(make_xlsx(["ВУЗ", " вуз "], [["A", "B"]]))
    with pytest.raises(ImportValidationError, match="повторяются"):
        service.parse_preview(file_id)


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


@pytest.mark.parametrize("catalog_type, headers, values, mapping, model", [
    ("universities", ["ВУЗ", "Город"], ["Новый университет", "Казань"],
     {"ВУЗ": "university.name", "Город": "university.city"}, "University"),
    ("directions", ["Код", "Направление"], ["AI", "Искусственный интеллект"],
     {"Код": "direction.code", "Направление": "direction.name"}, "ITDirection"),
    ("responsibles", ["ФИО", "Почта", "Телефон"], ["Тестовый Иван", "TEST@example.ru", 89001234567],
     {"ФИО": "responsible.full_name", "Почта": "responsible.email", "Телефон": "responsible.phone"}, "Responsible"),
    ("products", ["Компания", "Продукт"], ["Тестовый вендор", "«Продукт А», «Продукт Б»"],
     {"Компания": "vendor.name", "Продукт": "product.name"}, "ITProduct"),
])
def test_catalog_import_is_idempotent(staging, db, catalog_type, headers, values, mapping, model):
    from app import models

    file_id = _stage(make_xlsx(headers, [values]))
    first = service.execute_import(db, file_id, mapping, catalog_type=catalog_type)
    second = service.execute_import(db, file_id, mapping, catalog_type=catalog_type)
    assert first["inserted"] == 1 and not first["errors"], first
    assert second["skipped"] == 1 and not second["errors"], second
    expected = 2 if catalog_type == "products" else 1
    assert db.scalar(select(func.count()).select_from(getattr(models, model))) == expected


def test_vendor_contacts_import_preserves_product_relations(staging, db):
    from app.models.catalog import ITProduct, Vendor, VendorContact

    headers = ["Компания", "Продукт", "ФИО", "Телефон", "Почта", "Способ связи"]
    mapping = {
        "Компания": "vendor.name", "Продукт": "product.name",
        "ФИО": "vendor_contact.full_name", "Телефон": "vendor_contact.phone",
        "Почта": "vendor_contact.email", "Способ связи": "vendor_contact.communication_method",
    }
    rows = [["Тестовый вендор", "«Продукт А», «Продукт Б»", "Иван Иванов", 89001234567,
             "contact@example.ru", "Chat TG"]]
    file_id = _stage(make_xlsx(headers, rows))
    dry = service.execute_import(db, file_id, mapping, dry_run=True, catalog_type="vendor_contacts")
    assert dry["inserted"] == 1 and not dry["errors"], dry
    assert db.scalar(select(func.count()).select_from(Vendor)) == 0
    first = service.execute_import(db, file_id, mapping, catalog_type="vendor_contacts")
    second = service.execute_import(db, file_id, mapping, catalog_type="vendor_contacts")
    assert first["inserted"] == 1 and second["skipped"] == 1
    assert db.scalar(select(func.count()).select_from(ITProduct)) == 2
    assert db.scalar(select(func.count()).select_from(VendorContact)) == 2
    assert {item.phone for item in db.scalars(select(VendorContact))} == {"+79001234567"}


def test_license_import_reports_unresolved_manager_without_fake_contact(staging, db):
    from app.models.catalog import Responsible

    row = list(GOOD_ROWS[0])
    row[7] = "Неизвестный Менеджер"
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, [row])), MAPPING)
    assert summary["inserted"] == 0
    assert summary["errors"][0]["field"] == "responsible.full_name"
    assert summary["errors"][0]["code"] == "NOT_FOUND"
    assert db.scalar(select(func.count()).select_from(Responsible)) == 0


def test_license_import_rejects_contract_from_another_university(staging, db):
    rows = [list(GOOD_ROWS[0]), list(GOOD_ROWS[0])]
    rows[1][0] = "Другой ВУЗ"
    summary = service.execute_import(db, _stage(make_xlsx(HEADERS, rows)), MAPPING)
    assert summary["inserted"] == 1
    assert summary["errors"][0]["field"] == "contract.contract_number"
    assert summary["errors"][0]["code"] == "DUPLICATE"


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
        "filename": "import.xlsx",
        "catalog_type": "licenses",
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
    assert job["filename"] == "import.xlsx"
    assert job["catalog_type"] == "licenses"
    journal = client.get("/api/v1/import/jobs")
    assert journal.status_code == 200, journal.text
    assert [entry["id"] for entry in journal.json()] == [job_id]

    # The HTTP request only enqueues.  The worker performs the business
    # import and then publishes the terminal status.
    assert generate_report_task(job_id) == "ready"
    job = client.get(f"/api/v1/import/jobs/{job_id}").json()
    assert job["status"] == "ready"
    assert job["progress"] == 100
    assert job["error"] is None
    assert job["result"]["inserted"] == 2, job["result"]
    assert job["result"]["errors"] == []
    assert job["error_report_url"] == f"/api/v1/import/jobs/{job_id}/report"

    # P4-10-02: скачиваемый XLSX-отчёт (Итог + Ошибки).
    resp = client.get(f"/api/v1/import/jobs/{job_id}/report")
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml.sheet" in resp.headers["content-type"]
    assert len(resp.content) > 0


@pytest.mark.parametrize("catalog_type,headers,values,mapping,catalog_path,expected_name", [
    ("universities", ["ВУЗ", "Город"], ["Интеграционный университет", "Томск"],
     {"ВУЗ": "university.name", "Город": "university.city"},
     "/api/v1/universities", "Интеграционный университет"),
    ("products", ["Компания", "Продукт"], ["Интеграционный вендор", "Интеграционный продукт"],
     {"Компания": "vendor.name", "Продукт": "product.name"},
     "/api/v1/products", "Интеграционный продукт"),
    ("directions", ["Код", "Направление"], ["IMPORT-IT", "Интеграционное направление"],
     {"Код": "direction.code", "Направление": "direction.name"},
     "/api/v1/directions", "Интеграционное направление"),
    ("responsibles", ["ФИО", "Почта"], ["Интеграционный Ответственный", "integration@example.test"],
     {"ФИО": "responsible.full_name", "Почта": "responsible.email"},
     "/api/v1/responsibles", "Интеграционный Ответственный"),
])
def test_api_four_catalogs_dry_run_execute_and_repeat(
    client, catalog_type, headers, values, mapping, catalog_path, expected_name,
):
    content = make_xlsx(headers, [values])
    preview_response = client.post(
        "/api/v1/import/preview", data={"catalog_type": catalog_type},
        files={"file": ("catalog.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["row_count"] == 1
    assert preview["suggested_mapping"] == mapping
    assert preview["target_fields"]
    assert set(preview["required_fields"]) <= set(mapping.values())

    before = client.get(catalog_path)
    assert before.status_code == 200, before.text
    assert before.json()["total"] == 0

    base = {"file_id": preview["file_id"], "catalog_type": catalog_type, "mapping": mapping,
            "options": {"update_existing": True, "dry_run": True}}
    dry_response = client.post("/api/v1/import/execute", json=base)
    assert dry_response.status_code == 202, dry_response.text
    dry_id = dry_response.json()["job_id"]
    assert generate_report_task(dry_id) == "ready"
    dry_job = client.get(f"/api/v1/import/jobs/{dry_id}").json()
    assert dry_job["dry_run"] is True
    assert dry_job["result"]["inserted"] == 1
    assert dry_job["result"]["errors"] == []
    assert client.get(catalog_path).json()["total"] == 0

    real_response = client.post("/api/v1/import/execute", json={
        **base, "options": {"update_existing": True, "dry_run": False},
    })
    assert real_response.status_code == 202, real_response.text
    real_id = real_response.json()["job_id"]
    assert real_id != dry_id
    assert generate_report_task(real_id) == "ready"
    real_job = client.get(f"/api/v1/import/jobs/{real_id}").json()
    assert real_job["result"]["inserted"] == 1
    after = client.get(catalog_path)
    assert after.status_code == 200, after.text
    assert after.json()["total"] == 1
    assert expected_name in str(after.json()["items"])

    # A new upload produces a new job; natural keys prevent a duplicate.
    again = client.post(
        "/api/v1/import/preview", data={"catalog_type": catalog_type},
        files={"file": ("catalog.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    repeat = client.post("/api/v1/import/execute", json={
        **base, "file_id": again["file_id"], "options": {"update_existing": True, "dry_run": False},
    })
    assert repeat.status_code == 202, repeat.text
    assert generate_report_task(repeat.json()["job_id"]) == "ready"
    assert client.get(catalog_path).json()["total"] == 1
    assert client.get(f"/api/v1/import/jobs/{repeat.json()['job_id']}").json()["result"]["skipped"] == 1


def test_import_permissions_user_manager_admin(client):
    from app.main import app

    content = make_xlsx(["ВУЗ"], [["Разрешения: тестовый ВУЗ"]])
    for role, expected in (("user", 403), ("manager", 200), ("admin", 200)):
        app.dependency_overrides[get_current_user] = lambda role=role: CurrentUser(id=role, roles={role})
        preview = client.post(
            "/api/v1/import/preview", data={"catalog_type": "universities"},
            files={"file": ("roles.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert preview.status_code == expected, preview.text
        assert client.get("/api/v1/import/jobs").status_code == 200
        if expected == 200:
            submit = client.post("/api/v1/import/execute", json={
                "file_id": preview.json()["file_id"], "catalog_type": "universities",
                "mapping": {"ВУЗ": "university.name"},
                "options": {"update_existing": True, "dry_run": True},
            })
            assert submit.status_code == 202, submit.text


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
