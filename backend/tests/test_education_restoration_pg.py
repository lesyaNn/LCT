"""Education aggregates and contextual teacher training on canonical PostgreSQL."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.core.errors import BusinessException
from app.core.security import CurrentUser
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProgram, University
from app.models.education import ProgramEducationStats
from app.models.interactions import UniversityProgram
from app.modules.education import service as education_service
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


def test_lms_aggregate_website_counts_scope_and_no_student_crud(education_context):
    client, engine, (university_id, program_id) = education_context
    lms = {"university_id": str(university_id), "programs": [
        {"program_id": str(program_id), "learners_count": 31, "flows_count": 3},
    ]}
    endpoint = "/api/v1/integrations/lms/ingest"
    assert client.post(endpoint, json=lms).status_code == 200
    lms["programs"][0]["learners_count"] = 32
    assert client.post(endpoint, json=lms).status_code == 200
    website = {"university_id": str(university_id), "applications": [{
        "external_id": "website-application", "program_id": str(program_id),
        "status": "new", "external_created_at": "2026-09-20T12:00:00Z",
    }]}
    assert client.post("/api/v1/integrations/website/ingest", json=website).status_code == 200
    assert client.post("/api/v1/integrations/website/ingest", json=website).status_code == 200
    result = client.get(f"/api/v1/universities/{university_id}/education-statistics")
    assert result.status_code == 200, result.text
    assert result.json()["learners_count"] == 32
    assert result.json()["flows_count"] == 3
    assert result.json()["applications_count"] == 1
    assert result.json()["programs"][0]["learner_source"] == "lms"
    assert "full_name" not in str(result.json())
    assert client.post(f"/api/v1/universities/{university_id}/students", json={}).status_code == 404
    assert client.get(f"/api/v1/universities/{university_id}/students/summary").status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(ProgramEducationStats).where(
            ProgramEducationStats.program_id == program_id,
        )).learners_count == 32
        with pytest.raises(Exception):
            education_service.university_education(
                db, university_id, CurrentUser(id="outsider", roles={"user"},
                                               university_ids=(str(uuid.uuid4()),)),
            )
    settings.auth_dev_bypass = False
    assert client.get(f"/api/v1/universities/{university_id}/education-statistics").status_code == 401


def test_teacher_training_is_program_scoped_and_minimal(education_context):
    client, _, (university_id, program_id) = education_context
    base = f"/api/v1/universities/{university_id}/teachers"
    created = client.post(base, json={"full_name": "Мария Петрова", "program_id": str(program_id)})
    assert created.status_code == 201, created.text
    teacher_id = created.json()["id"]
    assert "email" not in created.json()
    assert "certificates" not in created.json()
    assert created.json()["teacher_programs"][0]["training_status"] == "not_started"
    updated = client.patch(f"/api/v1/teachers/{teacher_id}/programs/{program_id}", json={
        "training_status": "completed", "qualification_status": "needs_review",
        "last_training_at": "2026-09-01", "next_qualification_due_at": "2027-09-01",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["teacher_programs"][0]["qualification_status"] == "needs_review"
    assert client.patch(f"/api/v1/teachers/{teacher_id}/programs/{program_id}",
                        json={"training_status": None}).status_code == 422
    assert client.get(base).json()["total"] == 1
    assert client.post(f"/api/v1/teachers/{teacher_id}/certificates", json={}).status_code == 404
    settings.auth_dev_bypass = False
    assert client.post(base, json={"full_name": "Нет", "program_id": str(program_id)}).status_code == 401


def test_website_application_creates_workflow(education_context):
    client, engine, (university_id, program_id) = education_context
    payload = {"university_id": str(university_id), "applications": [{
        "external_id": "application-workflow", "program_id": str(program_id),
        "external_created_at": "2026-09-20T12:00:00Z",
    }]}
    assert client.post("/api/v1/integrations/website/ingest", json=payload).status_code == 200
    from app.bootstrap.workflow_defaults import ensure_spec_workflow_template
    with Session(engine) as db:
        ensure_spec_workflow_template(db)
    request = {"university_id": str(university_id), "source": "website",
               "external_id": "application-workflow"}
    first = client.post("/api/v1/workflow/instances/from-external", json=request)
    assert first.status_code == 200, first.text
    assert first.json()["existing"] is False
    assert client.post("/api/v1/workflow/instances/from-external", json=request).json()["existing"] is True


def test_demo_provider_is_explicit_and_carries_no_personal_profiles(education_context):
    client, _, (university_id, _) = education_context
    original_mode, original_env = settings.external_adapter_mode, settings.app_env
    try:
        settings.external_adapter_mode = "disabled"
        blocked = client.post("/api/v1/integrations/sync", json={
            "university_id": str(university_id), "source": "lms",
        })
        assert blocked.status_code == 503
        settings.external_adapter_mode = "mock"
        settings.app_env = "dev"
        synced = client.post("/api/v1/integrations/sync", json={
            "university_id": str(university_id), "source": "lms",
        })
        assert synced.status_code == 200, synced.text
        data = client.get(f"/api/v1/universities/{university_id}/external-data?source=lms").json()
        assert data["programs"][0]["learners_count"] == 24
        assert "name" not in str(data)
        settings.external_adapter_mode = "disabled"
        hidden = client.get(f"/api/v1/universities/{university_id}/education-statistics").json()
        assert hidden["learners_count"] == 0
    finally:
        settings.external_adapter_mode, settings.app_env = original_mode, original_env


def test_migration_37_backfills_counts_before_dropping_learner_pii():
    from tests.db_helpers import _load_migrate_module, assert_dedicated_test_db
    from sqlalchemy import create_engine

    url = os.getenv("TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires dedicated PostgreSQL test database")
    assert_dedicated_test_db(url)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    runner = _load_migrate_module()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        assert runner.cmd_up("000036_restore_learners_educators") == 0
        u, d, p = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO universities (id, name) VALUES (:u, 'Migration university')"), {"u": u})
            conn.execute(text("INSERT INTO it_directions (id, code, name) VALUES (:d, 'mig', 'Migration direction')"), {"d": d})
            conn.execute(text("INSERT INTO it_programs (id, direction_id, name, description) VALUES (:p, :d, 'Migration program', '')"), {"p": p, "d": d})
            for number, group in enumerate(("A", "A", "B"), start=1):
                conn.execute(text("INSERT INTO students (id, external_id, university_id, program_id, full_name, group_name, started_at, source) VALUES (:id, :ext, :u, :p, 'Legacy learner', :grp, '2026-01-01', 'manual')"),
                             {"id": uuid.uuid4(), "ext": f"legacy-{number}", "u": u, "p": p, "grp": group})
        assert runner.cmd_up() == 0
        with engine.connect() as conn:
            counts = conn.execute(text("SELECT learners_count, flows_count FROM program_education_stats WHERE university_id=:u"), {"u": u}).one()
            assert counts == (3, 2)
            assert conn.scalar(text("SELECT to_regclass('public.students')")) is None
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        engine.dispose()
