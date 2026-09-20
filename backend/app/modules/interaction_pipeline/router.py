from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, require_role
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.workflow import (
    WorkflowAttachment,
    WorkflowComment,
    WorkflowTask,
)
from app.modules.interaction_pipeline import service
from app.modules.interaction_pipeline.schemas import (
    TemplateStageCreate,
    TemplateStageRead,
    TransitionRequest,
    WorkflowAttachmentCreate,
    WorkflowAttachmentRead,
    WorkflowCommentCreate,
    WorkflowCommentRead,
    WorkflowCommentUpdate,
    WorkflowInstanceCreate,
    WorkflowInstanceRead,
    WorkflowInstanceStageRead,
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTemplateCreate,
    WorkflowTemplateRead,
    WorkflowTransitionRead,
)

router = APIRouter(prefix="/workflow", tags=["Workflow"])
READ = require_permission("workflow.read")
WRITE = require_permission("workflow.change_status")
ADMIN = require_role("admin")


def _instance_read(instance) -> WorkflowInstanceRead:
    return WorkflowInstanceRead(
        id=instance.id,
        template_id=instance.template_id,
        university_id=instance.university_id,
        program_id=instance.program_id,
        product_id=instance.product_id,
        status=instance.status,
        revision=instance.revision,
        started_at=instance.started_at,
        due_date=instance.due_date,
        completed_at=instance.completed_at,
        current_stage_code=instance.current_stage_code,
        progress_percent=instance.progress_percent,
        is_overdue=instance.is_overdue,
        days_overdue=instance.days_overdue,
        stages=[
            WorkflowInstanceStageRead(
                id=stage.id,
                template_stage_id=stage.template_stage_id,
                code=stage.template_stage.code,
                name=stage.template_stage.name,
                order_index=stage.order_index,
                is_required=stage.template_stage.is_required,
                status=stage.status,
                due_date=stage.due_date,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                skipped_at=stage.skipped_at,
                completed_by_keycloak_sub=stage.completed_by_keycloak_sub,
                is_overdue=stage.is_overdue,
                days_overdue=stage.days_overdue,
            )
            for stage in instance.stages
        ],
    )


@router.get("/templates", response_model=list[WorkflowTemplateRead])
def list_templates(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    return service.list_templates(db, include_inactive=include_inactive)


@router.post("/templates", response_model=WorkflowTemplateRead, status_code=201)
def create_template(
    data: WorkflowTemplateCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(ADMIN),
):
    return service.create_template(db, data, user.id)


@router.post(
    "/templates/{template_id}/stages",
    response_model=TemplateStageRead,
    status_code=201,
)
def add_template_stage(
    template_id: uuid.UUID,
    data: TemplateStageCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(ADMIN),
):
    return service.add_template_stage(db, template_id, data)


@router.post("/instances", response_model=WorkflowInstanceRead, status_code=201)
def create_instance(
    data: WorkflowInstanceCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return _instance_read(service.create_instance(db, data, user.id))


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceRead)
def get_instance(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    return _instance_read(service.get_instance(db, instance_id))


@router.post("/instances/{instance_id}/transition", response_model=WorkflowInstanceRead)
def transition_instance(
    instance_id: uuid.UUID,
    data: TransitionRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    instance = service.transition_instance(
        db,
        instance_id,
        data.target_stage_code,
        data.comment,
        user.id,
        user.roles,
        data.expected_revision,
    )
    return _instance_read(instance)


@router.get(
    "/instances/{instance_id}/transitions",
    response_model=list[WorkflowTransitionRead],
)
def list_transitions(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    return service.list_transitions(db, instance_id)


@router.get("/instances/{instance_id}/comments", response_model=list[WorkflowCommentRead])
def list_comments(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    service.get_instance(db, instance_id)
    return list(
        db.execute(
            select(WorkflowComment)
            .where(WorkflowComment.instance_id == instance_id)
            .order_by(WorkflowComment.created_at)
        ).scalars()
    )


@router.post(
    "/instances/{instance_id}/comments",
    response_model=WorkflowCommentRead,
    status_code=201,
)
def add_comment(
    instance_id: uuid.UUID,
    data: WorkflowCommentCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return service.add_comment(db, instance_id, data, user.id)


@router.patch("/comments/{comment_id}", response_model=WorkflowCommentRead)
def edit_comment(
    comment_id: uuid.UUID,
    data: WorkflowCommentUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return service.edit_comment(db, comment_id, data, user.id, user.roles)


@router.get("/instances/{instance_id}/tasks", response_model=list[WorkflowTaskRead])
def list_tasks(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    service.get_instance(db, instance_id)
    return list(
        db.execute(
            select(WorkflowTask)
            .where(WorkflowTask.instance_id == instance_id)
            .order_by(WorkflowTask.created_at.desc())
        ).scalars()
    )


@router.post("/instances/{instance_id}/tasks", response_model=WorkflowTaskRead, status_code=201)
def add_task(
    instance_id: uuid.UUID,
    data: WorkflowTaskCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return service.add_task(db, instance_id, data, user.id)


@router.post("/tasks/{task_id}/complete", response_model=WorkflowTaskRead)
def complete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return service.complete_task(db, task_id, user.id)


@router.get(
    "/instances/{instance_id}/attachments",
    response_model=list[WorkflowAttachmentRead],
)
def list_attachments(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
):
    service.get_instance(db, instance_id)
    return list(
        db.execute(
            select(WorkflowAttachment)
            .where(WorkflowAttachment.instance_id == instance_id)
            .order_by(WorkflowAttachment.created_at.desc())
        ).scalars()
    )


@router.post(
    "/instances/{instance_id}/attachments",
    response_model=WorkflowAttachmentRead,
    status_code=201,
)
def attach_document(
    instance_id: uuid.UUID,
    data: WorkflowAttachmentCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
):
    return service.attach_document(
        db, instance_id, data.document_id, data.instance_stage_id, user.id
    )
