"""Pure contract tests for the canonical B2 transition policy.

Runs on the B1 canonical pipeline (``instance_stages`` snapshot rows,
1-based ``order_index``; current row referenced by
``instance.current_instance_stage_id``). No database.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import BadTransition
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.workflow_instances.overdue import compute_overdue
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
