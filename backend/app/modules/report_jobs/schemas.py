from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ReportFormat = Literal["xlsx", "pdf", "json"]
JobStatus = Literal["queued", "building", "ready", "failed"]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: ReportFormat
    # Dev-1 owns UnifiedFilter and column validation, not this transport envelope.
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list, max_length=100)


class JobAccepted(BaseModel):
    job_id: UUID
    status: Literal["queued"] = "queued"


class JobRead(BaseModel):
    job_id: UUID
    status: JobStatus
    progress: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    file_size: int | None
    error_message: str | None
    download_url: str | None
