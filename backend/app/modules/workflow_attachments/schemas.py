"""P2-05 attachment DTOs: only factual ``workflow_attachments`` columns."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentRead(BaseModel):
    """Metadata response. Never carries storage_key or any host path."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instance_id: uuid.UUID
    stage_id: uuid.UUID | None = None
    original_filename: str
    mime_type: str
    file_size: int
    uploaded_by_keycloak_sub: str
    created_at: datetime
    updated_at: datetime
