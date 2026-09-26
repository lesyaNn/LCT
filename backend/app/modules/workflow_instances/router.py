"""P2-02-03 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> frozen RBAC -> university scope -> service -> DTO.
No SQL here.

RBAC (frozen permission names, no invented ones):
* ``GET`` instance needs ``workflow.read`` (manager/curator/admin read path,
  same as the P2-05 attachments read gate).
* ``POST`` instance needs ``workflow.change_status`` (mutation gate, same as
  the P2-05 attachments write gate).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, user_permissions
from app.core.errors import SecurityError
from app.schemas.errors import ErrorCode
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.modules.workflow_instances import service
from app.modules.workflow_instances.schemas import (
    InstanceCreate,
    InstanceDetail,
    InstanceResponsibleUpdate,
    WorkflowTaskRead,
    AllowedTransitionRead,
)
from app.schemas.common import PaginatedResponse
from app.modules.workflow_transitions.service import allowed_transition_targets

router = APIRouter(prefix="/workflow", tags=["Workflow"])

READ = require_permission("workflow.read")
WRITE = require_permission("workflow.change_status")


@router.post(
    "/instances",
    response_model=InstanceDetail,
    status_code=201,
    summary="Create workflow instance (snapshot active template stages)",
)
def create_workflow_instance(
    data: InstanceCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    service.require_university_scope(user, data.university_id)
    if (
        data.responsible_id is not None
        and "university_responsible.manage" not in user_permissions(user)
        and not (user.roles or set()).intersection({"admin", "curator"})
    ):
        raise SecurityError(ErrorCode.FORBIDDEN)
    return service.create_instance(
        db,
        university_id=data.university_id,
        template_id=data.template_id,
        program_id=data.program_id,
        product_id=data.product_id,
        responsible_id=data.responsible_id,
        actor_sub=user.id,
    )


@router.get("/instances", response_model=PaginatedResponse[InstanceDetail])
def list_workflow_instances(
    university_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[InstanceDetail]:
    if university_id is not None:
        service.require_university_scope(user, university_id)
    items, total = service.list_instance_page(db, user, page, page_size, university_id)
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/instances/by-program/{program_id}", response_model=InstanceDetail | None)
def get_workflow_by_program(
    program_id: uuid.UUID,
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> InstanceDetail | None:
    service.require_university_scope(user, university_id)
    return service.get_instance_by_program(db, university_id, program_id)


@router.get(
    "/instances/{instance_id}",
    response_model=InstanceDetail,
    summary="Get workflow instance with runtime stages in order",
)
def get_workflow_instance(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> InstanceDetail:
    detail = service.get_instance_detail(db, instance_id)
    service.authorize_scope(user, detail)
    return detail


@router.patch(
    "/instances/{instance_id}",
    response_model=InstanceDetail,
    summary="Assign or clear the workflow instance responsible",
)
def update_workflow_instance_responsible(
    instance_id: uuid.UUID,
    data: InstanceResponsibleUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    detail = service.get_instance_detail(db, instance_id)
    service.authorize_scope(user, detail)
    return service.set_instance_responsible(
        db, instance_id, data.responsible_id, actor_sub=user.id
    )


@router.get("/instances/{instance_id}/tasks", response_model=PaginatedResponse[WorkflowTaskRead])
def list_workflow_tasks(
    instance_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[WorkflowTaskRead]:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    rows, total = service.list_task_page(db, instance_id, page, page_size)
    return PaginatedResponse(items=[WorkflowTaskRead.model_validate(row) for row in rows], page=page, page_size=page_size, total=total)


@router.get("/instances/{instance_id}/allowed-transitions", response_model=list[AllowedTransitionRead])
def get_allowed_transitions(
    instance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> list[AllowedTransitionRead]:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    return [AllowedTransitionRead(id=row.id, order_index=row.order_index, name=row.name)
            for row in allowed_transition_targets(instance, list(instance.instance_stages))]
