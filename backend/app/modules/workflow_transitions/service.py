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
* forward moves (``order_index`` strictly grows);
* only optional (``is_required == False``) stages between current and target
  may be skipped; required ones block the move;
* the whole move (stage updates + history row + audit event) commits in ONE
  transaction (P2-03-01 atomicity).

Rollback policy (explicit step-back to a previous stage):

* only ``active`` instances move, comment is required;
* the target must be a *previous* stage (``order_index`` strictly smaller)
  that is already closed (``completed``/``skipped``);
* the target and every stage between it and the current one are reopened
  (``pending``, ``completed_at`` cleared) so the work is redone;
* history stays append-only: the step back is recorded as a transition row
  (from current to target) plus an audit event marked ``rollback: true``.

Comment policy (P2-04-01): anyone with the write gate creates; the author
may edit within 15 minutes, admins any time afterwards.

Overdue math is never local here: consumers use
``app.modules.workflow_instances.overdue.compute_overdue``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.exceptions import BadTransition, Conflict, NotFound
from app.schemas.errors import ErrorCode
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowComment,
    WorkflowInstance,
    WorkflowStageTransition,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowStage
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.meetings.service import ensure_workflow_meeting
from app.modules.workflow_instances.service import get_instance_or_404
from app.modules.workflow_transitions.schemas import (
    WorkflowCommentCreate,
    WorkflowCommentUpdate,
)

#: Instance-stage rows in one of these states are finished and can never be
#: a transition target again.
CLOSED_STAGE_STATUSES = frozenset({"completed", "skipped"})

#: Author edit window for comments (admins bypass it, P2-04-01).
COMMENT_EDIT_WINDOW_SECONDS = 15 * 60

logger = logging.getLogger(__name__)


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


def ordered_stages(instance_id: uuid.UUID, db: Session) -> list[InstanceStage]:
    """Runtime snapshot rows for one instance, oldest stage first."""
    return _ordered_stages(instance_id, db)


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


def allowed_transition_targets(instance: WorkflowInstance, stages: list[InstanceStage]) -> list[InstanceStage]:
    """Read projection of the same forward/required-stage policy as POST."""
    if instance.status != "active" or instance.current_instance_stage_id is None:
        return []
    current = _current_stage(instance, stages)
    return [target for target in stages
            if target.order_index > current.order_index
            and target.status not in CLOSED_STAGE_STATUSES
            and not any(row.is_required for row in stages
                        if current.order_index < row.order_index < target.order_index)]


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
        raise BadTransition(
            "Only active workflow instances can transition",
            code=ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE,
        )
    if not (comment or "").strip():
        raise BadTransition("Transition comment is required")

    current = _current_stage(instance, stages)
    target = next((s for s in stages if s.id == target_instance_stage_id), None)
    if target is None:
        raise NotFound("Target workflow stage not found")
    if target.order_index <= current.order_index:
        raise BadTransition("Workflow transitions can only move forward")
    if (target.status or "") in CLOSED_STAGE_STATUSES:
        raise BadTransition(
            "Target workflow stage is already closed",
            code=ErrorCode.STAGE_ALREADY_COMPLETED,
        )

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


def _require_completed_stage_tasks(db: Session, instance_id: uuid.UUID, stage: InstanceStage) -> None:
    """Read the current task statuses inside the locked transition transaction."""
    if stage.template_stage_id is None:
        return
    remaining = db.scalar(select(func.count(WorkflowTask.id)).where(
        WorkflowTask.instance_id == instance_id,
        WorkflowTask.stage_id == stage.template_stage_id,
        WorkflowTask.status != "done",
    )) or 0
    if remaining:
        raise BusinessException(
            ErrorCode.WORKFLOW_TASKS_INCOMPLETE,
            details={"remaining_tasks": remaining},
        )


def transition_instance(
    db: Session,
    instance_id: uuid.UUID,
    target_instance_stage_id: uuid.UUID,
    comment: str,
    actor: str,
    *,
    operation_id: uuid.UUID | None = None,
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
    _require_completed_stage_tasks(db, instance_id, current)

    now = utcnow()
    text = comment.strip()
    current.status = "completed"
    current.completed_at = now
    for skipped in between:
        skipped.status = "skipped"
        skipped.completed_at = now
    # The target row stays "pending" (B1 creation semantics: the current row
    # is pending; the pointer disambiguates current from upcoming).
    target.started_at = now
    instance.current_instance_stage_id = target.id
    instance.current_stage_id = target.template_stage_id
    ensure_workflow_meeting(db, instance, target, actor)
    db.add(
        WorkflowStageTransition(
            id=operation_id or uuid.uuid4(),
            instance_id=instance.id,
            from_stage_id=current.template_stage_id,
            to_stage_id=target.template_stage_id,
            actor_keycloak_sub=actor,
            comment=text,
        )
    )
    def _stage_ref(stage) -> str | None:
        return str(stage.template_stage_id) if stage.template_stage_id is not None else None

    AuditService(db).enqueue_event(
        context=context_for(db, actor),
        action=AuditAction.WORKFLOW_TRANSITION,
        entity_type="workflow_instance",
        entity_id=instance.id,
        university_id=instance.university_id,
        old_value={"audit_object_type": "workflow_transition",
                   "stage_id": _stage_ref(current), "stage_name": current.name},
        new_value={"audit_object_type": "workflow_transition",
                   "stage_id": _stage_ref(target), "stage_name": target.name},
    )
    db.commit()
    return get_instance_or_404(db, instance.id)


def validate_completion(instance: WorkflowInstance, stages: list[InstanceStage]) -> InstanceStage:
    if instance.status != "active":
        raise BadTransition("Only an active Workflow can be completed")
    current = _current_stage(instance, stages)
    if any(stage.order_index > current.order_index for stage in stages):
        raise BadTransition("Workflow can only be completed at its final stage")
    return current


def complete_instance(db: Session, instance_id: uuid.UUID, actor: str, *,
                      operation_id: uuid.UUID | None = None) -> WorkflowInstance:
    """Close the final runtime stage and instance in one transaction."""
    instance = db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id).with_for_update()
    ).scalar_one_or_none()
    if instance is None:
        raise NotFound("Workflow instance not found")
    stages = _ordered_stages(instance_id, db)
    current = validate_completion(instance, stages)
    _require_completed_stage_tasks(db, instance_id, current)
    now = utcnow()
    current.status = "completed"
    current.completed_at = now
    instance.status = "completed"
    instance.completed_at = now
    audit_event = AuditService(db).log_event(
        context=context_for(db, actor), action="UPDATE",
        entity_type="workflow_instance", entity_id=instance.id,
        university_id=instance.university_id,
        old_value={"status": "active"},
        new_value={"status": "completed", "stage_id": str(current.template_stage_id) if current.template_stage_id else None},
    )
    if operation_id is not None:
        audit_event.id = operation_id
    db.commit()
    return get_instance_or_404(db, instance.id)


def rollback_targets(instance: WorkflowInstance, stages: list[InstanceStage]) -> list[InstanceStage]:
    """Previous closed stages eligible for rollback, newest first."""
    if instance.status != "active" or instance.current_instance_stage_id is None:
        return []
    current = _current_stage(instance, stages)
    return sorted(
        (
            s for s in stages
            if s.order_index < current.order_index
            and (s.status or "") in CLOSED_STAGE_STATUSES
        ),
        key=lambda s: s.order_index,
        reverse=True,
    )


def validate_rollback(
    instance: WorkflowInstance,
    stages: list[InstanceStage],
    target_instance_stage_id: uuid.UUID,
    comment: str,
) -> tuple[InstanceStage, InstanceStage, list[InstanceStage]]:
    """Validate a step back; return (current, target, rows to reopen).

    Pure policy (no SQL), mirroring :func:`validate_transition`.
    """
    if instance.status != "active":
        raise BadTransition(
            "Only active workflow instances can transition",
            code=ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE,
        )
    if not (comment or "").strip():
        raise BadTransition("Transition comment is required")

    current = _current_stage(instance, stages)
    target = next((s for s in stages if s.id == target_instance_stage_id), None)
    if target is None:
        raise NotFound("Target workflow stage not found")
    if target.order_index >= current.order_index:
        raise BadTransition("Rollback target must be a previous stage")
    if (target.status or "") not in CLOSED_STAGE_STATUSES:
        raise BadTransition("Can only roll back to a completed stage")

    reopened = [
        s for s in stages
        if target.order_index <= s.order_index < current.order_index
    ]
    return current, target, reopened


def rollback_instance(
    db: Session,
    instance_id: uuid.UUID,
    target_instance_stage_id: uuid.UUID,
    comment: str,
    actor: str,
    *,
    operation_id: uuid.UUID | None = None,
) -> WorkflowInstance:
    """Step the current pointer back to a previous stage atomically.

    Reopens the target and every stage between it and the current one
    (``pending``, ``completed_at`` cleared), moves both current pointers,
    appends the history row and the audit event, then commits once.
    History stays append-only: the step back itself is recorded.
    """
    instance = db.execute(
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .with_for_update()
    ).scalar_one_or_none()
    if instance is None:
        raise NotFound("Workflow instance not found")
    stages = _ordered_stages(instance_id, db)
    current, target, reopened = validate_rollback(
        instance, stages, target_instance_stage_id, comment
    )

    now = utcnow()
    text = comment.strip()
    for row in reopened:
        row.status = "pending"
        row.completed_at = None
        row.started_at = now if row.id == target.id else None
    current.started_at = None
    instance.current_instance_stage_id = target.id
    instance.current_stage_id = target.template_stage_id
    ensure_workflow_meeting(db, instance, target, actor)
    db.add(
        WorkflowStageTransition(
            id=operation_id or uuid.uuid4(),
            instance_id=instance.id,
            from_stage_id=current.template_stage_id,
            to_stage_id=target.template_stage_id,
            actor_keycloak_sub=actor,
            comment=text,
        )
    )
    AuditService(db).enqueue_event(
        context=context_for(db, actor),
        action=AuditAction.WORKFLOW_TRANSITION,
        entity_type="workflow_instance",
        entity_id=instance.id,
        university_id=instance.university_id,
        old_value={"stage_id": current.template_stage_id, "stage_name": current.name},
        new_value={"stage_id": target.template_stage_id, "stage_name": target.name, "comment": text, "rollback": True},
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


def list_comment_page(
    db: Session, instance_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[WorkflowComment], int]:
    """Paginated instance discussion, oldest first (P2-04-01)."""
    from sqlalchemy import func as _func

    get_instance_or_404(db, instance_id)
    base = select(WorkflowComment).where(WorkflowComment.instance_id == instance_id)
    total = db.execute(select(_func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(WorkflowComment.created_at.asc(), WorkflowComment.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_comment_or_404(db: Session, comment_id: uuid.UUID) -> WorkflowComment:
    """Fetch a comment row without mutating (for scope checks)."""
    comment = db.get(WorkflowComment, comment_id)
    if comment is None:
        raise NotFound("Workflow comment not found")
    return comment


def _ensure_current_comment_stage(db: Session, instance: WorkflowInstance, stage_id: uuid.UUID | None) -> None:
    if instance.status != "active":
        raise BadTransition("Completed Workflow cannot be changed")
    if stage_id is None:
        return  # General instance discussion has no stage anchor.
    current = db.get(InstanceStage, instance.current_instance_stage_id) if instance.current_instance_stage_id else None
    if instance.status != "active" or current is None or current.template_stage_id != stage_id:
        raise BadTransition("Only the current stage comments can be changed")


def delete_comment(
    db: Session, comment_id: uuid.UUID, actor: str, actor_roles: set[str]
) -> WorkflowComment:
    """Delete a comment: author within 15 minutes, admins any time (P2-04-01).

    Same gate as edits. Returns the deleted row (for the scope check);
    the caller deletes after authorizing the instance.
    """
    comment = get_comment_or_404(db, comment_id)
    _ensure_current_comment_stage(db, get_instance_or_404(db, comment.instance_id), comment.stage_id)
    is_admin = "admin" in (actor_roles or set())
    if comment.author_keycloak_sub != actor and not is_admin:
        raise BadTransition("Only the author or an admin can delete a comment")
    if not is_admin:
        created = comment.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (utcnow() - created).total_seconds()
            if age > COMMENT_EDIT_WINDOW_SECONDS:
                raise Conflict("Comment delete window has expired")
    db.delete(comment)
    db.commit()
    return comment


def add_comment(
    db: Session,
    instance_id: uuid.UUID,
    data: WorkflowCommentCreate,
    actor: str,
) -> WorkflowComment:
    """Create a comment anchored to the instance (P2-04-01)."""
    instance = get_instance_or_404(db, instance_id)
    _ensure_current_comment_stage(db, instance, data.stage_id)
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
        # Explicit model default: the audit before_flush snapshot reads the
        # attribute before flush-time defaults fire, so None would leak in.
        is_internal=True,
        question_status="open" if data.is_question else "none",
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def add_comment_with_files(
    db: Session, storage, instance_id: uuid.UUID, data: WorkflowCommentCreate,
    files, actor: str,
) -> WorkflowComment:
    """Create a comment and its files in one DB transaction; remove objects on failure."""
    from app.modules.workflow_attachments import service as attachment_service
    from app.modules.workflow_attachments.storage import StorageError

    instance = get_instance_or_404(db, instance_id)
    _ensure_current_comment_stage(db, instance, data.stage_id)
    if data.stage_id is not None:
        stage = db.get(WorkflowStage, data.stage_id)
        if stage is None or stage.template_id != instance.template_id:
            raise NotFound("Workflow stage not found")
    content = (data.content or "").strip()
    if not content:
        raise BadTransition("Comment content is required")
    comment = WorkflowComment(
        instance_id=instance_id, stage_id=data.stage_id,
        author_keycloak_sub=actor, content=content, is_internal=True,
        question_status="open" if data.is_question else "none",
    )
    keys: list[str] = []
    try:
        db.add(comment)
        db.flush()
        for file in files:
            attachment = attachment_service.stage_attachment(
                db, storage, instance_id=instance_id, filename=file.filename,
                content_type=file.content_type, stream=file.file, actor_sub=actor,
                comment_id=comment.id,
            )
            keys.append(attachment.storage_key)
        db.commit()
    except Exception:
        db.rollback()
        for key in keys:
            try:
                storage.delete(key)
            except StorageError:
                logging.getLogger(__name__).exception("comment attachment cleanup failed", extra={"key": key})
        raise
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
    _ensure_current_comment_stage(db, get_instance_or_404(db, comment.instance_id), comment.stage_id)
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
    "delete_comment",
    "edit_comment",
    "get_comment_or_404",
    "get_instance_or_404",
    "list_comment_page",
    "list_comments",
    "list_transitions",
    "ordered_stages",
    "rollback_instance",
    "rollback_targets",
    "transition_instance",
    "utcnow",
    "validate_rollback",
    "validate_transition",
]
