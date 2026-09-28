"""P2-02-03/P2-06-01 DTOs: workflow instance creation + runtime detail.

* Create schemas never accept system fields (``id``/timestamps).
* ``is_overdue``/``days_overdue`` are derived via the shared
  ``overdue.compute_overdue`` helper (service layer); they are response-only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InstanceCreate(BaseModel):
    university_id: uuid.UUID
    template_id: uuid.UUID
    program_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    responsible_id: uuid.UUID | None = Field(default=None)


class InstanceResponsibleUpdate(BaseModel):
    responsible_id: uuid.UUID | None = Field(default=None)


class InstanceStageDueDateUpdate(BaseModel):
    due_date: date | None


class WorkflowActivityRead(BaseModel):
    id: uuid.UUID
    type: Literal["responsible_changed", "deadline_changed"]
    created_at: datetime
    actor_name: str
    stage_name: str
    title: str


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
    tasks_total: int = 0
    tasks_completed: int = 0


class InstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    university_id: uuid.UUID
    template_id: uuid.UUID
    program_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
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
    university_name: str | None = None
    university_city: str | None = None
    program_name: str | None = None
    product_name: str | None = None
    responsible_name: str | None = None
    responsible_email: str | None = None
    responsible_phone: str | None = None


class WorkflowTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instance_id: uuid.UUID
    stage_id: uuid.UUID | None
    title: str
    description: str
    responsible_id: uuid.UUID | None
    deadline: date | None
    status: str
    priority: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowTaskCreate(BaseModel):
    stage_id: uuid.UUID
    title: str = Field(min_length=1, max_length=512)


class WorkflowTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    status: Literal["open", "done"] | None = None


class AllowedTransitionRead(BaseModel):
    id: uuid.UUID
    order_index: int
    name: str
