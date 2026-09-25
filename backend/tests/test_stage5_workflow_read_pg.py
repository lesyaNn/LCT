"""Stage 5 read contract against a dedicated migrated PostgreSQL test database."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import WorkflowAttachment, WorkflowTask
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.workflow_instances import service


@pytest.fixture()
def engine():
    from tests.db_helpers import require_pg_engine

    db_engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    yield db_engine
    db_engine.dispose()


def test_program_lookup_and_read_blocks(engine):
    with Session(engine) as db:
        university = University(name="Stage5 University", city="Москва")
        direction = ITDirection(code="stage5", name="Stage5 direction")
        template = WorkflowTemplate(name="Stage5 template")
        db.add_all([university, direction, template])
        db.flush()
        program = ITProgram(direction_id=direction.id, name="Stage5 program")
        db.add(program)
        db.flush()
        db.add(UniversityProgram(university_id=university.id, program_id=program.id))
        first = WorkflowStage(template_id=template.id, name="Подготовка", order_index=1)
        second = WorkflowStage(template_id=template.id, name="Запуск", order_index=2)
        db.add_all([first, second])
        db.commit()

        detail = service.create_instance(db, university_id=university.id,
                                         template_id=template.id, program_id=program.id,
                                         actor_sub="stage5-test")
        assert detail.program_id == program.id
        assert detail.university_name == university.name
        assert service.get_instance_by_program(db, university.id, program.id).id == detail.id
        assert service.get_instance_by_program(db, university.id, uuid4()) is None

        current = next(row for row in detail.stages if row.id == detail.current_instance_stage_id)
        db.add_all([
            WorkflowTask(instance_id=detail.id, stage_id=current.template_stage_id,
                         title="Готово", status="done"),
            WorkflowTask(instance_id=detail.id, stage_id=current.template_stage_id,
                         title="Ожидает", status="open"),
            WorkflowAttachment(instance_id=detail.id, stage_id=current.template_stage_id,
                               original_filename="test.pdf", storage_key="stage5/test.pdf",
                               file_size=4, mime_type="application/pdf",
                               uploaded_by_keycloak_sub="stage5-test"),
        ])
        db.commit()
        refreshed = service.get_instance_detail(db, detail.id)
        assert refreshed.stages[0].tasks_total == 2
        assert refreshed.stages[0].tasks_completed == 1
        scoped_items, scoped_total = service.list_instance_page(
            db, CurrentUser(id="scoped", roles={"user"}, university_ids=(str(university.id),)), 1, 20)
        assert scoped_total == 1 and scoped_items[0].id == detail.id
        _, denied_total = service.list_instance_page(
            db, CurrentUser(id="unassigned", roles={"user"}, university_ids=()), 1, 20)
        assert denied_total == 0

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        old_bypass = settings.auth_dev_bypass
        settings.auth_dev_bypass = True
        try:
            client = TestClient(app)
            lookup = client.get(f"/api/v1/workflow/instances/by-program/{program.id}",
                                params={"university_id": str(university.id)})
            assert lookup.status_code == 200
            assert lookup.json()["id"] == str(detail.id)
            empty = client.get(f"/api/v1/workflow/instances/by-program/{uuid4()}",
                               params={"university_id": str(university.id)})
            assert empty.status_code == 200 and empty.json() is None
            assert client.get(f"/api/v1/workflow/instances/{uuid4()}").status_code == 404

            listing = client.get("/api/v1/workflow/instances", params={"page_size": 1})
            assert listing.status_code == 200 and listing.json()["total"] == 1
            tasks = client.get(f"/api/v1/workflow/instances/{detail.id}/tasks")
            assert tasks.status_code == 200 and tasks.json()["total"] == 2
            allowed = client.get(f"/api/v1/workflow/instances/{detail.id}/allowed-transitions")
            assert allowed.status_code == 200
            assert [row["name"] for row in allowed.json()] == ["Запуск"]
            files = client.get(f"/api/v1/workflow/instances/{detail.id}/attachments")
            assert files.status_code == 200
            assert files.json()["items"][0]["stage_id"] == str(current.template_stage_id)
            app.dependency_overrides[get_current_user] = lambda: CurrentUser(
                id="unassigned", roles={"user"}, university_ids=())
            assert client.get(f"/api/v1/workflow/instances/by-program/{program.id}",
                              params={"university_id": str(university.id)}).status_code == 403
            assert client.get("/api/v1/workflow/instances").json()["total"] == 0
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
            settings.auth_dev_bypass = old_bypass
