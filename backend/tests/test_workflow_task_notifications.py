"""Workflow task notifications follow committed task status changes."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Responsible, UniversityResponsible
from app.models.catalog import University
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask
from app.modules.notifications import service as notification_service
from app.modules.notifications.workflow_comments import _recipients
from app.modules.notifications.workflow_tasks import notify_task
from app.modules.workflow_instances import service as instance_service
from tests.test_admin_users_rbac import FakeKeycloak
from tests.test_workflow_comment_notifications import _prepare_stages

pytest_plugins = ("tests.test_workflow_comment_notifications",)


@pytest.fixture()
def task_context(request):
    comment_context = request.getfixturevalue("context")
    client, engine, kc, actor, university_id, instance_id, recipients, outsider, admin = comment_context
    stages = _prepare_stages(engine, instance_id)
    with Session(engine) as db:
        template_stage_id = db.get(InstanceStage, stages[0]).template_stage_id
        responsible = Responsible(full_name="Контакт ВУЗа", email="responsible@example.test",
                                  keycloak_sub=None)
        db.add(responsible)
        db.flush()
        db.add(UniversityResponsible(university_id=university_id,
                                     responsible_id=responsible.id))
        db.get(WorkflowInstance, instance_id).responsible_id = responsible.id
        db.commit()
    return (client, engine, kc, actor, university_id, instance_id, recipients,
            outsider, admin, stages, template_stage_id)


def _rows(engine, event_type):
    with Session(engine) as db:
        return list(db.scalars(select(Notification).where(Notification.type == event_type)).all())


def _create(client, instance_id, stage_id, title="Подготовить договор"):
    return client.post(f"/api/v1/workflow/instances/{instance_id}/tasks",
                       json={"stage_id": str(stage_id), "title": title})


def _update(client, instance_id, task_id, **changes):
    return client.patch(f"/api/v1/workflow/instances/{instance_id}/tasks/{task_id}",
                        json=changes)


def test_task_added_scope_email_content_and_responsible_null(task_context):
    (client, engine, kc, actor, university_id, instance_id, recipients, outsider,
     admin, stages, template_stage_id) = task_context
    actor.name = "Автор\n  Тестовый"
    with Session(engine) as db:
        db.get(University, university_id).name = "Тестовый\n  ВУЗ"
        db.get(InstanceStage, stages[0]).name = "Первый\n  этап"
        db.commit()
    scoped_admin = str(uuid.uuid4())
    no_permission = str(uuid.uuid4())
    disabled = str(uuid.uuid4())
    for user_id, roles, enabled in ((scoped_admin, {"admin"}, True),
                                    (no_permission, set(), True),
                                    (disabled, {"user"}, False)):
        kc.records[user_id] = {"id": user_id, "enabled": enabled,
                               "email": f"{user_id}@example.test",
                               "attributes": {"university_ids": [str(university_id)]}}
        kc.roles[user_id] = roles
    created = _create(client, instance_id, template_stage_id,
                      "Подготовить\n  договор " + "x" * 300)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    rows = _rows(engine, "workflow_task_added")
    assert {row.recipient_user_id for row in rows} == set(recipients) | {scoped_admin}
    assert not {actor.id, outsider, admin, no_permission, disabled} & {
        row.recipient_user_id for row in rows
    }
    assert all(row.event_key == f"workflow_task_added:{task_id}" and
               row.title == "Добавлена новая задача" and row.priority == "INFO" and
               row.entity_type == "workflow" and row.entity_id == str(instance_id) and
               "Автор Тестовый" in row.message and "Первый этап" in row.message and
               "Тестовый ВУЗ" in row.message and "Подготовить договор" in row.message and
               "\n" not in row.message and len(row.message) < 300 for row in rows)
    with Session(engine) as db:
        notify_task(db, kc, db.get(WorkflowInstance, instance_id),
                    db.get(WorkflowTask, uuid.UUID(task_id)), actor,
                    event_type="workflow_task_added", operation_id=uuid.UUID(task_id))
    assert len(_rows(engine, "workflow_task_added")) == len(rows)
    with Session(engine) as db:
        deliveries = db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([row.id for row in rows]))).all()
        assert {delivery.recipient for delivery in deliveries} == {
            "b@example.test", f"{scoped_admin}@example.test",
        }
        assert db.get(WorkflowInstance, instance_id).responsible_id is not None
        assert db.scalar(select(Responsible.keycloak_sub).where(
            Responsible.email == "responsible@example.test")) is None
    assert not _rows(engine, "workflow_comment_added")
    assert not _rows(engine, "workflow_stage_completed")


def test_completion_reopen_recomplete_rename_and_delete(task_context):
    client, engine, _, actor, _, instance_id, recipients, _, _, stages, template_stage_id = task_context
    created = _create(client, instance_id, template_stage_id)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    renamed = _update(client, instance_id, task_id, title="Подготовить договор до пятницы")
    assert renamed.status_code == 200, renamed.text
    assert len(_rows(engine, "workflow_task_added")) == len(recipients)
    assert not _rows(engine, "workflow_task_completed")

    completed = _update(client, instance_id, task_id, status="done")
    assert completed.status_code == 200 and completed.json()["status"] == "done"
    first = _rows(engine, "workflow_task_completed")
    assert {row.recipient_user_id for row in first} == set(recipients)
    assert all(row.title == "Задача выполнена" and row.priority == "INFO" and
               "Подготовить договор до пятницы" in row.message and
               row.entity_id == str(instance_id) for row in first)
    assert actor.id not in {row.recipient_user_id for row in first}
    with Session(engine) as db:
        deliveries = db.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([row.id for row in first]))).all()
        assert [delivery.recipient for delivery in deliveries] == ["b@example.test"]
    assert _update(client, instance_id, task_id, status="done").status_code == 200
    assert len(_rows(engine, "workflow_task_completed")) == len(recipients)
    assert _update(client, instance_id, task_id, status="open").status_code == 200
    assert len(_rows(engine, "workflow_task_completed")) == len(recipients)
    assert _update(client, instance_id, task_id, status="done").status_code == 200
    second = _rows(engine, "workflow_task_completed")
    assert len(second) == 2 * len(recipients)
    assert len({row.event_key for row in second}) == 2
    assert all(row.event_key.startswith("workflow_task_completed:") for row in second)
    deleted = client.delete(f"/api/v1/workflow/instances/{instance_id}/tasks/{task_id}")
    assert deleted.status_code == 204
    assert len(_rows(engine, "workflow_task_completed")) == 2 * len(recipients)
    assert len(_rows(engine, "workflow_task_added")) == len(recipients)
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)) is None
        assert db.get(WorkflowInstance, instance_id).current_instance_stage_id == stages[0]
    assert not _rows(engine, "workflow_comment_added")
    assert not _rows(engine, "workflow_stage_completed")


def test_failed_mutations_and_notification_failures_preserve_tasks(task_context, monkeypatch):
    client, engine, kc, _, _, instance_id, _, _, _, _, template_stage_id = task_context
    failed_create = _create(client, instance_id, uuid.uuid4())
    assert failed_create.status_code >= 400
    assert not _rows(engine, "workflow_task_added")

    original_create = instance_service.create_task

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("task create failed")

    monkeypatch.setattr(instance_service, "create_task", fail_create)
    assert _create(client, instance_id, template_stage_id).status_code >= 500
    assert not _rows(engine, "workflow_task_added")
    with Session(engine) as db:
        assert not db.scalars(select(WorkflowTask)).all()
    monkeypatch.setattr(instance_service, "create_task", original_create)

    original_users = kc.users

    def fail_users(**_):
        raise RuntimeError("Keycloak unavailable")

    monkeypatch.setattr(kc, "users", fail_users)
    created = _create(client, instance_id, template_stage_id)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)) is not None
    assert not _rows(engine, "workflow_task_added")
    monkeypatch.setattr(kc, "users", original_users)

    original_update = instance_service.update_task

    def fail_update(*_args, **_kwargs):
        raise RuntimeError("task mutation failed")

    monkeypatch.setattr(instance_service, "update_task", fail_update)
    failed_complete = _update(client, instance_id, task_id, status="done")
    assert failed_complete.status_code >= 500
    assert not _rows(engine, "workflow_task_completed")
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)).status == "open"
    monkeypatch.setattr(instance_service, "update_task", original_update)

    monkeypatch.setattr(kc, "users", fail_users)
    completed = _update(client, instance_id, task_id, status="done")
    assert completed.status_code == 200, completed.text
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)).status == "done"
    assert not _rows(engine, "workflow_task_completed")

    another = _create(client, instance_id, template_stage_id, "Ещё одна задача")
    assert another.status_code == 201, another.text
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(another.json()["id"])) is not None
    assert not _rows(engine, "workflow_task_added")
    monkeypatch.setattr(kc, "users", original_users)

    def fail_publish(*_args, **_kwargs):
        raise RuntimeError("notification unavailable")

    assert _update(client, instance_id, task_id, status="open").status_code == 200
    monkeypatch.setattr(notification_service, "publish", fail_publish)
    completed = _update(client, instance_id, task_id, status="done")
    assert completed.status_code == 200, completed.text
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)).status == "done"
    assert not _rows(engine, "workflow_task_completed")


def test_task_commit_failure_does_not_publish(task_context, monkeypatch):
    client, engine, _, _, _, instance_id, recipients, _, _, _, template_stage_id = task_context
    original_commit = Session.commit

    def fail_commit(_session):
        raise RuntimeError("task DB commit failed")

    monkeypatch.setattr(Session, "commit", fail_commit)
    assert _create(client, instance_id, template_stage_id).status_code >= 500
    monkeypatch.setattr(Session, "commit", original_commit)
    with Session(engine) as db:
        assert not db.scalars(select(WorkflowTask)).all()
    assert not _rows(engine, "workflow_task_added")

    created = _create(client, instance_id, template_stage_id)
    assert created.status_code == 201, created.text
    assert len(_rows(engine, "workflow_task_added")) == len(recipients)
    task_id = created.json()["id"]
    monkeypatch.setattr(Session, "commit", fail_commit)
    assert _update(client, instance_id, task_id, status="done").status_code >= 500
    monkeypatch.setattr(Session, "commit", original_commit)
    with Session(engine) as db:
        assert db.get(WorkflowTask, uuid.UUID(task_id)).status == "open"
    assert not _rows(engine, "workflow_task_completed")


def test_shared_recipient_resolver_paginates_beyond_200_users():
    kc = FakeKeycloak()
    university_id = uuid.uuid4()
    ids = []
    for index in range(205):
        user_id = str(uuid.uuid4())
        ids.append(user_id)
        kc.records[user_id] = {"id": user_id, "enabled": True,
                               "attributes": {"university_ids": [str(university_id)]}}
        kc.roles[user_id] = {"user"}
    assert set(ids) <= {row["id"] for row in _recipients(kc, university_id, "actor")}
