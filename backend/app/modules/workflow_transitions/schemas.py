"""P2-03/P2-04 DTOs: transition requests, history rows and comments."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TransitionRequest(BaseModel):
    """Move the current pointer to another runtime stage (P2-03-01)."""

    target_instance_stage_id: uuid.UUID = Field(
        description="Instance-stage (snapshot row) to move to; must be ahead "
        "of the current row, required rows in between block the move."
    )
    comment: str = Field(
        min_length=1,
        max_length=10000,
        description="Required history comment (stored NOT NULL, P2-03-03).",
    )


class WorkflowStageTransitionRead(BaseModel):
    """One history entry: prev stage + new stage + actor + comment (P2-03-03)."""

    id: uuid.UUID
    instance_id: uuid.UUID
    from_stage_id: uuid.UUID | None = Field(
        default=None, description="NULL for the creation entry."
    )
    to_stage_id: uuid.UUID | None = Field(
        default=None, description="NULL for the closure entry."
    )
    actor_keycloak_sub: str
    comment: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowCommentCreate(BaseModel):
    """New instance comment (P2-04-01)."""

    content: str = Field(min_length=1, max_length=10000)
    stage_id: uuid.UUID | None = Field(
        default=None,
        description="Optional template-stage anchor of this instance's template.",
    )


class WorkflowCommentUpdate(BaseModel):
    """Edited comment content (author <= 15 min, admin any time)."""

    content: str = Field(min_length=1, max_length=10000)


class WorkflowCommentRead(BaseModel):
    """Stored instance comment (P2-04-01)."""

    id: uuid.UUID
    instance_id: uuid.UUID
    stage_id: uuid.UUID | None = None
    author_keycloak_sub: str
    content: str
    is_internal: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
