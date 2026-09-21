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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.workflow_instances import service
from app.modules.workflow_instances.schemas import (
    InstanceCreate,
    InstanceDetail,
)

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
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    service.require_university_scope(user, data.university_id)
    return service.create_instance(
        db,
        university_id=data.university_id,
        template_id=data.template_id,
        responsible_id=data.responsible_id,
        actor_sub=user.id,
    )


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
