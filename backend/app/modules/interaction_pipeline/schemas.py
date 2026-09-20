from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TemplateStageCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)
    description: str = ""
    order_index: int = Field(ge=0)
    is_required: bool = True
    default_duration_days: int = Field(default=7, ge=0, le=3650)


class TemplateStageRead(TemplateStageCreate):
    id: uuid.UUID
    template_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowTemplateCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)
    description: str = ""
    stages: list[TemplateStageCreate] = Field(min_length=1)


class WorkflowTemplateRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    version: int
    is_active: bool
    stages: list[TemplateStageRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowInstanceCreate(BaseModel):
    template_id: uuid.UUID
    university_id: uuid.UUID
    program_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    due_date: datetime | None = None


class WorkflowInstanceStageRead(BaseModel):
    id: uuid.UUID
    template_stage_id: uuid.UUID
    code: str
    name: str
    order_index: int
    is_required: bool
    status: str
    due_date: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    skipped_at: datetime | None
    completed_by_keycloak_sub: str | None
    is_overdue: bool
    days_overdue: int


class WorkflowInstanceRead(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    university_id: uuid.UUID
    program_id: uuid.UUID | None
    product_id: uuid.UUID | None
    status: str
    revision: int
    started_at: datetime
    due_date: datetime | None
    completed_at: datetime | None
    current_stage_code: str | None
    progress_percent: float
    is_overdue: bool
    days_overdue: int
    stages: list[WorkflowInstanceStageRead] = Field(default_factory=list)


class TransitionRequest(BaseModel):
    target_stage_code: str = Field(min_length=1, max_length=64)
    comment: str = Field(min_length=1, max_length=10000)
    expected_revision: int | None = Field(default=None, ge=0)


class WorkflowTransitionRead(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    action: str
    actor_keycloak_sub: str
    comment: str
    revision: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    instance_stage_id: uuid.UUID | None = None


class WorkflowCommentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class WorkflowCommentRead(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    instance_stage_id: uuid.UUID | None
    author_keycloak_sub: str
    content: str
    edited_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    description: str = ""
    instance_stage_id: uuid.UUID | None = None
    assignee_keycloak_sub: str | None = Field(default=None, max_length=256)
    due_date: datetime | None = None


class WorkflowTaskRead(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    instance_stage_id: uuid.UUID | None
    title: str
    description: str
    assignee_keycloak_sub: str | None
    due_date: datetime | None
    status: str
    completed_at: datetime | None
    completed_by_keycloak_sub: str | None
    created_by_keycloak_sub: str
    created_at: datetime
    updated_at: datetime
    is_overdue: bool
    days_overdue: int

    model_config = {"from_attributes": True}


class WorkflowAttachmentCreate(BaseModel):
    document_id: uuid.UUID
    instance_stage_id: uuid.UUID | None = None


class WorkflowAttachmentRead(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    instance_stage_id: uuid.UUID | None
    document_id: uuid.UUID
    created_by_keycloak_sub: str
    created_at: datetime

    model_config = {"from_attributes": True}
