"""P2-02-01/02 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> RBAC -> service -> DTO. No SQL here.

RBAC: template management is admin-only via the frozen mechanism
(``require_role("admin")``); the read-only list is available to users with
``workflow.read`` so they can choose an active template for a new instance.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, require_role
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
READ = require_permission("workflow.read")


# ---------------------------------------------------------------- templates


@router.get(
    "/templates",
    response_model=PaginatedResponse[TemplateRead],
    summary="Список шаблонов Workflow",
    description="Возвращает постраничный список шаблонов workflow для выбора при создании экземпляра. Требуется право workflow.read.",
)
def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[TemplateRead]:
    items, total = service.list_template_page(db, page=page, page_size=page_size)
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/templates",
    response_model=TemplateDetail,
    status_code=201,
    summary="Создание шаблона Workflow",
    description="Создаёт новый шаблон workflow с названием, описанием и флагом активности. Доступно только роли admin.",
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
    summary="Карточка шаблона Workflow",
    description="Возвращает шаблон workflow с этапами в порядке следования. Доступно только роли admin.",
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
    summary="Частичное обновление шаблона",
    description="Частично обновляет поля шаблона workflow (название, описание, активность). Доступно только роли admin.",
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
    response_model=dict[str, str],
    summary="Удаление шаблона Workflow",
    description="Удаляет неиспользуемый шаблон workflow. Доступно только роли admin.",
)
def delete_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(ADMIN),
) -> dict[str, str]:
    service.delete_template(db, template_id)
    return {"status": "deleted"}


# ------------------------------------------------------------------- stages


@router.post(
    "/templates/{template_id}/stages",
    response_model=StageRead,
    status_code=201,
    summary="Добавление этапа в шаблон",
    description="Добавляет этап в шаблон workflow на указанную позицию (без позиции — в конец). Доступно только роли admin.",
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
        default_tasks=data.default_tasks,
    )


@router.patch(
    "/templates/{template_id}/stages/{stage_id}",
    response_model=StageRead,
    summary="Частичное обновление этапа",
    description="Частично обновляет поля этапа шаблона workflow (название, порядок, SLA). Доступно только роли admin.",
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
        default_tasks=data.default_tasks,
    )
