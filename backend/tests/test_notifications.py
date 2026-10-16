"""Notifications use the canonical PostgreSQL migration chain and auth scope."""

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import Contract, ITProduct, License, Responsible, University, UniversityResponsible, Vendor
from app.models.notification import Notification
from app.models.report_job import ReportJob
from app.models.workflow_instances import InstanceStage
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.catalog import service as catalog_service
from app.modules.notifications import service
from app.modules.workflow_instances import service as instance_service
from app.modules.workflow_transitions import service as transition_service


@pytest.fixture()
def database():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def _university(db):
    row = University(name=f"Университет {uuid.uuid4().hex[:6]}", city="Москва")
    db.add(row)
    db.flush()
    return row


def _responsible(db, sub="user-a"):
    row = Responsible(full_name="Тестовый ответственный", email=f"{uuid.uuid4()}@example.test",
                      role="manager", keycloak_sub=sub)
    db.add(row)
    db.flush()
    return row


def _user(sub, uni):
    return CurrentUser(id=sub, roles={"user"}, university_ids=(str(uni.id),))


def test_inbox_ownership_unread_and_read_actions(database):
    db = database
    uni = _university(db)
    user_a, user_b = _user("user-a", uni), _user("user-b", uni)
    assert service.publish(db, recipient_user_id="user-a", event_key="created:1",
                           type="assignment", priority="INFO", title="Назначение",
                           message="Работа назначена", entity_type="university",
                           entity_id=uni.id, university_id=uni.id)
    assert not service.publish(db, recipient_user_id="user-a", event_key="created:1",
                               type="assignment", priority="INFO", title="Назначение",
                               message="Работа назначена", entity_type="university",
                               entity_id=uni.id, university_id=uni.id)
    service.publish(db, recipient_user_id="user-b", event_key="created:1",
                    type="assignment", priority="INFO", title="Другое",
                    message="Чужое", entity_type="university", entity_id=uni.id,
                    university_id=uni.id)
    db.commit()
    a_items, a_total = service.list_for_user(db, user_a)
    b_items, b_total = service.list_for_user(db, user_b)
    assert (a_total, b_total) == (1, 1)
    assert a_items[0].title == "Назначение"
    assert b_items[0].title == "Другое"
    assert service.unread_count(db, user_a) == 1
    assert not service.mark_read(db, user_a, b_items[0].id)
    assert service.mark_read(db, user_a, a_items[0].id)
    assert service.unread_count(db, user_a) == 0
    assert a_items[0].read_at is not None
    assert service.mark_all_read(db, user_b) == 1
    assert service.unread_count(db, user_b) == 0


def test_api_uses_authenticated_recipient_even_for_admin(database):
    db = database
    uni = _university(db)
    for sub in ("user-a", "user-b"):
        service.publish(db, recipient_user_id=sub, event_key="same", type="assignment",
                        priority="INFO", title=sub, message=sub, entity_type="university",
                        entity_id=uni.id, university_id=uni.id)
    db.commit()
    foreign_id = db.scalar(select(Notification.id).where(Notification.recipient_user_id == "user-b"))
    identity = {"value": CurrentUser(id="user-a", roles={"admin"})}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: identity["value"]
    try:
        client = TestClient(app)
        response = client.get("/api/v1/notifications")
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["title"] == "user-a"
        assert client.patch(f"/api/v1/notifications/{foreign_id}/read").status_code == 404
        assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}
        assert client.post("/api/v1/notifications/read-all").json() == {"updated": 1}
        assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_assignment_transition_rollback_and_import_error(database):
    db = database
    uni = _university(db)
    responsible = _responsible(db)
    catalog_service.assign_responsible(db, uni.id, responsible.id, None)
    assert db.scalar(select(func.count()).select_from(Notification).where(
        Notification.type == "assignment")) == 1
    template = WorkflowTemplate(name="Этапы уведомлений")
    db.add(template)
    db.flush()
    db.add_all([
        WorkflowStage(template_id=template.id, name="Контакт", order_index=1),
        WorkflowStage(template_id=template.id, name="Переговоры", order_index=2),
    ])
    db.commit()
    instance = instance_service.create_instance(db, university_id=uni.id,
                                                template_id=template.id,
                                                responsible_id=responsible.id)
    assert db.scalar(select(func.count()).select_from(Notification).where(
        Notification.type == "assignment")) == 2
    first, second = instance.stages
    transition_service.transition_instance(db, instance.id, second.id, "Встреча прошла", "actor")
    transition_service.rollback_instance(db, instance.id, first.id, "Нужно уточнить условия", "actor")
    types = set(db.scalars(select(Notification.type)).all())
    assert {"workflow_stage_changed", "workflow_rollback"} <= types
    rollback = db.scalar(select(Notification).where(Notification.type == "workflow_rollback"))
    assert "Нужно уточнить условия" in rollback.message
    job = SimpleNamespace(id=uuid.uuid4(), actor_sub="user-a",
                          result={"total_rows": 120, "inserted": 114, "updated": 0, "errors_total": 6})
    assert service.notify_import_result(db, job)
    assert not service.notify_import_result(db, job)
    db.commit()
    assert db.scalar(select(Notification).where(Notification.type == "import_error")).priority == "WARNING"


def test_due_scan_idempotent_and_respects_scope(database):
    db = database
    uni = _university(db)
    resp = _responsible(db)
    db.add(UniversityResponsible(university_id=uni.id, responsible_id=resp.id, is_primary=True))
    template = WorkflowTemplate(name="Сроки")
    db.add(template)
    db.flush()
    db.add(WorkflowStage(template_id=template.id, name="Согласование", order_index=1))
    db.commit()
    instance = instance_service.create_instance(db, university_id=uni.id,
                                                template_id=template.id,
                                                responsible_id=resp.id)
    stage = instance.stages[0]
    from app.models.workflow_instances import InstanceStage
    db.get(InstanceStage, stage.id).due_date = date(2026, 10, 18)
    vendor = Vendor(name=f"Вендор {uuid.uuid4().hex[:6]}")
    db.add(vendor)
    db.flush()
    product = ITProduct(vendor_id=vendor.id, name="Платформа", version="1")
    db.add(product)
    db.flush()
    db.add(Contract(university_id=uni.id, contract_number=f"Д-{uuid.uuid4().hex[:6]}",
                    signed_at=date(2026, 1, 1), expires_at=date(2026, 11, 15)))
    db.add(License(university_id=uni.id, product_id=product.id,
                   license_number=f"Л-{uuid.uuid4().hex[:6]}",
                   signed_at=date(2026, 1, 1), expires_at=date(2026, 10, 30)))
    db.commit()
    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) >= 3
    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 0
    assert service.scan_due_notifications(db, today=date(2026, 10, 19)) >= 1
    visible, _ = service.list_for_user(db, _user("user-a", uni), filter="attention")
    assert any(item.priority == "CRITICAL" for item in visible)
    assert {"contract_expiry", "license_expiry"} <= {item.type for item in visible}
    denied = CurrentUser(id="user-a", roles={"user"}, university_ids=())
    assert service.list_for_user(db, denied)[1] == 0


def test_contract_scan_skips_inactive_statuses_and_keeps_checkpoints_distinct(database):
    db = database
    uni = _university(db)
    recipient = _responsible(db)
    db.add(UniversityResponsible(university_id=uni.id, responsible_id=recipient.id,
                                 is_primary=True))
    contracts = [
        Contract(university_id=uni.id, contract_number=f"Д-{uuid.uuid4().hex[:6]}",
                 signed_at=date(2026, 1, 1), expires_at=date(2026, 10, 30),
                 status_raw=status)
        for status in ("draft", "terminated", "signed")
    ]
    db.add_all(contracts)
    db.commit()

    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 1
    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 0
    assert service.scan_due_notifications(db, today=date(2026, 10, 23)) == 1
    rows = db.scalars(select(Notification).where(Notification.type == "contract_expiry")).all()
    assert {row.entity_id for row in rows} == {str(contracts[2].id)}
    assert {row.event_key for row in rows} == {
        f"contract_expiry:{contracts[2].id}:2026-10-30:14",
        f"contract_expiry:{contracts[2].id}:2026-10-30:7",
    }


def test_stage_scan_notifies_only_current_unfinished_stage(database):
    db = database
    uni = _university(db)
    recipient = _responsible(db)
    template = WorkflowTemplate(name="Сроки по этапам")
    db.add(template)
    db.flush()
    db.add_all([
        WorkflowStage(template_id=template.id, name=f"Этап {index}", order_index=index)
        for index in (1, 2, 3)
    ])
    db.commit()
    instance = instance_service.create_instance(db, university_id=uni.id,
                                                template_id=template.id,
                                                responsible_id=recipient.id)
    current, future_soon, future_overdue = (
        db.get(InstanceStage, stage.id) for stage in instance.stages
    )
    current.due_date = date(2026, 10, 18)
    future_soon.due_date = date(2026, 10, 17)
    future_overdue.due_date = date(2026, 10, 15)
    db.commit()

    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 1
    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 0
    current.due_date = date(2026, 10, 15)
    db.commit()
    assert service.scan_due_notifications(db, today=date(2026, 10, 16)) == 1
    current.status = "completed"
    current.completed_at = datetime(2026, 10, 16, tzinfo=timezone.utc)
    db.commit()
    assert service.scan_due_notifications(db, today=date(2026, 10, 17)) == 0
    keys = db.scalars(select(Notification.event_key).where(
        Notification.type.in_(["deadline_approaching", "overdue"])
    )).all()
    assert len(keys) == 2
    assert all(str(current.id) in key for key in keys)


def test_stage_assignment_notifies_only_new_effective_responsible(database):
    db = database
    uni = _university(db)
    fallback = _responsible(db, "ivanov")
    other = _responsible(db, "petrov")
    db.add_all([
        UniversityResponsible(university_id=uni.id, responsible_id=person.id)
        for person in (fallback, other)
    ])
    template = WorkflowTemplate(name="Назначение этапа")
    db.add(template)
    db.flush()
    db.add(WorkflowStage(template_id=template.id, name="Текущий", order_index=1))
    db.commit()
    instance = instance_service.create_instance(db, university_id=uni.id,
                                                template_id=template.id,
                                                responsible_id=fallback.id)
    stage_id = instance.current_instance_stage_id

    def recipients():
        return db.scalars(select(Notification.recipient_user_id).where(
            Notification.type == "assignment").order_by(Notification.created_at, Notification.id)
        ).all()

    assert recipients() == ["ivanov"]
    instance_service.set_instance_stage_responsible(db, instance.id, stage_id, fallback.id)
    assert recipients() == ["ivanov"]
    instance_service.set_instance_stage_responsible(db, instance.id, stage_id, other.id)
    assert recipients() == ["ivanov", "petrov"]
    instance_service.set_instance_stage_responsible(db, instance.id, stage_id, other.id)
    assert recipients() == ["ivanov", "petrov"]
    instance_service.set_instance_stage_responsible(db, instance.id, stage_id, None)
    assert recipients() == ["ivanov", "petrov", "ivanov"]


def test_import_worker_delivers_error_to_initiator(database, monkeypatch, tmp_path):
    from app.modules.analytics import report_worker
    from app.modules.imports import service as import_service

    db = database
    job = ReportJob(format="xlsx", filters={}, columns=[], actor_sub="user-a",
                    actor_name="Пользователь", actor_roles=["manager"], status="building",
                    job_type="xlsx_import", payload={"file_id": "staged", "sheet": "ВУЗы"},
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(job)
    db.commit()
    summary = {"total_rows": 3, "inserted": 2, "updated": 0, "errors_total": 1,
               "errors": [{"row": 3, "field": "name", "error": "Не заполнено"}]}
    monkeypatch.setattr(import_service, "execute_sheet", lambda *args, **kwargs: summary)
    monkeypatch.setattr(import_service, "write_error_report", lambda *args: 1)
    monkeypatch.setattr(report_worker.jobs, "job_file_path", lambda *args: tmp_path / "result.xlsx")
    assert report_worker.run_import_job(db, job) == "ready"
    row = db.scalar(select(Notification).where(Notification.recipient_user_id == "user-a"))
    assert row is not None
    assert row.type == "import_error"
    assert "Ошибок: 1" in row.message
