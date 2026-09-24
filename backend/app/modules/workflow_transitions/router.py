"""P2-03/P2-04 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> frozen RBAC -> university scope -> service -> DTO.
No SQL here.

RBAC (frozen permission names, same as the B1 instance/attachment gates):
* ``GET`` history/comments need ``workflow.read``;
* ``POST``/``PATCH`` mutations need ``workflow.change_status``;
* comment edits additionally enforce author-or-admin inside the service
  (``require_role("admin")`` is NOT a route gate here so authors keep their
  15-minute window).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.audit.service import get_audit_db
from app.modules.workflow_instances import service as instance_service
from app.modules.workflow_instances.schemas import InstanceDetail
from app.modules.workflow_transitions import service
from app.modules.workflow_transitions.schemas import (
    TransitionRequest,
    WorkflowCommentCreate,
    WorkflowCommentRead,
    WorkflowCommentUpdate,
    WorkflowStageTransitionRead,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/workflow", tags=["Workflow"])

READ = require_permission("workflow.read")
WRITE = require_permission("workflow.change_status")


@router.post(
    "/instances/{instance_id}/transition",
    response_model=InstanceDetail,
    summary="Move the workflow instance to a later stage (atomic)",
)
def transition_instance(
    instance_id: uuid.UUID,
    data: TransitionRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    existing = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, existing)
    instance = service.transition_instance(
        db,
        instance_id,
        data.target_instance_stage_id,
        data.comment,
        user.id,
    )
    return instance_service.get_instance_detail(db, instance.id)


@router.get(
    "/instances/{instance_id}/transitions",
    response_model=list[WorkflowStageTransitionRead],
    summary="Transition history: prev/new stage + actor + comment (oldest first)",
)
def list_transitions(
    instance_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> list[WorkflowStageTransitionRead]:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    return service.list_transitions(db, instance_id)


@router.get(
    "/instances/{instance_id}/comments",
    response_model=PaginatedResponse[WorkflowCommentRead],
    summary="Instance comments, oldest first (paginated)",
)
def list_comments(
    instance_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[WorkflowCommentRead]:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    rows, total = service.list_comment_page(db, instance_id, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[WorkflowCommentRead.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/instances/{instance_id}/comments",
    response_model=WorkflowCommentRead,
    status_code=201,
    summary="Add an instance comment",
)
def add_comment(
    instance_id: uuid.UUID,
    data: WorkflowCommentCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> WorkflowCommentRead:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    return service.add_comment(db, instance_id, data, user.id)


@router.patch(
    "/comments/{comment_id}",
    response_model=WorkflowCommentRead,
    summary="Edit a comment (author within 15 minutes, admin any time)",
)
def edit_comment(
    comment_id: uuid.UUID,
    data: WorkflowCommentUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> WorkflowCommentRead:
    existing = service.get_comment_or_404(db, comment_id)
    instance = service.get_instance_or_404(db, existing.instance_id)
    instance_service.authorize_scope(user, instance)
    comment = service.edit_comment(
        db, comment_id, data, user.id, set(user.roles or ())
    )
    return comment


@router.delete(
    "/comments/{comment_id}",
    status_code=204,
    response_model=None,
    summary="Delete a comment (author within 15 minutes, admin any time)",
)
def delete_comment(
    comment_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> None:
    existing = service.get_comment_or_404(db, comment_id)
    instance = service.get_instance_or_404(db, existing.instance_id)
    instance_service.authorize_scope(user, instance)
    service.delete_comment(db, comment_id, user.id, set(user.roles or ()))
