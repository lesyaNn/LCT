"""Manual Workflow comments notify explicitly scoped Keycloak users only."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.models.workflow_instances import InstanceStage, WorkflowComment, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.admin_users.keycloak_client import get_keycloak_admin_client
from app.modules.notifications import service as notification_service
from app.modules.notifications.workflow_comments import _preview, _recipients, notify_comment
from app.modules.notifications.workflow_status import notify_status
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import LocalStorageBackend
from app.modules.workflow_transitions import service as transition_service
from tests.test_admin_users_rbac import FakeKeycloak


def test_recipient_scope_is_explicit_even_for_admin():
    kc = FakeKeycloak()
    university_id = uuid.uuid4()
    author = next(iter(kc.records))
    user_id = next(user_id for user_id in kc.records if user_id != author)
    kc.records[user_id]["attributes"] = {"university_ids": [str(university_id)]}
    assert [row["id"] for row in _recipients(kc, university_id, author)] == [user_id]
    assert not list(_recipients(kc, university_id, user_id))
    kc.records[author]["attributes"] = {"university_ids": [str(university_id)]}
    assert {row["id"] for row in _recipients(kc, university_id, "someone-else")} == {author, user_id}
    assert _preview("line one\n\n line two") == "line one line two"
    assert len(_preview("x" * 1000)) <= 180


@pytest.fixture()
def context(monkeypatch):
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    university = University(name="Тестовый ВУЗ", city="Москва")
    template = WorkflowTemplate(name="Тестовый Workflow")
    with Session(engine) as db:
        db.add_all([university, template])
        db.flush()
        db.add_all([
            WorkflowStage(template_id=template.id, name="Первый", order_index=1),
            WorkflowStage(template_id=template.id, name="Второй", order_index=2),
            WorkflowStage(template_id=template.id, name="Третий", order_index=3),
        ])
        instance = WorkflowInstance(university_id=university.id, template_id=template.id, status="active")
        db.add(instance)
        db.commit()
        university_id, instance_id = university.id, instance.id

    kc = FakeKeycloak()
    author_id = next(iter(kc.records))
    kc.roles[author_id] = {"user"}
    kc.records[author_id]["attributes"] = {"university_ids": [str(university_id)]}
    recipients = []
    for index, email in enumerate(("b@example.test", "", "invalid-address"), start=1):
        user_id = f"00000000-0000-4000-8000-{index + 100:012d}"
        kc.records[user_id] = {
            "id": user_id, "username": f"recipient-{index}", "email": email,
            "enabled": True, "attributes": {"university_ids": [str(university_id)]},
        }
        kc.roles[user_id] = {"user"}
        recipients.append(user_id)
    outsider = "00000000-0000-4000-8000-000000000199"
    kc.records[outsider] = {"id": outsider, "enabled": True, "email": "d@example.test",
                            "attributes": {"university_ids": [str(uuid.uuid4())]}}
    kc.roles[outsider] = {"user"}
    admin = "00000000-0000-4000-8000-000000000200"
    kc.records[admin] = {"id": admin, "enabled": True, "email": "admin@example.test",
                          "attributes": {}}
    kc.roles[admin] = {"admin"}
    actor = CurrentUser(id=author_id, name="Автор Тестовый", roles={"user"},
                        university_ids=(str(university_id),))

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_keycloak_admin_client] = lambda: kc
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    try:
        yield TestClient(app), engine, kc, actor, university_id, instance_id, recipients, outsider, admin
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_keycloak_admin_client, None)
        engine.dispose()


def test_manual_comment_fanout_email_visibility_and_dedup(context):
    client, engine, kc, actor, university_id, instance_id, recipients, outsider, admin = context
    response = client.post(f"/api/v1/workflow/instances/{instance_id}/comments",
                           json={"content": "Первый\n\n комментарий"})
    assert response.status_code == 201, response.text
    comment_id = response.json()["id"]
    with Session(engine) as db:
        rows = db.scalars(select(Notification).where(
            Notification.event_key == f"workflow_comment_added:{comment_id}")).all()
        assert {row.recipient_user_id for row in rows} == set(recipients)
        assert all(row.priority == "INFO" and row.entity_type == "workflow"
                   and row.entity_id == str(instance_id) for row in rows)
        assert all("Автор Тестовый" in row.message and "Первый комментарий" in row.message
                   for row in rows)
        assert not {actor.id, outsider, admin} & {row.recipient_user_id for row in rows}
        deliveries = db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([row.id for row in rows]))).all()
        assert len(deliveries) == 1
        assert deliveries[0].recipient == "b@example.test"
        for user_id in recipients:
            visible, total = notification_service.list_for_user(
                db, CurrentUser(id=user_id, roles={"user"}, university_ids=(str(university_id),)))
            assert total == 1 and visible[0].type == "workflow_comment_added"
        comment = db.get(WorkflowComment, uuid.UUID(comment_id))
        instance = db.get(WorkflowInstance, instance_id)
        notify_comment(db, kc, instance, comment, actor)
        assert len(db.scalars(select(Notification).where(
            Notification.event_key == f"workflow_comment_added:{comment_id}")).all()) == 3
        assert len(db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([row.id for row in rows]))).all()) == 1


def test_failed_comment_and_transition_comments_do_not_trigger_event(context):
    client, engine, _, _, _, instance_id, _, _, _ = context
    rejected = client.post(f"/api/v1/workflow/instances/{instance_id}/comments",
                           json={"content": "  "})
    assert rejected.status_code >= 400
    with Session(engine) as db:
        assert not db.scalars(select(Notification).where(
            Notification.type == "workflow_comment_added")).all()
        # Transition and rollback comments live in transition history.
        instance = db.get(WorkflowInstance, instance_id)
        stages = list(db.scalars(select(WorkflowStage).where(
            WorkflowStage.template_id == instance.template_id).order_by(WorkflowStage.order_index)))
        from app.models.workflow_instances import InstanceStage
        snapshots = [InstanceStage(instance_id=instance_id, template_stage_id=stage.id,
                                   order_index=index, name=stage.name, is_required=True,
                                   status="pending") for index, stage in enumerate(stages, start=1)]
        db.add_all(snapshots)
        db.flush()
        instance.current_instance_stage_id = snapshots[0].id
        instance.current_stage_id = stages[0].id
        db.commit()
        transition_service.transition_instance(db, instance_id, snapshots[1].id,
                                               "Переход с комментарием", "actor")
        transition_service.rollback_instance(db, instance_id, snapshots[0].id,
                                             "Откат с комментарием", "actor")
        assert not db.scalars(select(Notification).where(
            Notification.type == "workflow_comment_added")).all()


def test_attachment_comment_and_publication_failure(context, tmp_path, monkeypatch):
    client, engine, kc, _, _, instance_id, recipients, _, _ = context
    app.dependency_overrides[get_storage] = lambda: LocalStorageBackend(tmp_path)
    try:
        created = client.post(
            f"/api/v1/workflow/instances/{instance_id}/comments/with-attachments",
            data={"content": "Комментарий с файлом"},
            files=[("files", ("notes.pdf", b"document", "application/pdf"))],
        )
        assert created.status_code == 201, created.text
        with Session(engine) as db:
            rows = db.scalars(select(Notification).where(
                Notification.event_key == f"workflow_comment_added:{created.json()['id']}")).all()
            assert {row.recipient_user_id for row in rows} == set(recipients)

        def fail_users(**_):
            raise RuntimeError("Keycloak unavailable")

        monkeypatch.setattr(kc, "users", fail_users)
        saved = client.post(f"/api/v1/workflow/instances/{instance_id}/comments",
                            json={"content": "Сохранён при сбое уведомления"})
        assert saved.status_code == 201, saved.text
        with Session(engine) as db:
            assert db.get(WorkflowComment, uuid.UUID(saved.json()["id"])) is not None
            assert not db.scalars(select(Notification).where(
                Notification.event_key == f"workflow_comment_added:{saved.json()['id']}")).all()
    finally:
        app.dependency_overrides.pop(get_storage, None)


def _prepare_stages(engine, instance_id):
    with Session(engine) as db:
        instance = db.get(WorkflowInstance, instance_id)
        stages = list(db.scalars(select(WorkflowStage).where(
            WorkflowStage.template_id == instance.template_id).order_by(WorkflowStage.order_index)))
        snapshots = [InstanceStage(instance_id=instance_id, template_stage_id=stage.id,
                                   order_index=index, name=stage.name, is_required=True,
                                   status="pending") for index, stage in enumerate(stages, start=1)]
        db.add_all(snapshots)
        db.flush()
        instance.current_instance_stage_id = snapshots[0].id
        instance.current_stage_id = stages[0].id
        db.commit()
        return [row.id for row in snapshots]


def _status_rows(engine, event_type):
    with Session(engine) as db:
        return list(db.scalars(select(Notification).where(Notification.type == event_type)).all())


def test_status_routes_fanout_email_rollback_and_final_completion(context):
    client, engine, kc, actor, university_id, instance_id, recipients, outsider, admin = context
    stages = _prepare_stages(engine, instance_id)
    with Session(engine) as db:
        assert db.get(WorkflowInstance, instance_id).responsible_id is None

    def move(route, target, comment):
        response = client.post(f"/api/v1/workflow/instances/{instance_id}/{route}",
                               json={"target_instance_stage_id": str(target), "comment": comment})
        assert response.status_code == 200, response.text

    move("transition", stages[1], "Переход с комментарием")
    rows = _status_rows(engine, "workflow_stage_completed")
    assert {row.recipient_user_id for row in rows} == set(recipients)
    assert not {actor.id, outsider, admin} & {row.recipient_user_id for row in rows}
    assert all(row.title == "Этап Workflow завершён" and "Первый" in row.message
               and "Второй" in row.message and "Тестовый ВУЗ" in row.message for row in rows)
    assert not _status_rows(engine, "workflow_completed")
    with Session(engine) as db:
        deliveries = db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([row.id for row in rows]))).all()
        assert [delivery.recipient for delivery in deliveries] == ["b@example.test"]
        notify_status(db, kc, db.get(WorkflowInstance, instance_id), actor,
                      event_type="workflow_stage_completed",
                      operation_id=uuid.UUID(rows[0].event_key.rsplit(":", 1)[1]),
                      from_stage_name="Первый", to_stage_name="Второй")
    assert len(_status_rows(engine, "workflow_stage_completed")) == 3

    move("transition", stages[2], "Ещё один переход")
    move("rollback", stages[1], "Нужно уточнить условия")
    rollback = _status_rows(engine, "workflow_rollback")
    assert {row.recipient_user_id for row in rollback} == set(recipients)
    assert all(row.title == "Workflow возвращён на предыдущий этап"
               and "Второй" in row.message and "Нужно уточнить условия" in row.message
               and "Автор Тестовый" in row.message for row in rollback)
    move("transition", stages[2], "Повторный переход")
    response = client.post(f"/api/v1/workflow/instances/{instance_id}/complete")
    assert response.status_code == 200, response.text
    completed = _status_rows(engine, "workflow_completed")
    assert {row.recipient_user_id for row in completed} == set(recipients)
    assert all(row.title == "Workflow завершён" and "Тестовый Workflow" in row.message
               and row.entity_id == str(instance_id) for row in completed)
    assert len(_status_rows(engine, "workflow_stage_completed")) == 9
    assert not _status_rows(engine, "workflow_comment_added")


def test_failed_status_actions_and_keycloak_failure_after_commit(context, monkeypatch):
    client, engine, kc, _, _, instance_id, _, _, _ = context
    stages = _prepare_stages(engine, instance_id)
    failed = client.post(f"/api/v1/workflow/instances/{instance_id}/transition",
                         json={"target_instance_stage_id": str(stages[0]), "comment": "Нельзя"})
    assert failed.status_code >= 400
    failed = client.post(f"/api/v1/workflow/instances/{instance_id}/rollback",
                         json={"target_instance_stage_id": str(stages[1]), "comment": "Нельзя"})
    assert failed.status_code >= 400
    assert not _status_rows(engine, "workflow_stage_completed")
    assert not _status_rows(engine, "workflow_rollback")

    def fail_users(**_):
        raise RuntimeError("Keycloak unavailable")

    original_users = kc.users
    monkeypatch.setattr(kc, "users", fail_users)
    response = client.post(f"/api/v1/workflow/instances/{instance_id}/transition",
                           json={"target_instance_stage_id": str(stages[1]),
                                 "comment": "Операция завершится"})
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.get(WorkflowInstance, instance_id).current_instance_stage_id == stages[1]
    assert not _status_rows(engine, "workflow_stage_completed")

    monkeypatch.setattr(kc, "users", original_users)

    def fail_publish(*_args, **_kwargs):
        raise RuntimeError("Notification publication unavailable")

    monkeypatch.setattr(notification_service, "publish", fail_publish)
    response = client.post(f"/api/v1/workflow/instances/{instance_id}/rollback",
                           json={"target_instance_stage_id": str(stages[0]),
                                 "comment": "Откат при сбое уведомлений"})
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.get(WorkflowInstance, instance_id).current_instance_stage_id == stages[0]
    assert not _status_rows(engine, "workflow_rollback")
