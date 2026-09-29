"""P1-07-01 meetings HTTP API (mounted under /api/v1).

Thin routes: path/body params -> RBAC -> service -> DTO. No SQL and no
business logic here. RBAC reuses the frozen permission names:
``university.read`` for GET, ``university.edit`` for mutations.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.audit.service import get_audit_db
from app.modules.meetings import service
from app.modules.meetings.schemas import MeetingCreate, MeetingRead, MeetingUpdate
from app.schemas.common import PaginatedResponse

router = APIRouter()

READ = require_permission("university.read")
WRITE = require_permission("university.edit")


@router.post(
    "/universities/{university_id}/meetings",
    response_model=MeetingRead,
    status_code=201,
    tags=["Universities"],
    summary="Создать встречу",
    description="Создаёт встречу для вуза. Требуется право university.edit.",
)
def create_meeting(
    university_id: uuid.UUID,
    data: MeetingCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> MeetingRead:
    return service.create_meeting(
        db, university_id, data, actor_sub=user.id, user=user
    )


@router.get(
    "/universities/{university_id}/meetings",
    response_model=PaginatedResponse[MeetingRead],
    tags=["Universities"],
    summary="Список встреч вуза",
    description="Возвращает страницу встреч вуза, новые первыми. Требуется право university.read.",
)
def list_meetings(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[MeetingRead]:
    items, total = service.list_meeting_page(
        db, university_id, page=page, page_size=page_size, user=user
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/meetings/{meeting_id}",
    response_model=MeetingRead,
    tags=["Universities"],
    summary="Получить встречу по id",
    description="Возвращает встречу по id. Требуется право university.read.",
)
def get_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> MeetingRead:
    return service.get_meeting(db, meeting_id, user=user)


@router.patch(
    "/meetings/{meeting_id}",
    response_model=MeetingRead,
    tags=["Universities"],
    summary="Частично обновить встречу",
    description="Частично обновляет встречу. Требуется право university.edit.",
)
def patch_meeting(
    meeting_id: uuid.UUID,
    data: MeetingUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> MeetingRead:
    return service.patch_meeting(db, meeting_id, data, user=user)


@router.delete(
    "/meetings/{meeting_id}",
    status_code=204,
    response_model=None,
    tags=["Universities"],
    summary="Удалить встречу",
    description="Удаляет встречу (связи с документами каскадируются). Требуется право university.edit.",
)
def delete_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_meeting(db, meeting_id, user=user)
