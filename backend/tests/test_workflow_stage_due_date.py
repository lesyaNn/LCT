"""Current runtime-stage due dates persist without changing template stages."""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.audit.models import AuditEvent


@pytest.fixture()
def setup():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    previous = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    try:
        with Session(engine) as db:
            university = University(name="Due date test", city="Москва")
            template = WorkflowTemplate(name="Due date test")
            db.add_all([university, template])
            db.flush()
            instance = WorkflowInstance(university_id=university.id, template_id=template.id, status="active")
            db.add(instance)
            db.flush()
            first = InstanceStage(instance_id=instance.id, order_index=1, name="Current")
            second = InstanceStage(instance_id=instance.id, order_index=2, name="Next")
            db.add_all([first, second])
            db.flush()
            instance.current_instance_stage_id = first.id
            db.commit()
            ids = instance.id, first.id, second.id
        yield TestClient(app, raise_server_exceptions=False), engine, ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = previous
        engine.dispose()


def test_current_stage_due_date_round_trip_and_wrong_stage_rejected(setup):
    client, engine, (instance_id, stage_id, other_stage_id) = setup
    path = f"/api/v1/workflow/instances/{instance_id}/stages/{stage_id}/due-date"
    created = client.patch(path, json={"due_date": "2026-10-15"})
    assert created.status_code == 200, created.text
    assert created.json()["stages"][0]["due_date"] == "2026-10-15"
    assert created.json()["due_date"] == "2026-10-15"
    persisted = client.get(f"/api/v1/workflow/instances/{instance_id}")
    assert persisted.json()["stages"][0]["due_date"] == "2026-10-15"
    changed = client.patch(path, json={"due_date": "2026-10-20"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["stages"][0]["due_date"] == "2026-10-20"
    activity = client.get(f"/api/v1/workflow/instances/{instance_id}/activity")
    assert activity.status_code == 200, activity.text
    deadline_changes = [item for item in activity.json() if item["type"] == "deadline_changed"]
    assert len(deadline_changes) == 2
    assert deadline_changes[-1]["title"] == "15.10.2026 → 20.10.2026"
    assert deadline_changes[-1]["stage_name"] == "Current"
    assert "stage_id" not in deadline_changes[-1]
    assert "old_value" not in deadline_changes[-1]
    denied = client.patch(f"/api/v1/workflow/instances/{instance_id}/stages/{other_stage_id}/due-date", json={"due_date": "2026-10-21"})
    assert denied.status_code in (400, 409), denied.text
    with Session(engine) as db:
        assert db.get(InstanceStage, stage_id).due_date == date(2026, 10, 20)
        assert db.get(InstanceStage, other_stage_id).due_date is None
        changes = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == instance_id, AuditEvent.action == "UPDATE")).all()
        assert any(event.new_value and event.new_value.get("due_date") == "2026-10-20" for event in changes)
    cleared = client.patch(path, json={"due_date": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["stages"][0]["due_date"] is None
    assert cleared.json()["due_date"] is None
    settings.auth_dev_bypass = False
    unauthorized = client.patch(path, json={"due_date": "2026-10-22"})
    assert unauthorized.status_code == 401
    assert client.get(f"/api/v1/workflow/instances/{instance_id}/activity").status_code == 401
