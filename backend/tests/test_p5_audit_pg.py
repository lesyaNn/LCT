"""P5 audit ledger, scoped API and transaction invariants on PostgreSQL."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.analytics import report_jobs
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditAction, AuditContext, AuditService


@pytest.fixture()
def audit_context():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    own, foreign = uuid.uuid4(), uuid.uuid4()
    with Session(engine) as db:
        db.add_all([University(id=own, name="Own"), University(id=foreign, name="Foreign")])
        db.commit()
    current = {"user": CurrentUser(id="manager-sub", name="Manager", roles={"manager"},
                                   university_ids=(str(own),))}

    def db_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    try:
        with TestClient(app) as client:
            yield engine, client, current, own, foreign
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        engine.dispose()


def _event(db, university_id, actor="actor", action=AuditAction.UPDATE):
    return AuditService(db).log_event(
        context=AuditContext(actor, actor, "admin"), action=action,
        entity_type="university", entity_id=university_id,
        university_id=university_id,
        old_value={"status": "old", "nested": {"x": [1, 2]}},
        new_value={"status": "new"},
    )


def test_canonical_schema_and_indexes(audit_context):
    engine, _, _, _, _ = audit_context
    with engine.connect() as conn:
        assert conn.scalar(text("select to_regclass('public.audit_events')")) == "audit_events"
        assert conn.scalar(text("select to_regclass('public.audit_logs')")) is None
        columns = dict(conn.execute(text(
            "select column_name, data_type from information_schema.columns "
            "where table_name='audit_events'"
        )).all())
        assert columns["id"] == "uuid"
        assert columns["entity_id"] == "uuid"
        assert columns["created_at"] == "timestamp with time zone"
        assert columns["old_value"] == columns["new_value"] == "jsonb"
        indexes = {row[0] for row in conn.execute(text(
            "select indexname from pg_indexes where tablename='audit_events'"
        ))}
        assert {
            "ix_audit_events_created_desc", "ix_audit_events_user_id",
            "ix_audit_events_university_id", "ix_audit_events_entity",
            "ix_audit_events_action", "ix_audit_events_request_id",
        } <= indexes


def test_transaction_rollback_and_jsonb(audit_context):
    engine, _, _, own, _ = audit_context
    with Session(engine) as db:
        obj = db.get(University, own)
        obj.name = "Committed"
        event = _event(db, own)
        assert event.id is None  # writer only adds; caller owns flush/commit
        db.commit()
        event_id = event.id
    with Session(engine) as db:
        assert db.get(University, own).name == "Committed"
        assert db.get(AuditEvent, event_id).old_value["nested"]["x"] == [1, 2]
        with pytest.raises(RuntimeError, match="business failure"):
            db.get(University, own).name = "Rolled back"
            _event(db, own, "rollback-actor")
            db.flush()
            raise RuntimeError("business failure")
        db.rollback()
    with Session(engine) as db:
        assert db.get(University, own).name == "Committed"
        assert db.scalar(select(AuditEvent).where(AuditEvent.user_id == "rollback-actor")) is None


def test_sanitizer_recursive_and_bounded(audit_context):
    engine, _, _, own, _ = audit_context
    with Session(engine) as db:
        event = AuditService(db).log_event(
            context=AuditContext("actor", "Actor", "manager"),
            action=AuditAction.UPDATE, entity_type="university", entity_id=own,
            university_id=own,
            old_value={"password": "x", "Authorization": "Bearer abc",
                       "nested": {"refresh_token": "refresh-value"}},
            new_value={"file_bytes": b"secret file", "large": "z" * 20000,
                       "note": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"},
        )
        db.commit()
        raw = str(db.get(AuditEvent, event.id).old_value)
        assert "Bearer abc" not in raw and "refresh-value" not in raw
        assert "'x'" not in raw
        assert event.new_value["file_bytes"] == "***REDACTED***"
        assert "eyJhbGci" not in str(event.new_value)
        assert len(str(event.new_value)) < 8192


def test_audit_insert_failure_aborts_business_update(audit_context):
    engine, _, _, own, _ = audit_context
    with Session(engine) as db:
        db.get(University, own).name = "Should not persist"
        AuditService(db).log_event(
            context=AuditContext("actor", "Actor", "manager"),
            action=AuditAction.UPDATE, entity_type="university",
            entity_id=None, university_id=own,  # type: ignore[arg-type]
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with Session(engine) as db:
        assert db.get(University, own).name == "Own"
        assert db.scalar(select(AuditEvent)) is None


def test_scoped_filters_rbac_and_openapi(audit_context):
    engine, client, current, own, foreign = audit_context
    with Session(engine) as db:
        first = _event(db, own, "one")
        second = _event(db, own, "two", AuditAction.CREATE)
        _event(db, foreign, "foreign")
        AuditService(db).log_event(
            context=AuditContext("system", "System", "admin"),
            action=AuditAction.ADMIN_CONFIG, entity_type="config", entity_id=uuid.uuid4(),
        )
        db.flush()
        first.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second.created_at = datetime(2026, 1, 2, 23, 59, tzinfo=timezone.utc)
        db.commit()
    route = "/api/v1/audit/events"
    current["user"] = CurrentUser(id="user", roles={"user"}, university_ids=(str(own),))
    denied = client.get(route)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert denied.json()["error"]["request_id"] == denied.headers["X-Request-ID"]
    current["user"] = CurrentUser(id="curator", roles={"curator"}, university_ids=(str(own),))
    assert client.get(route).status_code == 403
    current["user"] = CurrentUser(id="manager", roles={"manager"}, university_ids=(str(own),))
    response = client.get(route)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert response.json()["page"] == 1 and response.json()["page_size"] == 20
    assert all(item["university_id"] == str(own) for item in response.json()["items"])
    assert [item["user_id"] for item in response.json()["items"]] == ["two", "one"]
    assert set(response.json()["items"][0]) == {
        "id", "timestamp", "user_id", "user_name", "role", "action",
        "entity_type", "entity_id", "university_id", "old_value",
        "new_value", "request_id", "ip", "user_agent",
    }
    assert client.get(route, params={"university_id": str(own)}).status_code == 200
    assert client.get(route, params={"university_id": str(foreign)}).status_code == 403
    assert client.get(route, params=[("university_id", str(own)),
                                     ("university_id", str(foreign))]).status_code == 403
    filtered = client.get(route, params=[("user_id", "one"), ("user_id", "two"),
                                         ("action", "CREATE"), ("page_size", "5")])
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["user_id"] == "two"
    period = client.get(route, params={"date_from": "2026-01-02", "date_to": "2026-01-02"})
    assert period.json()["total"] == 1
    assert period.json()["items"][0]["user_id"] == "two"
    invalid = client.get(route, params={"action": "INVALID"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid.json()["error"]["request_id"] == invalid.headers["X-Request-ID"]
    assert client.get(route, params={"page_size": "101"}).status_code == 422
    assert client.get(route, params={"entity_type": "unknown"}).status_code == 422
    assert client.get(route, params={"user_id": "no-such-sub"}).json()["total"] == 0
    assert client.get(route, params={"date_from": "2026-09-24",
                                     "date_to": "2026-09-23"}).json()["error"]["code"] == "VALIDATION_ERROR"
    current["user"] = CurrentUser(id="mixed", roles={"manager", "curator"})
    assert client.get(route).json()["total"] == 0
    assert client.get(route, params={"university_id": str(own)}).status_code == 403
    current["user"] = CurrentUser(id="admin", roles={"admin"})
    assert client.get(route).json()["total"] == 4
    assert client.get(route, params={"university_id": str(uuid.uuid4())}).json()["total"] == 0
    operation = app.openapi()["paths"][route]["get"]
    assert operation["security"] == [{"BearerAuth": []}]
    assert {"200", "401", "403", "422"} <= set(operation["responses"])
    assert set(app.openapi()["paths"][route]) == {"get"}
    assert not any(
        method in {"post", "patch", "delete"}
        for path, methods in app.openapi()["paths"].items()
        if path.startswith(route)
        for method in methods
    )


def test_filter_options_scope_and_personal_field_redaction(audit_context):
    engine, client, current, own, foreign = audit_context
    with Session(engine) as db:
        AuditService(db).log_event(
            context=AuditContext("visible-actor", "Visible Actor", "manager"),
            action=AuditAction.UPDATE, entity_type="university", entity_id=own,
            university_id=own,
            new_value={"safe": "shown", "passport_number": "123456", "nested": [{"СНИЛС": "secret"}]},
        )
        _event(db, foreign, "hidden-actor")
        db.commit()
    current["user"] = CurrentUser(id="manager", roles={"manager"}, university_ids=(str(own),))
    options = client.get("/api/v1/audit/filter-options")
    assert options.status_code == 200, options.text
    assert [item["id"] for item in options.json()["users"]] == ["visible-actor"]
    assert [item["id"] for item in options.json()["universities"]] == [str(own)]
    assert "UPDATE" in options.json()["actions"]
    event = client.get("/api/v1/audit/events").json()["items"][0]
    assert event["new_value"] == {"safe": "shown", "passport_number": "***REDACTED***", "nested": [{"СНИЛС": "***REDACTED***"}]}
    current["user"] = CurrentUser(id="user", roles={"user"}, university_ids=(str(own),))
    assert client.get("/api/v1/audit/filter-options").status_code == 403


def test_http_university_mutation_context(audit_context):
    engine, client, current, own, _ = audit_context
    request_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/v1/universities/{own}", json={"name": "Changed"},
        headers={"X-Request-ID": request_id, "User-Agent": "P5-Audit-Test"},
    )
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == own)).all()
        assert len(events) == 1
        event = events[0]
        assert event.action == "UPDATE"
        assert event.old_value["name"] == "Own"
        assert event.new_value["name"] == "Changed"
        assert str(event.request_id) == response.headers["X-Request-ID"] == request_id
        assert event.user_agent == "P5-Audit-Test"
        assert event.ip_address
        assert event.role == "manager"
        assert event.user_name == "Manager"


def test_required_production_hooks(audit_context):
    engine, client, current, own, _ = audit_context
    current["user"] = CurrentUser(id="admin-sub", name="Admin", roles={"admin"})
    created = client.post("/api/v1/universities", json={"name": "Audit Created"})
    assert created.status_code == 201, created.text
    created_id = uuid.UUID(created.json()["id"])
    assert client.delete(f"/api/v1/universities/{created_id}").status_code == 204
    responsible = client.post(
        "/api/v1/responsibles", json={"full_name": "Auditor", "email": "auditor@example.test"}
    )
    assert responsible.status_code == 201, responsible.text
    responsible_id = responsible.json()["id"]
    assigned = client.post(f"/api/v1/universities/{own}/responsibles/{responsible_id}")
    assert assigned.status_code == 201, assigned.text
    meeting = client.post(
        f"/api/v1/universities/{own}/meetings",
        json={"subject": "Audit meeting", "meeting_at": "2026-09-23T12:00:00Z"},
    )
    assert meeting.status_code == 201, meeting.text
    meeting_id = uuid.UUID(meeting.json()["id"])
    assert client.patch(f"/api/v1/meetings/{meeting_id}", json={"subject": "Changed meeting"}).status_code == 200
    assert client.delete(f"/api/v1/meetings/{meeting_id}").status_code == 204
    template = client.post("/api/v1/workflow/templates", json={"name": "Audit Template"})
    assert template.status_code == 201, template.text
    report_request_id = str(uuid.uuid4())
    report = client.post(
        "/api/v1/reports", json={"format": "json"},
        headers={"X-Request-ID": report_request_id},
    )
    assert report.status_code == 202, report.text
    with Session(engine) as db:
        events = db.scalars(select(AuditEvent)).all()
        university_events = [event for event in events if event.entity_id == created_id]
        assert [event.action for event in university_events] == ["CREATE", "DELETE"]
        assert university_events[0].old_value is None
        assert university_events[0].new_value["name"] == "Audit Created"
        assert university_events[1].old_value["name"] == "Audit Created"
        assert university_events[1].new_value is None
        assignments = [event for event in events if event.action == "ASSIGN_RESPONSIBLE"]
        assert len(assignments) == 1
        assert assignments[0].old_value is None
        assert assignments[0].new_value["responsible_id"] == responsible_id
        assert assignments[0].university_id == own
        meeting_events = [event for event in events if event.entity_id == meeting_id]
        assert [event.action for event in meeting_events] == ["CREATE", "UPDATE", "DELETE"]
        assert meeting_events[1].old_value["subject"] == "Audit meeting"
        assert meeting_events[1].new_value["subject"] == "Changed meeting"
        assert len([event for event in events if event.action == "ADMIN_CONFIG"]) == 1
        report_events = [event for event in events if event.action == "REPORT_GENERATE"]
        assert len(report_events) == 1
        assert str(report_events[0].entity_id) == report.json()["job_id"]
        assert report_events[0].new_value["status"] == "queued"
        assert report_events[0].university_id is None
        assert report_events[0].user_id == "admin-sub"
        assert report_events[0].role == "admin"
        assert str(report_events[0].request_id) == report.headers["X-Request-ID"] == report_request_id
        job = report_jobs.get_job(db, report.json()["job_id"])
        assert report_jobs.mark_building(db, job)
        assert db.scalar(select(AuditEvent).where(AuditEvent.id == report_events[0].id))
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == job.id,
            AuditEvent.action == "REPORT_GENERATE",
        )).all()) == 1


def test_dev2_program_catalog_and_comment_audit(audit_context):
    engine, client, current, own, _ = audit_context
    current["user"] = CurrentUser(id="admin-sub", name="Admin", roles={"admin"})
    with Session(engine) as db:
        direction = ITDirection(code=f"AUD-{uuid.uuid4().hex[:8]}", name="Audit base")
        db.add(direction)
        db.flush()
        program = ITProgram(direction_id=direction.id, name="Audit program", description="")
        db.add(program)
        db.flush()
        db.add(UniversityProgram(university_id=own, program_id=program.id))
        template = WorkflowTemplate(name=f"Audit template {uuid.uuid4()}")
        db.add(template)
        db.flush()
        instance = WorkflowInstance(university_id=own, template_id=template.id)
        db.add(instance)
        db.commit()
        instance_id = instance.id

    direction = client.post(
        "/api/v1/directions", json={"code": f"HTTP-{uuid.uuid4().hex[:8]}", "name": "HTTP direction"}
    )
    assert direction.status_code == 201, direction.text
    direction_id = uuid.UUID(direction.json()["id"])
    assert client.patch(
        f"/api/v1/directions/{direction_id}", json={"name": "HTTP direction changed"}
    ).status_code == 200
    assert client.delete(f"/api/v1/directions/{direction_id}").status_code == 204

    meeting = client.post(
        f"/api/v1/universities/{own}/meetings",
        json={
            "meeting_type": "online",
            "subject": f"AUD-{uuid.uuid4().hex}",
            "participants": [],
            "meeting_at": "2026-09-01T12:00:00+00:00",
        },
    )
    assert meeting.status_code in (200, 201), meeting.text
    meeting_id = uuid.UUID(meeting.json()["id"])
    assert client.patch(
        f"/api/v1/meetings/{meeting_id}", json={"subject": "Changed"}
    ).status_code == 200
    assert client.delete(f"/api/v1/meetings/{meeting_id}").status_code == 204

    comment = client.post(
        f"/api/v1/workflow/instances/{instance_id}/comments",
        json={"content": "Audit comment"},
    )
    assert comment.status_code == 201, comment.text
    comment_id = uuid.UUID(comment.json()["id"])
    assert client.patch(
        f"/api/v1/workflow/comments/{comment_id}", json={"content": "Changed comment"}
    ).status_code == 200
    assert client.delete(f"/api/v1/workflow/comments/{comment_id}").status_code == 204

    with Session(engine) as db:
        direction_events = db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == direction_id)
        ).all()
        meeting_events = db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == meeting_id)
        ).all()
        comment_events = db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == comment_id)
        ).all()
        assert [event.action for event in direction_events] == ["CREATE", "UPDATE", "DELETE"]
        assert [event.entity_type for event in direction_events] == ["direction"] * 3
        assert [event.action for event in meeting_events] == ["CREATE", "UPDATE", "DELETE"]
        assert [event.entity_type for event in meeting_events] == ["meeting"] * 3
        assert [event.action for event in comment_events] == ["CREATE", "UPDATE", "DELETE"]
        assert [event.entity_type for event in comment_events] == ["workflow_comment"] * 3
        assert all(event.university_id == own for event in meeting_events + comment_events)


def test_import_job_boundary_has_one_event(audit_context):
    engine, _, _, own, _ = audit_context
    with Session(engine) as db:
        db.info["audit_context"] = AuditContext("importer", "Importer", "manager")
        job = report_jobs.create_job(
            db, format="xlsx", filters={}, columns=[], actor_sub="importer",
            actor_name="Importer", actor_roles=["manager"],
            effective_university_ids=[str(own)], job_type="xlsx_import",
            payload={"file_id": "staged", "mapping": {"name": "Name"}},
        )
        assert report_jobs.mark_building(db, job)
    with Session(engine) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == job.id)).all()
        assert len(events) == 1
        assert events[0].action == "IMPORT"
        assert events[0].university_id == own
        assert events[0].new_value == {
            "format": "xlsx", "columns": [], "status": "queued", "job_type": "xlsx_import",
        }
