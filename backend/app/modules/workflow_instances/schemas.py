"""P2-02-03/P2-06-01 DTOs: workflow instance creation + runtime detail.

* Create schemas never accept system fields (``id``/timestamps).
* ``is_overdue``/``days_overdue`` are derived via the shared
  ``overdue.compute_overdue`` helper (service layer); they are response-only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class InstanceCreate(BaseModel):
    university_id: uuid.UUID
    template_id: uuid.UUID
    responsible_id: uuid.UUID | None = Field(default=None)


class InstanceStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_stage_id: uuid.UUID | None
    order_index: int
    name: str
    description: str | None
    is_required: bool
    status: str
    due_date: date | None
    completed_at: datetime | None
    is_overdue: bool = False
    days_overdue: int = 0
    created_at: datetime
    updated_at: datetime


class InstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    university_id: uuid.UUID
    template_id: uuid.UUID
    current_stage_id: uuid.UUID | None
    current_instance_stage_id: uuid.UUID | None
    responsible_id: uuid.UUID | None
    status: str
    due_date: date | None
    completed_at: datetime | None
    is_overdue: bool = False
    days_overdue: int = 0
    created_at: datetime
    updated_at: datetime


class InstanceDetail(InstanceRead):
    stages: list[InstanceStageRead] = Field(default_factory=list)
