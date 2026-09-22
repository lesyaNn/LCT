"""P2-03/P2-04 canonical workflow transitions and comments (B2).

Runs on the B1 canonical pipeline (``000011``-``000014`` + ``000016``):

* per-instance runtime snapshot ``instance_stages`` (1-based dense
  ``order_index``; open rows are ``pending``, closed rows are
  ``completed``/``skipped``; the current row is the one referenced by
  ``workflow_instances.current_instance_stage_id``);
* append-only history ``workflow_stage_transitions`` anchored to template
  ``workflow_stages`` (``comment`` comes from ``000016``);
* discussion ``workflow_comments`` anchored to the instance (optional
  template-stage anchor).

Transition policy (P2-03-02, pinned by ``test_p2_11_01_transition.py``):

* only ``active`` instances move;
* a non-empty comment is required (history keeps it, P2-03-03);
* only forward moves (``order_index`` strictly grows);
* only optional (``is_required == False``) stages between current and target
  may be skipped; required ones block the move;
* the whole move (stage updates + history row + audit event) commits in ONE
  transaction (P2-03-01 atomicity).

Comment policy (P2-04-01): anyone with the write gate creates; the author
may edit within 15 minutes, admins any time afterwards.

Overdue math is never local here: consumers use
``app.modules.workflow_instances.overdue.compute_overdue``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadTransition, Conflict, NotFound
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowComment,
    WorkflowInstance,
    WorkflowStageTransition,
)
from app.models.workflow_templates import WorkflowStage
from app.modules.audit.models import AuditEvent
from app.modules.workflow_transitions.schemas import (
    WorkflowCommentCreate,
    WorkflowCommentUpdate,
)

#: Instance-stage rows in one of these states are finished and can never be
#: a transition target again.
CLOSED_STAGE_STATUSES = frozenset({"completed", "skipped"})

#: Author edit window for comments (admins bypass it, P2-04-01).
COMMENT_EDIT_WINDOW_SECONDS = 15 * 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ordered_stages(instance_id: uuid.UUID, db: Session) -> list[InstanceStage]:
    return list(
        db.execute(
            select(InstanceStage)
            .where(InstanceStage.instance_id == instance_id)
            .order_by(InstanceStage.order_index.asc())
        ).scalars()
    )


def get_instance_or_404(db: Session, instance_id: uuid.UUID) -> WorkflowInstance:
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None:
        raise NotFound("Workflow instance not found")
    return instance


def _current_stage(
    instance: WorkflowInstance, stages: list[InstanceStage]
) -> InstanceStage:
    if instance.current_instance_stage_id is not None:
        current = next(
            (s for s in stages if s.id == instance.current_instance_stage_id), None
        )
        if current is not None:
            return current
    raise Conflict("Workflow instance has no current stage")


def validate_transition(
    instance: WorkflowInstance,
    stages: list[InstanceStage],
    target_instance_stage_id: uuid.UUID,
    comment: str,
) -> tuple[InstanceStage, InstanceStage, list[InstanceStage]]:
    """Validate a forward transition; return (current, target, skippable).

    Pure policy (no SQL): reusable by HTTP handlers, jobs and unit tests.
    """
    if instance.status != "active":
        raise BadTransition("Only active workflow instances can transition")
    if not (comment or "").strip():
        raise BadTransition("Transition comment is required")

    current = _current_stage(instance, stages)
    target = next((s for s in stages if s.id == target_instance_stage_id), None)
    if target is None:
        raise NotFound("Target workflow stage not found")
    if target.order_index <= current.order_index:
        raise BadTransition("Workflow transitions can only move forward")
    if (target.status or "") in CLOSED_STAGE_STATUSES:
        raise BadTransition("Target workflow stage is already closed")

    between = [
        s
        for s in stages
        if current.order_index < s.order_index < target.order_index
    ]
    required = [s for s in between if s.is_required]
    if required:
        names = ", ".join(s.name for s in required)
        raise BadTransition(f"Required stages cannot be skipped: {names}")
    return current, target, between


def transition_instance(
    db: Session,
    instance_id: uuid.UUID,
    target_instance_stage_id: uuid.UUID,
    comment: str,
    actor: str,
) -> WorkflowInstance:
    """Move the current pointer forward atomically (P2-03-01).

    Locks the instance row, closes the current snapshot row, marks skipped
    optional rows, moves both current pointers, appends the history row and
    the ``WORKFLOW_TRANSITION`` audit event, then commits once.
    """
    instance = db.execute(
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .with_for_update()
    ).scalar_one_or_none()
    if instance is None:
        raise NotFound("Workflow instance not found")
    stages = _ordered_stages(instance_id, db)
    current, target, between = validate_transition(
        instance, stages, target_instance_stage_id, comment
    )

    now = utcnow()
    text = comment.strip()
    current.status = "completed"
    current.completed_at = now
    for skipped in between:
        skipped.status = "skipped"
        skipped.completed_at = now
    # The target row stays "pending" (B1 creation semantics: the current row
    # is pending; the pointer disambiguates current from upcoming).
    instance.current_instance_stage_id = target.id
    instance.current_stage_id = target.template_stage_id
    db.add(
        WorkflowStageTransition(
            instance_id=instance.id,
            from_stage_id=current.template_stage_id,
            to_stage_id=target.template_stage_id,
            actor_keycloak_sub=actor,
            comment=text,
        )
    )
    db.add(
        AuditEvent(
            user_id=actor,
            entity_type="workflow_instance",
            entity_id=str(instance.id),
            action="WORKFLOW_TRANSITION",
            before_data=json.dumps(
                {
                    "stage": current.name,
                    "order_index": current.order_index,
                },
                ensure_ascii=False,
            ),
            after_data=json.dumps(
                {
                    "stage": target.name,
                    "order_index": target.order_index,
                },
                ensure_ascii=False,
            ),
            university_id=instance.university_id,
        )
    )
    db.commit()
    return get_instance_or_404(db, instance.id)


def list_transitions(
    db: Session, instance_id: uuid.UUID
) -> list[WorkflowStageTransition]:
    """Transition history for one instance, oldest first (P2-03-03)."""
    get_instance_or_404(db, instance_id)
    return list(
        db.execute(
            select(WorkflowStageTransition)
            .where(WorkflowStageTransition.instance_id == instance_id)
            .order_by(
                WorkflowStageTransition.created_at.asc(),
                WorkflowStageTransition.id.asc(),
            )
        ).scalars()
    )


def list_comments(db: Session, instance_id: uuid.UUID) -> list[WorkflowComment]:
    """Instance discussion, oldest first (P2-04-01)."""
    get_instance_or_404(db, instance_id)
    return list(
        db.execute(
            select(WorkflowComment)
            .where(WorkflowComment.instance_id == instance_id)
            .order_by(
                WorkflowComment.created_at.asc(),
                WorkflowComment.id.asc(),
            )
        ).scalars()
    )


def add_comment(
    db: Session,
    instance_id: uuid.UUID,
    data: WorkflowCommentCreate,
    actor: str,
) -> WorkflowComment:
    """Create a comment anchored to the instance (P2-04-01)."""
    instance = get_instance_or_404(db, instance_id)
    if data.stage_id is not None:
        stage = db.get(WorkflowStage, data.stage_id)
        if stage is None or stage.template_id != instance.template_id:
            raise NotFound("Workflow stage not found")
    content = (data.content or "").strip()
    if not content:
        raise BadTransition("Comment content is required")
    comment = WorkflowComment(
        instance_id=instance_id,
        stage_id=data.stage_id,
        author_keycloak_sub=actor,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def edit_comment(
    db: Session,
    comment_id: uuid.UUID,
    data: WorkflowCommentUpdate,
    actor: str,
    actor_roles: set[str],
) -> WorkflowComment:
    """Edit a comment: author within 15 minutes, admins any time (P2-04-01)."""
    comment = db.get(WorkflowComment, comment_id)
    if comment is None:
        raise NotFound("Workflow comment not found")
    is_admin = "admin" in (actor_roles or set())
    if comment.author_keycloak_sub != actor and not is_admin:
        raise BadTransition("Only the author or an admin can edit a comment")
    if not is_admin:
        created = comment.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (utcnow() - created).total_seconds()
            if age > COMMENT_EDIT_WINDOW_SECONDS:
                raise Conflict("Comment edit window has expired")
    content = (data.content or "").strip()
    if not content:
        raise BadTransition("Comment content is required")
    comment.content = content
    db.commit()
    db.refresh(comment)
    return comment


__all__ = [
    "CLOSED_STAGE_STATUSES",
    "COMMENT_EDIT_WINDOW_SECONDS",
    "add_comment",
    "edit_comment",
    "get_instance_or_404",
    "list_comments",
    "list_transitions",
    "transition_instance",
    "utcnow",
    "validate_transition",
]
