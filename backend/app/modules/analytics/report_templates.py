"""Report templates API (ТЗ §6/§8: сохранить параметры, переиспользовать).

Endpoints (mounted BEFORE ``reports_router`` so ``GET /reports/templates``
never collides with ``GET /reports/{job_id}``)::

    POST   /api/v1/reports/templates     -> 201 ReportTemplateRead
    GET    /api/v1/reports/templates     -> 200 list (own + shared)
    DELETE /api/v1/reports/templates/{id} -> 204

RBAC: ``reports.create`` to save, ``reports.read`` to list/delete-own.
``is_shared=true`` only for admins (``*`` in permissions); a non-admin
asking for shared gets ``403``. Deleting a foreign template is ``403``
for non-admins, unknown id is ``404``. Bodies reuse the frozen
``ReportRequest`` validation (format + ``UnifiedFilter`` + columns).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.schemas.validation import NonBlankText
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, SecurityError
from app.core.permissions import user_permissions
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.models.report_template import ReportTemplate
from app.modules.analytics.columns import resolve_columns
from app.modules.analytics.filters import UnifiedFilter
from app.modules.audit.service import get_audit_db
from app.schemas.common import ReportFormat
from app.schemas.errors import ErrorCode

__all__ = ["ReportTemplateRead", "router"]

router = APIRouter(prefix="/reports/templates", tags=["Reports"])


class ReportTemplateRead(BaseModel):
    """One saved template (params only, no files)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    owner_sub: str
    is_shared: bool
    format: ReportFormat
    filters: dict[str, Any]
    columns: list[str]


class ReportTemplateCreate(BaseModel):
    """Save current form params as a template."""

    name: NonBlankText = Field(min_length=1, max_length=256)
    format: ReportFormat
    filters: UnifiedFilter = Field(default_factory=UnifiedFilter)
    columns: list[str] | None = Field(default=None)
    is_shared: bool = Field(default=False)


def _is_admin(user: CurrentUser) -> bool:
    return "*" in user_permissions(user)


def _read_model(tpl: ReportTemplate) -> ReportTemplateRead:
    return ReportTemplateRead(
        id=tpl.id,
        name=tpl.name,
        owner_sub=tpl.owner_sub,
        is_shared=bool(tpl.is_shared),
        format=ReportFormat(tpl.format),
        filters=dict(tpl.filters or {}),
        columns=list(tpl.columns or []),
    )


@router.post(
    "",
    response_model=ReportTemplateRead,
    status_code=201,
    summary="Сохранить шаблон отчёта",
    description="Сохраняет параметры формы (format, filters, columns) как шаблон; is_shared=true только для администраторов. Требуется право reports.create.",
)
def create_template(
    body: ReportTemplateCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("reports.create")),
) -> ReportTemplateRead:
    if body.is_shared and not _is_admin(user):
        raise SecurityError(ErrorCode.FORBIDDEN)
    try:
        resolved = resolve_columns(body.columns)
    except ValueError as exc:
        raise BusinessException(ErrorCode.VALIDATION_ERROR) from exc
    tpl = ReportTemplate(
        id=uuid.uuid4(),
        name=body.name.strip(),
        owner_sub=user.id or "",
        is_shared=bool(body.is_shared),
        format=body.format.value,
        filters=body.filters.model_dump(mode="json"),
        columns=resolved,
    )
    if not tpl.name:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return _read_model(tpl)


@router.get(
    "",
    response_model=list[ReportTemplateRead],
    summary="Список шаблонов отчётов",
    description="Возвращает свои и общие шаблоны (до 100, сначала общие). Требуется право reports.read.",
)
def list_templates(
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("reports.read")),
) -> list[ReportTemplateRead]:
    stmt = (
        select(ReportTemplate)
        .where(
            or_(
                ReportTemplate.owner_sub == (user.id or ""),
                ReportTemplate.is_shared.is_(True),
            )
        )
        .order_by(ReportTemplate.is_shared.desc(), ReportTemplate.created_at.desc())
        .limit(100)
    )
    return [_read_model(t) for t in db.execute(stmt).scalars().all()]


@router.delete(
    "/{template_id}",
    status_code=204,
    summary="Удалить шаблон отчёта",
    description="Удаляет свой шаблон; чужой — только для администраторов, неизвестный id — 404. Требуется право reports.read.",
)
def delete_template(
    template_id: str,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("reports.read")),
):
    try:
        key = uuid.UUID(str(template_id))
    except (ValueError, AttributeError, TypeError):
        raise BusinessException(ErrorCode.NOT_FOUND) from None
    tpl = db.get(ReportTemplate, key)
    if tpl is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    if tpl.owner_sub != (user.id or "") and not _is_admin(user):
        raise SecurityError(ErrorCode.FORBIDDEN)
    db.delete(tpl)
    db.commit()
