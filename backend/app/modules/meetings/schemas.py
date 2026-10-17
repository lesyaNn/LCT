"""P1-07-01: meeting DTOs (Create/Update/Read).

``participants`` mirrors the model (JSON array, free-form objects).
``meeting_at`` must be timezone-aware (P1-01-05).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import MeetingType


class MeetingCreate(BaseModel):
    meeting_type: MeetingType = MeetingType.ONLINE
    subject: str = Field(min_length=1, max_length=1024)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    outcome: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    meeting_at: datetime

    @field_validator("meeting_at")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("meeting_at must be timezone-aware")
        return value


class MeetingUpdate(BaseModel):
    meeting_type: MeetingType | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=1024)
    participants: list[dict[str, Any]] | None = None
    outcome: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    meeting_at: datetime | None = None

    @field_validator("meeting_at")
    @classmethod
    def _tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("meeting_at must be timezone-aware")
        return value


class MeetingRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    meeting_type: str | None
    subject: str
    participants: list = Field(default_factory=list)
    outcome: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    meeting_at: datetime | None
    workflow_instance_stage_id: uuid.UUID | None = None
    workflow_instance_id: uuid.UUID | None = None
    workflow_stage_name: str | None = None
    created_by_keycloak_sub: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


__all__ = ["MeetingCreate", "MeetingRead", "MeetingUpdate"]
