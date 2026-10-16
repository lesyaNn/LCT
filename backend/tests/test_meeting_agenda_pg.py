"""Real PostgreSQL integration, canonical SQL migrations only (no ORM DDL)."""

import io
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.errors import register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.models.catalog import ITDirection, ITProduct, ITProgram, License, University, Vendor
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowComment, WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditContext, get_audit_db
from app.modules.meeting_agenda.router import router
from app.modules.workflow_transitions.router import router as comment_router


@pytest.fixture()
def graph():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    today = datetime.now(UTC).date()
    ids = {
        name: uuid4()
        for name in (
            "uni",
            "foreign_uni",
            "instance",
            "foreign_instance",
            "archived",
            "other_instance",
            "stage",
            "question",
            "resolved",
            "ordinary",
            "foreign_question",
            "archived_question",
            "other_question",
            "old_question",
        )
    }
    with Session(engine) as db:
        template, vendor, direction = (
            WorkflowTemplate(name="Повестка"),
            Vendor(name="Тестовый вендор"),
            ITDirection(code="IT", name="ИТ"),
        )
        db.add_all(
            [
                template,
                vendor,
                direction,
                University(id=ids["uni"], name="Наш вуз"),
                University(id=ids["foreign_uni"], name="Чужой вуз"),
            ]
        )
        db.flush()
        product = ITProduct(vendor_id=vendor.id, name="Продукт")
        db.add(product)
        for status in ("active", "launched", "planned", "archived"):
            program = ITProgram(name=status, direction_id=direction.id)
            db.add(program)
            db.flush()
            db.add(
                UniversityProgram(university_id=ids["uni"], program_id=program.id, status=status)
            )
        foreign_program = ITProgram(name="foreign", direction_id=direction.id)
        db.add(foreign_program)
        db.flush()
        db.add(
            UniversityProgram(
                university_id=ids["foreign_uni"], program_id=foreign_program.id, status="active"
            )
        )
        for iid, uid, status in (
            ("instance", "uni", "active"),
            ("other_instance", "uni", "completed"),
            ("archived", "uni", "archived"),
            ("foreign_instance", "foreign_uni", "active"),
        ):
            db.add(
                WorkflowInstance(
                    id=ids[iid], university_id=ids[uid], template_id=template.id, status=status
                )
            )
        db.flush()
        db.add(
            InstanceStage(
                id=ids["stage"], instance_id=ids["instance"], name="Встреча", order_index=3
            )
        )
        db.flush()
        db.get(WorkflowInstance, ids["instance"]).current_instance_stage_id = ids["stage"]
        for offset in (-1, 0, 30, 31):
            db.add(
                License(
                    university_id=ids["uni"],
                    product_id=product.id,
                    license_number=f"day-{offset}",
                    signed_at=today - timedelta(days=90),
                    expires_at=today + timedelta(days=offset),
                )
            )
        db.add(
            License(
                university_id=ids["foreign_uni"],
                product_id=product.id,
                license_number="foreign",
                signed_at=today,
                expires_at=today,
            )
        )
        for key, instance, status in (
            ("question", "instance", "open"),
            ("resolved", "instance", "resolved"),
            ("ordinary", "instance", "none"),
            ("foreign_question", "foreign_instance", "open"),
            ("archived_question", "archived", "open"),
            ("other_question", "other_instance", "open"),
            ("old_question", "instance", "open"),
        ):
            db.add(
                WorkflowComment(
                    id=ids[key],
                    instance_id=ids[instance],
                    author_keycloak_sub="author",
                    content=key,
                    question_status=status,
                    created_at=datetime.now(UTC) - timedelta(days=40),
                )
            )
        db.commit()

    current = [CurrentUser(id="author", roles={"user"}, university_ids=(str(ids["uni"]),))]

    def db_session():
        with Session(engine) as db:
            db.info["audit_context"] = AuditContext(current[0].id, "Test actor", "user")
            yield db

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.include_router(comment_router, prefix="/api/v1")
    register_error_handlers(application)
    application.dependency_overrides[get_current_user] = lambda: current[0]
    application.dependency_overrides[get_audit_db] = db_session
    try:
        yield TestClient(application), engine, ids, current
    finally:
        engine.dispose()


def test_real_dataset_boundaries_and_no_foreign_rows(graph):
    client, _, ids, _ = graph
    response = client.get(f"/api/v1/workflow/instances/{ids['instance']}/meeting-agenda")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {r["name"] for r in data["programs"]["items"]} == {"active", "launched"}
    assert [r["license_number"] for r in data["expiring_licenses"]["items"]] == ["day-0", "day-30"]
    assert [r["days_left"] for r in data["expiring_licenses"]["items"]] == [0, 30]
    assert {r["content"] for r in data["open_questions"]["items"]} == {
        "question",
        "old_question",
        "other_question",
    }
    assert all(
        data[key]["omitted"] == 0 for key in ("programs", "expiring_licenses", "open_questions")
    )


def test_real_status_lifecycle_creation_and_audit(graph):
    client, engine, ids, _ = graph
    base = f"/api/v1/workflow/instances/{ids['instance']}"
    ordinary = client.post(f"{base}/comments", json={"content": "Вопрос?"})
    assert ordinary.status_code == 201, ordinary.text
    assert ordinary.json()["question_status"] == "none"
    question = client.post(
        f"{base}/comments", json={"content": "Обсудить сроки", "is_question": True}
    )
    assert question.status_code == 201 and question.json()["question_status"] == "open"
    url = f"/api/v1/workflow/comments/{ids['old_question']}/question-status"
    for status in ("resolved", "open", "none"):
        result = client.patch(url, json={"status": status})
        assert result.status_code == 200, result.text
        assert result.json()["content"] == "old_question"
        assert result.json()["question_status"] == status
        texts = {
            r["content"]
            for r in client.get(f"{base}/meeting-agenda").json()["open_questions"]["items"]
        }
        assert ("old_question" in texts) == (status == "open")
    with Session(engine) as db:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == ids["old_question"], AuditEvent.action == "UPDATE"
            )
        ).all()
        assert len(events) == 3
        assert {e.new_value["question_status"] for e in events} == {"resolved", "open", "none"}
        assert all("old_question" not in str(e.new_value) for e in events)


@pytest.mark.parametrize("suffix", ["", ".pdf"])
def test_foreign_and_missing_objects_same_404(graph, suffix):
    client, _, ids, _ = graph
    for instance_id in (ids["foreign_instance"], uuid4()):
        result = client.get(f"/api/v1/workflow/instances/{instance_id}/meeting-agenda{suffix}")
        assert result.status_code == 404 and result.json()["error"]["code"] == "NOT_FOUND"
    result = client.patch(
        f"/api/v1/workflow/comments/{ids['foreign_question']}/question-status",
        json={"status": "resolved"},
    )
    assert result.status_code == 404


def test_status_author_manager_scope_and_archived_guards(graph):
    client, _, ids, current = graph
    current[0] = CurrentUser(id="stranger", roles={"user"}, university_ids=(str(ids["uni"]),))
    url = f"/api/v1/workflow/comments/{ids['question']}/question-status"
    assert client.patch(url, json={"status": "resolved"}).status_code == 403
    current[0].roles = {"manager"}
    assert client.patch(url, json={"status": "resolved"}).status_code == 200
    assert (
        client.patch(
            f"/api/v1/workflow/comments/{ids['archived_question']}/question-status",
            json={"status": "resolved"},
        ).status_code
        == 409
    )


def test_real_pdf_and_export_audit(graph):
    client, engine, ids, _ = graph
    response = client.get(f"/api/v1/workflow/instances/{ids['instance']}/meeting-agenda.pdf")
    assert response.status_code == 200, response.text[:200]
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 1
    with Session(engine) as db:
        event = db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == ids["instance"], AuditEvent.action == "REPORT_GENERATE"
            )
        ).one()
        assert event.new_value["open_question_count"] == 3
        assert event.user_id == "author"


def test_migration_default_constraint_index_and_downgrade(graph):
    _, engine, ids, _ = graph
    from pathlib import Path

    with Session(engine) as db:
        # Legacy INSERT with no explicit flag must remain an ordinary comment.
        db.execute(
            text(
                "INSERT INTO workflow_comments (id, instance_id, author_keycloak_sub, content) "
                "VALUES (:id, :iid, 'author', 'legacy')"
            ),
            {"id": uuid4(), "iid": ids["instance"]},
        )
        db.commit()
        assert (
            db.scalar(
                select(WorkflowComment.question_status).where(WorkflowComment.content == "legacy")
            )
            == "none"
        )
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE workflow_comments SET question_status = 'invalid' WHERE id = :id"),
                {"id": ids["question"]},
            )
            db.commit()
        db.rollback()
    assert "ix_workflow_comments_open_questions" in {
        i["name"] for i in inspect(engine).get_indexes("workflow_comments")
    }
    migration = Path(__file__).resolve().parents[1] / "migrations"
    # This fixture already verified a dedicated disposable database. Exercise
    # the exact down/up SQL without affecting any application database.
    for suffix, present in (("down", False), ("up", True)):
        script = (migration / f"000045_meeting_agenda.{suffix}.sql").read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.exec_driver_sql(script)
        assert (
            "question_status"
            in {c["name"] for c in inspect(engine).get_columns("workflow_comments")}
        ) == present
