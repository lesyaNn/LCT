"""Current user's in-app notification inbox."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.notifications import service
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    priority: Literal["INFO", "WARNING", "CRITICAL"]
    title: str
    message: str
    entity_type: str
    entity_id: str
    university_id: uuid.UUID | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    total: int
    limit: int
    offset: int


@router.get("", response_model=NotificationPage)
def list_notifications(
    filter: Literal["all", "unread", "attention"] = "all",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> NotificationPage:
    rows, total = service.list_for_user(db, user, filter=filter, limit=limit, offset=offset)
    return NotificationPage(items=[NotificationRead.model_validate(row) for row in rows],
                            total=total, limit=limit, offset=offset)


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)) -> dict[str, int]:
    return {"count": service.unread_count(db, user)}


@router.patch("/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)) -> None:
    if not service.mark_read(db, user, notification_id):
        raise BusinessException(ErrorCode.NOT_FOUND)


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)) -> dict[str, int]:
    return {"updated": service.mark_all_read(db, user)}
