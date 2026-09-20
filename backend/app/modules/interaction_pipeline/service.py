"""Business rules for the canonical workflow runtime.

This module intentionally does not import the legacy ``app.modules.workflow``
package.  All identifiers are UUIDs and all state changes go through one
transaction so the instance, history and audit event cannot diverge.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import BadTransition, Conflict, NotFound
from app.models.catalog import ITProduct, ITProgram, University
from app.models.interactions import Document
from app.models.workflow import (
    WorkflowAttachment,
    WorkflowComment,
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTask,
    WorkflowTemplate,
    WorkflowTemplateStage,
    WorkflowTransition,
)
from app.modules.audit.models import AuditEvent
from app.modules.interaction_pipeline.schemas import (
    TemplateStageCreate,
    WorkflowCommentCreate,
    WorkflowCommentUpdate,
    WorkflowInstanceCreate,
    WorkflowTaskCreate,
    WorkflowTemplateCreate,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _template_options(template: WorkflowTemplate) -> list[WorkflowTemplateStage]:
    stages = sorted((stage for stage in template.stages if stage.is_active),
                    key=lambda stage: stage.order_index)
    if not stages:
        raise BadTransition("Workflow template has no active stages")
    orders = [stage.order_index for stage in stages]
    if len(orders) != len(set(orders)):
        raise Conflict("Workflow template contains duplicate stage order")
    return stages


def _instance_query(instance_id: uuid.UUID):
    return (
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .options(
            selectinload(WorkflowInstance.stages).selectinload(
                WorkflowInstanceStage.template_stage
            ),
            selectinload(WorkflowInstance.transitions),
            selectinload(WorkflowInstance.comments),
            selectinload(WorkflowInstance.tasks),
            selectinload(WorkflowInstance.attachments),
        )
    )


def get_template(db: Session, template_id: uuid.UUID) -> WorkflowTemplate:
    template = db.execute(
        select(WorkflowTemplate)
        .where(WorkflowTemplate.id == template_id)
        .options(selectinload(WorkflowTemplate.stages))
    ).scalar_one_or_none()
    if template is None:
        raise NotFound("Workflow template not found")
    return template


def list_templates(db: Session, include_inactive: bool = False) -> list[WorkflowTemplate]:
    stmt = select(WorkflowTemplate).options(selectinload(WorkflowTemplate.stages))
    if not include_inactive:
        stmt = stmt.where(WorkflowTemplate.is_active.is_(True))
    return list(db.execute(stmt.order_by(WorkflowTemplate.created_at.desc())).scalars())


def create_template(
    db: Session, data: WorkflowTemplateCreate, actor: str
) -> WorkflowTemplate:
    if len({stage.code for stage in data.stages}) != len(data.stages):
        raise Conflict("Workflow template stage codes must be unique")
    if len({stage.order_index for stage in data.stages}) != len(data.stages):
        raise Conflict("Workflow template stage order must be unique")
    template = WorkflowTemplate(
        code=data.code,
        name=data.name,
        description=data.description,
        created_by_keycloak_sub=actor,
    )
    template.stages = [
        WorkflowTemplateStage(**stage.model_dump()) for stage in data.stages
    ]
    db.add(template)
    db.commit()
    return get_template(db, template.id)


def add_template_stage(
    db: Session, template_id: uuid.UUID, data: TemplateStageCreate
) -> WorkflowTemplateStage:
    template = get_template(db, template_id)
    if any(stage.code == data.code for stage in template.stages):
        raise Conflict("Workflow template stage code already exists")
    if any(stage.order_index == data.order_index for stage in template.stages):
        raise Conflict("Workflow template stage order already exists")
    stage = WorkflowTemplateStage(template_id=template.id, **data.model_dump())
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


def get_instance(db: Session, instance_id: uuid.UUID) -> WorkflowInstance:
    instance = db.execute(_instance_query(instance_id)).scalar_one_or_none()
    if instance is None:
        raise NotFound("Workflow instance not found")
    return instance


def create_instance(
    db: Session, data: WorkflowInstanceCreate, actor: str
) -> WorkflowInstance:
    template = get_template(db, data.template_id)
    if not template.is_active:
        raise Conflict("Cannot start an inactive workflow template")
    stages = _template_options(template)

    if db.get(University, data.university_id) is None:
        raise NotFound("University not found")
    if data.program_id is not None and db.get(ITProgram, data.program_id) is None:
        raise NotFound("Program not found")
    if data.product_id is not None and db.get(ITProduct, data.product_id) is None:
        raise NotFound("Product not found")

    started_at = utcnow()
    cursor = started_at
    stage_rows: list[WorkflowInstanceStage] = []
    for index, template_stage in enumerate(stages):
        cursor += timedelta(days=template_stage.default_duration_days)
        stage_rows.append(
            WorkflowInstanceStage(
                template_stage_id=template_stage.id,
                order_index=index,
                status="current" if index == 0 else "pending",
                due_date=cursor,
                started_at=started_at if index == 0 else None,
            )
        )

    instance = WorkflowInstance(
        template_id=template.id,
        university_id=data.university_id,
        program_id=data.program_id,
        product_id=data.product_id,
        status="active",
        revision=0,
        started_at=started_at,
        due_date=data.due_date or cursor,
        created_by_keycloak_sub=actor,
        updated_by_keycloak_sub=actor,
        stages=stage_rows,
    )
    db.add(instance)
    db.commit()
    return get_instance(db, instance.id)


def _current_stage(instance: WorkflowInstance) -> WorkflowInstanceStage:
    current = next((stage for stage in instance.stages if stage.status == "current"), None)
    if current is None:
        raise Conflict("Workflow instance has no current stage")
    return current


def validate_transition(
    instance: WorkflowInstance, target_stage_code: str, comment: str
) -> tuple[WorkflowInstanceStage, WorkflowInstanceStage, list[WorkflowInstanceStage]]:
    """Validate a forward transition and return current/target/skippable stages.

    Keeping this policy separate from persistence makes the workflow rules
    deterministic and reusable by HTTP handlers, background jobs and tests.
    Only optional stages may be skipped; every required stage between the
    current and target stage blocks the transition.
    """
    if instance.status != "active":
        raise BadTransition("Only active workflow instances can transition")
    if not comment.strip():
        raise BadTransition("Transition comment is required")

    current = _current_stage(instance)
    target = next(
        (stage for stage in instance.stages
         if stage.template_stage.code == target_stage_code),
        None,
    )
    if target is None:
        raise NotFound("Target workflow stage not found")
    if target.order_index <= current.order_index:
        raise BadTransition("Workflow transitions can only move forward")
    if target.status in {"completed", "skipped"}:
        raise BadTransition("Target workflow stage is already closed")

    between = [
        stage for stage in instance.stages
        if current.order_index < stage.order_index < target.order_index
    ]
    required_between = [stage for stage in between if stage.template_stage.is_required]
    if required_between:
        names = ", ".join(stage.template_stage.name for stage in required_between)
        raise BadTransition(f"Required stages cannot be skipped: {names}")
    return current, target, between


def transition_instance(
    db: Session,
    instance_id: uuid.UUID,
    target_stage_code: str,
    comment: str,
    actor: str,
    actor_roles: set[str],
    expected_revision: int | None = None,
) -> WorkflowInstance:
    # Lock only the instance row; eager-loaded relations use separate queries.
    instance = db.execute(
        _instance_query(instance_id).with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if instance is None:
        raise NotFound("Workflow instance not found")
    if expected_revision is not None and expected_revision != instance.revision:
        raise Conflict("Workflow instance was changed by another user")
    current, target, between = validate_transition(instance, target_stage_code, comment)

    now = utcnow()
    next_revision = instance.revision + 1
    for skipped in between:
        skipped.status = "skipped"
        skipped.skipped_at = now
        skipped.completed_by_keycloak_sub = actor
        db.add(
            WorkflowTransition(
                instance_id=instance.id,
                from_stage_id=current.id,
                to_stage_id=skipped.id,
                action="skip",
                actor_keycloak_sub=actor,
                comment=comment,
                revision=next_revision,
            )
        )

    current.status = "completed"
    current.completed_at = now
    current.completed_by_keycloak_sub = actor
    # Release the partial unique 'current' slot before activating the target.
    # ORM UPDATE ordering is by UUID, not by stage order.
    db.flush()
    target.status = "current"
    target.started_at = target.started_at or now
    instance.revision = next_revision
    instance.updated_by_keycloak_sub = actor
    db.add(
        WorkflowTransition(
            instance_id=instance.id,
            from_stage_id=current.id,
            to_stage_id=target.id,
            action="next",
            actor_keycloak_sub=actor,
            comment=comment,
            revision=next_revision,
        )
    )
    db.add(
        AuditEvent(
            user_id=actor,
            entity_type="workflow_instance",
            entity_id=str(instance.id),
            action="WORKFLOW_TRANSITION",
            before_data=json.dumps(
                {"stage": current.template_stage.code, "revision": next_revision - 1},
                ensure_ascii=False,
            ),
            after_data=json.dumps(
                {"stage": target.template_stage.code, "revision": next_revision},
                ensure_ascii=False,
            ),
            university_id=instance.university_id,
        )
    )
    db.commit()
    return get_instance(db, instance.id)


def list_transitions(db: Session, instance_id: uuid.UUID) -> list[WorkflowTransition]:
    get_instance(db, instance_id)
    return list(
        db.execute(
            select(WorkflowTransition)
            .where(WorkflowTransition.instance_id == instance_id)
            .order_by(WorkflowTransition.created_at, WorkflowTransition.id)
        ).scalars()
    )


def add_comment(
    db: Session, instance_id: uuid.UUID, data: WorkflowCommentCreate, actor: str
) -> WorkflowComment:
    instance = get_instance(db, instance_id)
    if data.instance_stage_id is not None and not any(
        stage.id == data.instance_stage_id for stage in instance.stages
    ):
        raise NotFound("Workflow stage not found")
    content = data.content.strip()
    if not content:
        raise BadTransition("Comment content is required")
    comment = WorkflowComment(
        instance_id=instance_id,
        instance_stage_id=data.instance_stage_id,
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
    comment = db.get(WorkflowComment, comment_id)
    if comment is None:
        raise NotFound("Workflow comment not found")
    now = utcnow()
    is_admin = "admin" in actor_roles
    if comment.author_keycloak_sub != actor and not is_admin:
        raise BadTransition("Only the author or an admin can edit a comment")
    created_at = comment.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if not is_admin and (now - created_at).total_seconds() > 15 * 60:
        raise Conflict("Comment edit window has expired")
    content = data.content.strip()
    if not content:
        raise BadTransition("Comment content is required")
    comment.content = content
    comment.edited_at = now
    db.commit()
    db.refresh(comment)
    return comment


def add_task(
    db: Session, instance_id: uuid.UUID, data: WorkflowTaskCreate, actor: str
) -> WorkflowTask:
    instance = get_instance(db, instance_id)
    if data.instance_stage_id is not None and not any(
        stage.id == data.instance_stage_id for stage in instance.stages
    ):
        raise NotFound("Workflow stage not found")
    if not data.title.strip():
        raise BadTransition("Task title is required")
    task = WorkflowTask(instance_id=instance_id, created_by_keycloak_sub=actor,
                        title=data.title.strip(), description=data.description.strip(),
                        instance_stage_id=data.instance_stage_id,
                        assignee_keycloak_sub=data.assignee_keycloak_sub,
                        due_date=data.due_date)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def complete_task(
    db: Session, task_id: uuid.UUID, actor: str
) -> WorkflowTask:
    task = db.get(WorkflowTask, task_id)
    if task is None:
        raise NotFound("Workflow task not found")
    if task.status != "open":
        raise Conflict("Workflow task is already closed")
    task.status = "done"
    task.completed_at = utcnow()
    task.completed_by_keycloak_sub = actor
    db.commit()
    db.refresh(task)
    return task


def attach_document(
    db: Session, instance_id: uuid.UUID, document_id: uuid.UUID,
    instance_stage_id: uuid.UUID | None, actor: str,
) -> WorkflowAttachment:
    instance = get_instance(db, instance_id)
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound("Document not found")
    if document.university_id != instance.university_id:
        raise BadTransition("Document belongs to another university")
    if instance_stage_id is not None and not any(
        stage.id == instance_stage_id for stage in instance.stages
    ):
        raise NotFound("Workflow stage not found")
    attachment = WorkflowAttachment(
        instance_id=instance_id,
        document_id=document_id,
        instance_stage_id=instance_stage_id,
        created_by_keycloak_sub=actor,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment
