"""Stage 11 contract: explicit mock, exact-ID dedup and atomic Workflow."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import settings
from app.core.errors import BusinessException
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProgram, University
from app.models.external import ExternalApplication
from app.models.interactions import Student, UniversityProgram
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.integrations import service
from app.modules.imports import service as import_service


@pytest.fixture()
def engine():
    from tests.db_helpers import require_pg_engine

    db_engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    old_mode = settings.external_adapter_mode
    old_env = settings.app_env
    settings.external_adapter_mode = "mock"
    settings.app_env = "test"
    try:
        yield db_engine
    finally:
        settings.external_adapter_mode = old_mode
        settings.app_env = old_env
        db_engine.dispose()


def seed(engine):
    with Session(engine) as db:
        university = University(name="Stage11 university", city="Москва")
        direction = ITDirection(code="stage11", name="Stage11 direction")
        template = WorkflowTemplate(name="Stage11 template")
        db.add_all([university, direction, template])
        db.flush()
        program = ITProgram(direction_id=direction.id, name="Stage11 program")
        db.add(program)
        db.flush()
        db.add(UniversityProgram(university_id=university.id, program_id=program.id))
        db.add(WorkflowStage(template_id=template.id, name="Start", order_index=1))
        db.commit()
        return university.id, program.id


def test_mock_sync_read_metrics_and_exact_id_dedup(engine):
    university_id, program_id = seed(engine)
    with Session(engine) as db:
        lms = service.sync_mock(db, university_id, "lms")
        website = service.sync_mock(db, university_id, "website")
        assert lms["processed"] == website["processed"] == 1
        assert service.sync_mock(db, university_id, "website")["processed"] == 1
        students = service.university_data(db, university_id, "lms")
        applications = service.university_data(db, university_id, "website")
        assert students["students"][0]["progress"] is None
        assert students["students"][0]["source"] == "lms"
        assert students["synced_at"] is not None
        assert applications["applications"][0]["applications_count"] == 1
        assert applications["applications"][0]["program_id"] == program_id
        assert applications["applications"][0]["demand_score"] is None
        assert service.metrics(db)["lms_students"] == 1
        assert service.metrics(db)["website_applications_7d"] == 1
        scoped_out = service.metrics(db, CurrentUser(id="outside", roles={"user"}, university_ids=()))
        assert scoped_out["lms_students"] is None and scoped_out["website_applications_7d"] is None
        external_id = applications["applications"][0]["id"]
        service.upsert_application(db, {
            "external_id": external_id, "university_id": university_id,
            "program_id": program_id, "status": "updated",
            "external_created_at": datetime.now(timezone.utc),
        }, ingest_channel="file", synced_at=datetime.now(timezone.utc))
        db.commit()
        assert db.scalar(select(func.count(ExternalApplication.id))) == 1
        assert db.scalar(select(ExternalApplication.ingest_channel)) == "file"
        assert db.scalar(select(func.count(Student.id)).where(Student.source == "lms")) == 1


def test_xlsx_import_then_website_sync_share_one_application(engine):
    university_id, program_id = seed(engine)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID заявки", "ВУЗ", "Программа", "Статус заявки"])
    sheet.append([f"mock-website:{university_id}:{program_id}", "Stage11 university", "Stage11 program", "new"])
    output = BytesIO()
    workbook.save(output)
    file_id = import_service.stage_upload("stage11-applications.xlsx", output.getvalue())
    mapping = {"ID заявки": "application.external_id", "ВУЗ": "university.name",
               "Программа": "program.name", "Статус заявки": "application.status"}
    with Session(engine) as db:
        preview = import_service.mapping_contract(["ID заявки", "ВУЗ", "Программа", "Статус заявки"], "applications")
        assert set(preview["required_fields"]) == {"application.external_id", "university.name", "program.name"}
        dry = import_service.execute_import(db, file_id, mapping, dry_run=True, catalog_type="applications")
        assert dry["inserted"] == 1
        assert db.scalar(select(func.count(ExternalApplication.id))) == 0
        imported = import_service.execute_import(db, file_id, mapping, catalog_type="applications")
        assert imported["inserted"] == 1 and not imported["errors"]
        assert db.scalar(select(ExternalApplication.ingest_channel)) == "file"
        settings.external_adapter_mode = "disabled"
        imported_data = service.university_data(db, university_id, "website")
        assert imported_data["mode"] == "import"
        assert imported_data["applications"][0]["applications_count"] == 1
        imported_workflow = service.create_workflow_from_application(
            db, university_id, f"mock-website:{university_id}:{program_id}", None, "import-test"
        )
        assert imported_workflow["existing"] is False
        settings.external_adapter_mode = "mock"
        assert service.sync_mock(db, university_id, "website")["processed"] == 1
        assert db.scalar(select(func.count(ExternalApplication.id))) == 1
        assert db.scalar(select(ExternalApplication.ingest_channel)) == "mock"
        assert service.create_workflow_from_application(
            db, university_id, f"mock-website:{university_id}:{program_id}", None, "import-test"
        )["instance_id"] == imported_workflow["instance_id"]


def test_unavailable_never_falls_back_to_mock(engine):
    university_id, _ = seed(engine)
    settings.external_adapter_mode = "disabled"
    with Session(engine) as db:
        with pytest.raises(BusinessException) as err:
            service.university_data(db, university_id, "lms")
        assert err.value.code.value == "EXTERNAL_SOURCE_UNAVAILABLE"
        assert db.scalar(select(func.count(Student.id))) == 0


def test_website_without_source_state_is_unconfigured(engine):
    university_id, _ = seed(engine)
    settings.external_adapter_mode = "disabled"
    with Session(engine) as db:
        result = service.university_data(db, university_id, "website")
        assert result["mode"] == "unconfigured"
        assert result["applications"] == []


def test_external_workflow_repeat_and_concurrent_requests(engine):
    university_id, program_id = seed(engine)
    with Session(engine) as db:
        service.sync_mock(db, university_id, "website")
        external_id = service.university_data(db, university_id, "website")["applications"][0]["id"]

    def create():
        with Session(engine) as db:
            return service.create_workflow_from_application(db, university_id, external_id, None, "stage11-test")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: create(), range(2)))
    assert first["instance_id"] == second["instance_id"]
    assert {first["existing"], second["existing"]} == {False, True}
    assert create()["existing"] is True
    with Session(engine) as db:
        assert db.scalar(select(func.count(WorkflowInstance.id))) == 1
        application = db.scalar(select(ExternalApplication))
        assert application.workflow_instance_id == first["instance_id"]
        assert application.program_id == program_id


def test_http_permissions_unavailable_and_no_fixture_leak(engine):
    university_id, _ = seed(engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="stage11-user", roles={"user"}, university_ids=(str(university_id),)
    )
    try:
        client = TestClient(app)
        path = f"/api/v1/universities/{university_id}/external-data"
        assert client.post("/api/v1/integrations/sync", json={"university_id": str(university_id), "source": "website"}).status_code == 403
        empty = client.get(path, params={"source": "website"})
        assert empty.status_code == 200 and empty.json()["applications"] == []
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id="stage11-manager", roles={"manager"}, university_ids=(str(university_id),)
        )
        assert client.post("/api/v1/integrations/sync", json={"university_id": str(university_id), "source": "website"}).status_code == 200
        assert client.post("/api/v1/integrations/sync", json={"university_id": str(university_id), "source": "lms"}).status_code == 200
        assert client.get(path, params={"source": "website"}).json()["applications"][0]["applications_count"] == 1
        assert client.get("/api/v1/universities", params={"external_source": "website"}).json()["total"] == 1
        assert client.get("/api/v1/universities", params={"external_source": "lms"}).json()["total"] == 1
        settings.external_adapter_mode = "disabled"
        unavailable = client.get(path, params={"source": "website"})
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "EXTERNAL_SOURCE_UNAVAILABLE"
        assert "mock-website" not in str(unavailable.json())
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
