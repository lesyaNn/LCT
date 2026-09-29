"""Read-only, scoped P5 audit API."""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import SecurityError
from app.core.permissions import require_permission
from app.core.policies import apply_university_scope, get_data_scope
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.models import AuditEvent
from app.models.catalog import University
from app.modules.audit.presentation import actor_display_name, summarize_event
from app.modules.audit.resolver import (
    entity_display_name,
    fallback_name,
    resolve_names,
)
from app.modules.audit.service import AuditAction, AuditEntityType
from app.schemas.common import PaginatedResponse
from app.schemas.errors import ErrorCode, ErrorResponse

router = APIRouter(prefix="/audit", tags=["Audit"])

_SENSITIVE_KEYS = ("snils", "снилс", "passport", "паспорт", "address", "адрес", "birth", "рождения", "diploma", "диплом")


def public_audit_value(value: Any) -> Any:
    """Redact personal-document fields in API output without altering the ledger."""
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if any(part in str(key).lower() for part in _SENSITIVE_KEYS)
            else public_audit_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [public_audit_value(item) for item in value]
    return value


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    user_id: str
    user_name: str
    role: str
    action: str
    entity_type: str
    entity_id: uuid.UUID
    university_id: uuid.UUID | None
    old_value: Any | None
    new_value: Any | None
    request_id: uuid.UUID | None
    ip: str | None
    user_agent: str | None
    # Human-readable enrichment (additive; old clients ignore it).
    university_name: str | None = None
    entity_name: str | None = None
    presentation: dict | None = None

    @classmethod
    def from_event(cls, event: AuditEvent) -> "AuditEventRead":
        return cls.from_event_enriched(event, None, None, None)

    @classmethod
    def from_event_enriched(
        cls,
        event: AuditEvent,
        names: dict[str, str] | None,
        university_name: str | None = None,
        entity_name: str | None = None,
    ) -> "AuditEventRead":
        names = names or {}
        resolved_uni = university_name
        if resolved_uni is None and event.university_id is not None:
            resolved_uni = names.get(str(event.university_id).lower())
        if resolved_uni is None and str(event.entity_type or "").lower() == "university":
            # The university row may be physically deleted already; the
            # historic snapshot (old/new `name`) is then the only source.
            # Never fall back to the raw UUID here.
            resolved_uni = entity_display_name(
                event.entity_type, event.entity_id, event.old_value,
                event.new_value, names,
            )
        resolved_entity = entity_name or entity_display_name(
            event.entity_type, event.entity_id, event.old_value,
            event.new_value, names,
        )
        presentation = summarize_event(
            event.action, event.entity_type, event.old_value,
            event.new_value, names, resolved_uni,
        )
        # The actor line never leaks Keycloak sub: presentation consumers
        # use user_name; raw user_id stays available for filtering only.
        presentation["actor_name"] = actor_display_name(
            event.user_name, event.user_id)
        presentation["actor_role"] = event.role
        return cls(
            id=event.id, timestamp=event.created_at, user_id=event.user_id,
            user_name=event.user_name, role=event.role, action=event.action,
            entity_type=event.entity_type, entity_id=event.entity_id,
            university_id=event.university_id, old_value=public_audit_value(event.old_value),
            new_value=public_audit_value(event.new_value), request_id=event.request_id,
            ip=event.ip_address, user_agent=event.user_agent,
            university_name=resolved_uni, entity_name=resolved_entity,
            presentation=presentation,
        )


class AuditFilterOptionsRead(BaseModel):
    users: list[dict[str, str]]
    universities: list[dict[str, str]]
    actions: list[str]
    entity_types: list[str]


@router.get(
    "/filter-options",
    response_model=AuditFilterOptionsRead,
    summary="Опции фильтров аудита",
    description="Возвращает доступных акторов, вузы, действия и типы сущностей для фильтров журнала. Требуется право audit.read; выборка ограничена scope пользователя.",
)
def audit_filter_options(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("audit.read")),
) -> AuditFilterOptionsRead:
    visible = apply_university_scope(
        select(AuditEvent.user_id, AuditEvent.user_name, AuditEvent.university_id),
        AuditEvent.university_id, user,
    ).subquery()
    actors = db.execute(
        select(visible.c.user_id, func.max(visible.c.user_name))
        .group_by(visible.c.user_id).order_by(visible.c.user_id).limit(500)
    ).all()
    universities = db.execute(
        select(University.id, University.name)
        .where(University.id.in_(select(visible.c.university_id).where(visible.c.university_id.is_not(None))))
        .order_by(University.name).limit(500)
    ).all()
    return AuditFilterOptionsRead(
        users=[{"id": actor_id, "name": name or actor_id} for actor_id, name in actors],
        universities=[{"id": str(uid), "name": name} for uid, name in universities],
        actions=[action.value for action in AuditAction],
        entity_types=[entity.value for entity in AuditEntityType],
    )


@router.get(
    "/events", response_model=PaginatedResponse[AuditEventRead],
    summary="Список событий аудита",
    description="Возвращает постраничный журнал событий с фильтрами по датам, пользователям, вузам, действиям, типам сущностей и поиску. Требуется право audit.read.",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
               422: {"model": ErrorResponse}},
)
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: list[str] | None = Query(default=None),
    university_id: list[uuid.UUID] | None = Query(default=None),
    action: list[AuditAction] | None = Query(default=None),
    entity_type: list[AuditEntityType] | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("audit.read")),
) -> PaginatedResponse[AuditEventRead]:
    if date_from and date_to and date_from > date_to:
        raise SecurityError(ErrorCode.VALIDATION_ERROR)
    scope = get_data_scope(user)
    if university_id and not scope.is_all and any(not scope.allows(uid) for uid in university_id):
        raise SecurityError(ErrorCode.FORBIDDEN)
    stmt = apply_university_scope(select(AuditEvent), AuditEvent.university_id, user)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.outerjoin(
            University, University.id == AuditEvent.university_id
        ).where(or_(
            AuditEvent.user_name.ilike(term),
            University.name.ilike(term),
            # Object names live inside old/new JSON snapshots; matching
            # their text form keeps search to a single statement.
            cast(AuditEvent.old_value, String).ilike(term),
            cast(AuditEvent.new_value, String).ilike(term),
        ))
    if date_from:
        stmt = stmt.where(AuditEvent.created_at >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        stmt = stmt.where(AuditEvent.created_at < datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc))
    if user_id:
        stmt = stmt.where(AuditEvent.user_id.in_(user_id))
    if university_id:
        stmt = stmt.where(AuditEvent.university_id.in_(university_id))
    if action:
        stmt = stmt.where(AuditEvent.action.in_([a.value for a in action]))
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type.in_([e.value for e in entity_type]))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).scalars().all()
    # Batch name resolution: a constant number of queries no matter the
    # page size (never one query per row).
    names = resolve_names(db, list(rows))
    items = []
    for event in rows:
        uni_name = None
        if event.university_id is not None:
            uni_name = names.get(str(event.university_id).lower())
        entity_name = entity_display_name(
            event.entity_type, event.entity_id, event.old_value,
            event.new_value, names,
        )
        if entity_name is None:
            entity_name = fallback_name(
                event.entity_type, deleted=str(event.action).upper() == "DELETE")
        items.append(AuditEventRead.from_event_enriched(event, names, uni_name, entity_name))
    return PaginatedResponse(
        items=items,
        total=total, page=page, page_size=page_size,
    )
