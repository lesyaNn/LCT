"""P1-08-01: student DTOs (Create/Update/Read).

Minimal set, no PII beyond the full name (no email/phone/passport).
``external_id`` is globally unique (natural key for imports).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import StudentStatus


class StudentCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=256)
    program_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=512)
    group_name: str | None = Field(default=None, max_length=256)
    status: StudentStatus = StudentStatus.ACTIVE
    started_at: date
    finished_at: date | None = None


class StudentUpdate(BaseModel):
    program_id: uuid.UUID | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=512)
    group_name: str | None = Field(default=None, max_length=256)
    status: StudentStatus | None = None
    started_at: date | None = None
    finished_at: date | None = None


class StudentRead(BaseModel):
    id: uuid.UUID
    external_id: str
    university_id: uuid.UUID
    program_id: uuid.UUID
    full_name: str
    group_name: str | None = None
    status: str
    started_at: date
    finished_at: date | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


__all__ = ["StudentCreate", "StudentRead", "StudentUpdate"]
