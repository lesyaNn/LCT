"""P2-02-01/02 DTOs: workflow templates + stages.

* Create schemas never accept system fields (``id``/timestamps).
* Update schemas are all-optional; routers forward ``model_fields_set`` so
  the service can apply ``exclude_unset`` semantics (explicit ``null`` on a
  nullable field clears it, an absent field leaves it untouched).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from app.schemas.validation import NonBlankText


# ---------------------------------------------------------------- templates


class TemplateCreate(BaseModel):
    name: NonBlankText = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None)
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: NonBlankText | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    is_active: bool | None = None


class TemplateRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------- stages


class StageCreate(BaseModel):
    name: NonBlankText = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None)
    order_index: int | None = Field(
        default=None, ge=1, description="1-based position; omitted = append"
    )
    is_required: bool = True
    is_active: bool = True
    sla_days: int | None = Field(default=None, ge=0)


class StageUpdate(BaseModel):
    name: NonBlankText | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    order_index: int | None = Field(default=None, ge=1)
    is_required: bool | None = None
    is_active: bool | None = None
    sla_days: int | None = Field(default=None, ge=0)


class StageRead(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    name: str
    description: str | None
    order_index: int
    is_required: bool
    is_active: bool
    sla_days: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateDetail(TemplateRead):
    stages: list[StageRead] = Field(default_factory=list)
