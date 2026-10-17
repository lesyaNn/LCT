"""Pure contract tests for the canonical B2 transition policy.

Runs on the B1 canonical pipeline (``instance_stages`` snapshot rows,
1-based ``order_index``; current row referenced by
``instance.current_instance_stage_id``). No database.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.exceptions import BadTransition
from app.schemas.errors import ErrorCode
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.workflow_instances.overdue import compute_overdue
from app.modules.workflow_transitions import service as transition_service
from app.modules.workflow_transitions.service import validate_completion, validate_transition


def _instance(required_middle: bool = False
              ) -> tuple[WorkflowInstance, list[InstanceStage]]:
    current_id, middle_id, last_id = uuid4(), uuid4(), uuid4()
    instance = WorkflowInstance(
        id=uuid4(),
        university_id=uuid4(),
        template_id=uuid4(),
        status="active",
        current_instance_stage_id=current_id,
    )
    stages = [
        InstanceStage(
            id=current_id,
            instance_id=instance.id,
            template_stage_id=uuid4(),
            order_index=1,
            name="Contacts",
            is_required=True,
            status="pending",
        ),
        InstanceStage(
            id=middle_id,
            instance_id=instance.id,
            template_stage_id=uuid4(),
            order_index=2,
            name="Meeting",
            is_required=required_middle,
            status="pending",
        ),
        InstanceStage(
            id=last_id,
            instance_id=instance.id,
            template_stage_id=uuid4(),
            order_index=3,
            name="Agreement",
            is_required=True,
            status="pending",
        ),
    ]
    # Transient relationship wiring (no DB round-trip).
    return instance, stages


def test_validate_transition_skips_only_optional_stages():
    instance, stages = _instance(required_middle=False)
    current, target, skipped = validate_transition(
        instance, stages, stages[2].id, "done"
    )

    assert current.name == "Contacts"
    assert target.name == "Agreement"
    assert [stage.name for stage in skipped] == ["Meeting"]


def test_completion_requires_last_runtime_stage_and_active_instance():
    instance, stages = _instance()
    with pytest.raises(BadTransition, match="final stage"):
        validate_completion(instance, stages)
    instance.current_instance_stage_id = stages[-1].id
    assert validate_completion(instance, stages) is stages[-1]
    instance.status = "completed"
    with pytest.raises(BadTransition, match="active"):
        validate_completion(instance, stages)


def test_validate_transition_rejects_required_stage_skip():
    instance, stages = _instance(required_middle=True)
    with pytest.raises(BadTransition, match="Required stages"):
        validate_transition(instance, stages, stages[2].id, "done")


def test_validate_transition_rejects_backward_and_empty_comment():
    instance, stages = _instance()
    with pytest.raises(BadTransition, match="comment"):
        validate_transition(instance, stages, stages[2].id, "   ")

    instance.current_instance_stage_id = stages[2].id
    stages[0].status = "completed"
    with pytest.raises(BadTransition, match="forward"):
        validate_transition(instance, stages, stages[0].id, "reopen")


def test_overdue_is_derived_by_shared_helper_without_mutating_status():
    today = date(2026, 9, 20)
    overdue, days = compute_overdue(today - timedelta(days=2), None, today)

    assert overdue is True
    assert days == 2


def test_task_guard_reads_only_unfinished_tasks_of_current_stage():
    instance, stages = _instance()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE workflow_tasks (id CHAR(32), instance_id CHAR(32), stage_id CHAR(32), status VARCHAR(32))"))
        for stage_id, status in ((stages[0].template_stage_id, "open"), (stages[0].template_stage_id, "done"), (stages[1].template_stage_id, "open")):
            connection.execute(text("INSERT INTO workflow_tasks VALUES (:id, :instance_id, :stage_id, :status)"), {
                "id": uuid4().hex, "instance_id": instance.id.hex, "stage_id": stage_id.hex, "status": status,
            })
    with Session(engine) as db:
        with pytest.raises(BusinessException) as caught:
            transition_service._require_completed_stage_tasks(db, instance.id, stages[0])
        assert caught.value.code == ErrorCode.WORKFLOW_TASKS_INCOMPLETE
        assert caught.value.status_code == 409
        assert caught.value.details == {"remaining_tasks": 1}
        db.execute(text("UPDATE workflow_tasks SET status = 'done' WHERE stage_id = :stage_id"), {"stage_id": stages[0].template_stage_id.hex})
        transition_service._require_completed_stage_tasks(db, instance.id, stages[0])
    engine.dispose()


def test_transition_and_completion_both_reject_unfinished_current_tasks(monkeypatch):
    class Result:
        def __init__(self, instance):
            self.instance = instance

        def scalar_one_or_none(self):
            return self.instance

    class SessionStub:
        def __init__(self, instance):
            self.instance = instance
            self.commits = 0

        def execute(self, statement):
            return Result(self.instance)

        def scalar(self, statement):
            return 2

        def commit(self):
            self.commits += 1

    instance, stages = _instance()
    monkeypatch.setattr(transition_service, "_ordered_stages", lambda instance_id, db: stages)
    db = SessionStub(instance)
    with pytest.raises(BusinessException) as transition_error:
        transition_service.transition_instance(db, instance.id, stages[1].id, "Готово", "actor")
    assert transition_error.value.code == ErrorCode.WORKFLOW_TASKS_INCOMPLETE
    assert instance.current_instance_stage_id == stages[0].id
    assert stages[0].status == "pending" and db.commits == 0

    instance.current_instance_stage_id = stages[-1].id
    with pytest.raises(BusinessException) as completion_error:
        transition_service.complete_instance(db, instance.id, "actor")
    assert completion_error.value.details == {"remaining_tasks": 2}
    assert instance.status == "active" and stages[-1].status == "pending" and db.commits == 0
