"""Canonical workflow task write guards without a database fixture."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import Conflict, NotFound
from app.models.workflow_instances import WorkflowTask
from app.modules.workflow_instances import service


class TaskSession:
    def __init__(self, task=None):
        self.task = task
        self.added = None
        self.deleted = None
        self.commits = 0

    def get(self, model, task_id):
        return self.task if model is WorkflowTask and self.task and self.task.id == task_id else None

    def add(self, task):
        self.added = task

    def delete(self, task):
        self.deleted = task

    def commit(self):
        self.commits += 1

    def refresh(self, task):
        pass


def instance(status="active", stage_status="current"):
    instance_id, stage_id, template_stage_id = uuid4(), uuid4(), uuid4()
    stage = SimpleNamespace(id=stage_id, template_stage_id=template_stage_id, status=stage_status)
    return SimpleNamespace(id=instance_id, status=status, current_instance_stage_id=stage_id,
                           instance_stages=[stage]), template_stage_id


def test_task_create_is_scoped_to_current_stage(monkeypatch):
    running, current_stage = instance()
    monkeypatch.setattr(service, "get_instance_or_404", lambda db, instance_id: running)
    db = TaskSession()
    task = service.create_task(db, running.id, current_stage, "  Проверить документы  ")
    assert task.title == "Проверить документы"
    assert task.stage_id == current_stage
    assert db.added is task and db.commits == 1
    with pytest.raises(Conflict):
        service.create_task(db, running.id, uuid4(), "Другая задача")
    assert db.commits == 1


def test_task_edits_stop_after_stage_completion(monkeypatch):
    running, current_stage = instance(stage_status="completed")
    monkeypatch.setattr(service, "get_instance_or_404", lambda db, instance_id: running)
    task = WorkflowTask(id=uuid4(), instance_id=running.id, stage_id=current_stage,
                        title="Документы", description="", status="open")
    db = TaskSession(task)
    with pytest.raises(Conflict):
        service.update_task(db, running.id, task.id, title=None, status="done")
    with pytest.raises(Conflict):
        service.delete_task(db, running.id, task.id)
    assert db.commits == 0


def test_task_completion_and_reopen(monkeypatch):
    running, current_stage = instance()
    monkeypatch.setattr(service, "get_instance_or_404", lambda db, instance_id: running)
    task = WorkflowTask(id=uuid4(), instance_id=running.id, stage_id=current_stage,
                        title="Документы", description="", status="open")
    db = TaskSession(task)
    service.update_task(db, running.id, task.id, title=None, status="done")
    assert task.status == "done" and task.completed_at is not None
    service.update_task(db, running.id, task.id, title=None, status="open")
    assert task.status == "open" and task.completed_at is None
    assert db.commits == 2
    with pytest.raises(NotFound):
        service.update_task(db, uuid4(), uuid4(), title=None, status="done")
