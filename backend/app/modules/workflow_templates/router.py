"""P2-02-01/02 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> RBAC -> service -> DTO. No SQL here.

RBAC: templates are admin-only via the frozen mechanism
(``require_role("admin")`` — no invented ``workflow.admin`` permission;
admin holds ``*``, every other role gets 403).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_role
from app.core.security import CurrentUser
from app.modules.audit.service import get_audit_db
from app.modules.workflow_templates import service
from app.modules.workflow_templates.schemas import (
    StageCreate,
    StageRead,
    StageUpdate,
    TemplateCreate,
    TemplateDetail,
    TemplateRead,
    TemplateUpdate,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/workflow", tags=["Workflow"])

ADMIN = require_role("admin")


# ---------------------------------------------------------------- templates


@router.get(
    "/templates",
    response_model=PaginatedResponse[TemplateRead],
    summary="List workflow templates (paginated, stable ordering)",
)
def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> PaginatedResponse[TemplateRead]:
    items, total = service.list_template_page(db, page=page, page_size=page_size)
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/templates",
    response_model=TemplateDetail,
    status_code=201,
    summary="Create workflow template",
)
def create_template(
    data: TemplateCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> TemplateDetail:
    return service.create_template(
        db, name=data.name, description=data.description, is_active=data.is_active
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetail,
    summary="Get workflow template with stages in order",
)
def get_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> TemplateDetail:
    return service.get_template_detail(db, template_id)


@router.patch(
    "/templates/{template_id}",
    response_model=TemplateDetail,
    summary="Partially update workflow template",
)
def patch_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> TemplateDetail:
    fields = data.model_fields_set
    return service.patch_template(
        db,
        template_id,
        fields=fields,
        name=data.name,
        description=data.description,
        is_active=data.is_active,
    )


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_200_OK,
    response_class=Response,
    summary="Delete an unused workflow template",
)
def delete_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> None:
    service.delete_template(db, template_id)


# ------------------------------------------------------------------- stages


@router.post(
    "/templates/{template_id}/stages",
    response_model=StageRead,
    status_code=201,
    summary="Add stage at a position (omitted = append)",
)
def create_stage(
    template_id: uuid.UUID,
    data: StageCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> StageRead:
    return service.create_stage(
        db,
        template_id,
        name=data.name,
        description=data.description,
        order_index=data.order_index,
        is_required=data.is_required,
        is_active=data.is_active,
        sla_days=data.sla_days,
    )


@router.patch(
    "/templates/{template_id}/stages/{stage_id}",
    response_model=StageRead,
    summary="Partially update workflow stage",
)
def patch_stage(
    template_id: uuid.UUID,
    stage_id: uuid.UUID,
    data: StageUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> StageRead:
    fields = data.model_fields_set
    return service.patch_stage(
        db,
        template_id,
        stage_id,
        fields=fields,
        name=data.name,
        description=data.description,
        order_index=data.order_index,
        is_required=data.is_required,
        is_active=data.is_active,
        sla_days=data.sla_days,
    )
