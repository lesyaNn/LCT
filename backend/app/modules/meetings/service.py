"""P1-07-01 service: meeting rows -> DTOs, NotFound mapping.

No SQL outside this module's functions. UNIQUE/FK violations surface as
``IntegrityError`` and are mapped centrally to HTTP 409 — never caught
per-endpoint, never leaked to the client.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.core.permissions import user_permissions
from app.models.catalog import University
from app.models.interactions import Meeting
from app.modules.meetings.schemas import MeetingCreate, MeetingRead, MeetingUpdate


def _check_scope(user, university_id: uuid.UUID) -> None:
    """University-scope gate (same semantics as workflow attachments).

    Admins (``*``) skip scoping; tokens without the optional
    ``university_ids`` claim keep global RBAC behaviour; scoped users
    asking for a foreign university get 403.
    """
    if "*" in user_permissions(user):
        return
    scope = getattr(user, "university_ids", None)
    if scope is not None and str(university_id) not in set(scope):
        raise HTTPException(status_code=403, detail="Forbidden: other university")


def _get_university_or_404(db: Session, university_id: uuid.UUID) -> University:
    university = db.get(University, university_id)
    if university is None:
        raise NotFound("University not found")
    return university


def _get_meeting_or_404(db: Session, meeting_id: uuid.UUID) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise NotFound("Meeting not found")
    return meeting


def create_meeting(
    db: Session,
    university_id: uuid.UUID,
    data: MeetingCreate,
    *,
    actor_sub: str,
    user,
) -> MeetingRead:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    meeting = Meeting(
        university_id=university_id,
        meeting_type=data.meeting_type.value,
        subject=data.subject,
        participants=data.participants,
        outcome=data.outcome,
        next_action=data.next_action,
        next_action_due=data.next_action_due,
        meeting_at=data.meeting_at,
        created_by_keycloak_sub=actor_sub or "",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return MeetingRead.model_validate(meeting)


def list_meeting_page(
    db: Session,
    university_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    user,
) -> tuple[list[MeetingRead], int]:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    base = select(Meeting).where(Meeting.university_id == university_id)
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Meeting.meeting_at.desc(), Meeting.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return [MeetingRead.model_validate(r) for r in rows], total


def get_meeting(db: Session, meeting_id: uuid.UUID, *, user) -> MeetingRead:
    meeting = _get_meeting_or_404(db, meeting_id)
    _check_scope(user, meeting.university_id)
    return MeetingRead.model_validate(meeting)


def patch_meeting(
    db: Session, meeting_id: uuid.UUID, data: MeetingUpdate, *, user
) -> MeetingRead:
    meeting = _get_meeting_or_404(db, meeting_id)
    _check_scope(user, meeting.university_id)
    fields = data.model_fields_set
    if "meeting_type" in fields and data.meeting_type is not None:
        meeting.meeting_type = data.meeting_type.value
    for field in (
        "subject",
        "participants",
        "outcome",
        "next_action",
        "next_action_due",
        "meeting_at",
    ):
        if field in fields:
            setattr(meeting, field, getattr(data, field))
    db.commit()
    db.refresh(meeting)
    return MeetingRead.model_validate(meeting)


def delete_meeting(db: Session, meeting_id: uuid.UUID, *, user) -> None:
    meeting = _get_meeting_or_404(db, meeting_id)
    _check_scope(user, meeting.university_id)
    db.delete(meeting)
    db.commit()
