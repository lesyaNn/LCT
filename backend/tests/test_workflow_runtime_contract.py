"""Pure contract tests for the canonical B2 transition policy."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import BadTransition
from app.models.workflow import (
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTemplateStage,
)
from app.modules.interaction_pipeline.service import validate_transition


def _instance(required_middle: bool = False) -> WorkflowInstance:
    template_stages = [
        WorkflowTemplateStage(
            code="contacts", name="Contacts", order_index=0, is_required=True
        ),
        WorkflowTemplateStage(
            code="meeting", name="Meeting", order_index=1, is_required=required_middle
        ),
        WorkflowTemplateStage(
            code="agreement", name="Agreement", order_index=2, is_required=True
        ),
    ]
    return WorkflowInstance(
        status="active",
        stages=[
            WorkflowInstanceStage(
                status="current", order_index=0, template_stage=template_stages[0]
            ),
            WorkflowInstanceStage(
                status="pending", order_index=1, template_stage=template_stages[1]
            ),
            WorkflowInstanceStage(
                status="pending", order_index=2, template_stage=template_stages[2]
            ),
        ],
    )


def test_validate_transition_skips_only_optional_stages():
    instance = _instance(required_middle=False)
    current, target, skipped = validate_transition(instance, "agreement", "done")

    assert current.template_stage.code == "contacts"
    assert target.template_stage.code == "agreement"
    assert [stage.template_stage.code for stage in skipped] == ["meeting"]


def test_validate_transition_rejects_required_stage_skip():
    with pytest.raises(BadTransition, match="Required stages"):
        validate_transition(_instance(required_middle=True), "agreement", "done")


def test_validate_transition_rejects_backward_and_empty_comment():
    instance = _instance()
    with pytest.raises(BadTransition, match="comment"):
        validate_transition(instance, "agreement", "   ")

    instance.stages[2].status = "current"
    instance.stages[0].status = "completed"
    with pytest.raises(BadTransition, match="forward"):
        validate_transition(instance, "contacts", "reopen")


def test_overdue_properties_are_derived_without_mutating_status():
    instance = _instance()
    instance.due_date = datetime.now(timezone.utc) - timedelta(days=2, hours=1)

    assert instance.is_overdue is True
    assert instance.days_overdue >= 2
    assert instance.status == "active"
