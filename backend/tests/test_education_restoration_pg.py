"""Recovered learner/educator domain uses canonical PostgreSQL and scoped APIs."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.core.errors import BusinessException
from app.core.security import CurrentUser
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import Student, UniversityProgram
from app.modules.students import service as student_service
from app.modules.integrations import service as integration_service


def test_provider_timeout_maps_to_typed_unavailable_error():
    class FailingAdapter:
        def fetch(self, university_id, program_id, *, timeout_seconds=10):
            raise TimeoutError("provider timeout")

    with pytest.raises(BusinessException) as error:
        integration_service.fetch_from_provider(FailingAdapter(), uuid.uuid4(), uuid.uuid4())
    assert error.value.code.value == "EXTERNAL_SOURCE_UNAVAILABLE"


@pytest.fixture()
def education_context():
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
            university = University(name="Education university", city="Москва")
            direction = ITDirection(code="education-test", name="Test direction")
            db.add_all([university, direction])
            db.flush()
            program = ITProgram(direction_id=direction.id, name="Test program", description="")
            db.add(program)
            db.flush()
            db.add(UniversityProgram(university_id=university.id, program_id=program.id))
            db.commit()
            ids = university.id, program.id
        yield TestClient(app, raise_server_exceptions=False), engine, ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = previous
        engine.dispose()


def test_students_lms_summary_and_scope(education_context):
    client, engine, (university_id, program_id) = education_context
    base = f"/api/v1/universities/{university_id}/students"
    created = client.post(base, json={
        "external_id": "manual-learner", "program_id": str(program_id),
        "full_name": "Ручной студент", "group_name": "Поток А",
        "status": "active", "started_at": "2026-09-01",
    })
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "manual"
    learner_id = created.json()["id"]
    patch = client.patch(f"/api/v1/students/{learner_id}", json={"status": "graduated"})
    assert patch.status_code == 200, patch.text

    ingest = client.post("/api/v1/integrations/lms/ingest", json={
        "university_id": str(university_id),
        "learners": [{"external_id": "lms-learner", "program_id": str(program_id),
                      "full_name": "Студент LMS", "group_name": "Поток Б",
                      "status": "active", "started_at": "2026-09-01", "progress": 42}],
    })
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["processed"] == 1
    duplicate = client.post("/api/v1/integrations/lms/ingest", json={
        "university_id": str(university_id),
        "learners": [{"external_id": "lms-learner", "program_id": str(program_id),
                      "full_name": "Студент LMS", "group_name": "Поток Б",
                      "status": "active", "started_at": "2026-09-01", "progress": 55}],
    })
    assert duplicate.status_code == 200, duplicate.text
    summary = client.get(f"{base}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["learners"] == 2
    assert summary.json()["active_learners"] == 1
    assert summary.json()["flows"] == 2
    assert summary.json()["programs"][0]["lms_learners"] == 1
    filtered = client.get(f"{base}?status=active")
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["progress"] == 55
    with Session(engine) as db:
        assert db.scalar(select(Student).where(Student.external_id == "lms-learner")).source == "lms"
        with pytest.raises(Exception):
            student_service.student_summary(
                db, university_id, user=CurrentUser(id="outsider", roles={"user"},
                                                     university_ids=(str(uuid.uuid4()),)),
            )
    settings.auth_dev_bypass = False
    assert client.get(base).status_code == 401


def test_teacher_training_records_and_permissions(education_context):
    client, _, (university_id, program_id) = education_context
    base = f"/api/v1/universities/{university_id}/teachers"
    created = client.post(base, json={"full_name": "Мария Петрова", "email": "teacher@example.test", "position": "Доцент"})
    assert created.status_code == 201, created.text
    teacher_id = created.json()["id"]
    linked = client.post(f"/api/v1/teachers/{teacher_id}/programs", json={
        "program_id": str(program_id), "can_teach": True, "assigned_at": "2026-09-01",
    })
    assert linked.status_code == 200, linked.text
    qualified = client.post(f"/api/v1/teachers/{teacher_id}/qualifications", json={
        "qualification_name": "DevOps", "obtained_at": "2026-09-01",
        "expires_at": "2028-09-01",
    })
    assert qualified.status_code == 200, qualified.text
    certified = client.post(f"/api/v1/teachers/{teacher_id}/certificates", json={
        "certificate_name": "Практика", "issued_at": "2026-09-02",
        "program_id": str(program_id), "is_mandatory": True,
    })
    assert certified.status_code == 200, certified.text
    reread = client.get(f"/api/v1/teachers/{teacher_id}")
    assert reread.status_code == 200, reread.text
    assert len(reread.json()["teacher_programs"]) == 1
    assert len(reread.json()["qualifications"]) == 1
    assert len(reread.json()["certificates"]) == 1
    listed = client.get(base)
    assert listed.status_code == 200 and listed.json()["total"] == 1
    settings.auth_dev_bypass = False
    assert client.post(base, json={"full_name": "Нет", "email": "no@example.test"}).status_code == 401


def test_website_json_ingest_is_idempotent_and_visible(education_context):
    client, engine, (university_id, program_id) = education_context
    payload = {
        "university_id": str(university_id),
        "applications": [{"external_id": "website-application", "program_id": str(program_id),
                          "person_name": "Заявитель", "status": "new", "flow_name": "Поток А",
                          "external_created_at": "2026-09-20T12:00:00Z"}],
    }
    endpoint = "/api/v1/integrations/website/ingest"
    first = client.post(endpoint, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["processed"] == 1
    second = client.post(endpoint, json=payload)
    assert second.status_code == 200, second.text
    data = client.get(f"/api/v1/universities/{university_id}/external-data?source=website")
    assert data.status_code == 200, data.text
    assert data.json()["applications"][0]["applications_count"] == 1
    assert data.json()["applications"][0]["source"] == "website"
    from app.bootstrap.workflow_defaults import ensure_spec_workflow_template
    with Session(engine) as db:
        ensure_spec_workflow_template(db)
    workflow = client.post("/api/v1/workflow/instances/from-external", json={
        "university_id": str(university_id), "source": "website",
        "external_id": "website-application",
    })
    assert workflow.status_code == 200, workflow.text
    assert workflow.json()["instance_id"]
    again = client.post("/api/v1/workflow/instances/from-external", json={
        "university_id": str(university_id), "source": "website",
        "external_id": "website-application",
    })
    assert again.status_code == 200 and again.json()["existing"] is True
    settings.auth_dev_bypass = False
    assert client.post(endpoint, json=payload).status_code == 401


def test_demo_adapters_are_explicit_and_disabled_by_default(education_context):
    client, _, (university_id, _) = education_context
    original_mode, original_env = settings.external_adapter_mode, settings.app_env
    try:
        settings.external_adapter_mode = "disabled"
        blocked = client.post("/api/v1/integrations/sync", json={
            "university_id": str(university_id), "source": "lms",
        })
        assert blocked.status_code == 503, blocked.text
        settings.external_adapter_mode = "mock"
        settings.app_env = "dev"
        for source in ("lms", "website"):
            synced = client.post("/api/v1/integrations/sync", json={
                "university_id": str(university_id), "source": source,
            })
            assert synced.status_code == 200, synced.text
            assert synced.json()["processed"] == 1
            data = client.get(f"/api/v1/universities/{university_id}/external-data?source={source}")
            assert data.status_code == 200, data.text
            assert data.json()["students" if source == "lms" else "applications"]
    finally:
        settings.external_adapter_mode, settings.app_env = original_mode, original_env
