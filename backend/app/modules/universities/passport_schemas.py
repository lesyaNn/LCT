"""University passport DTOs."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field
from app.schemas.location import CityLocation

from app.models.enums import (
    UniversityProductStatus,
    UniversityProgramStatus,
)


class ProgramShort(BaseModel):
    id: uuid.UUID
    name: str
    direction_name: str
    status: UniversityProgramStatus
    launch_date: date | None = None
    responsible_name: str | None = None

    model_config = {"from_attributes": True}


class LicenseShort(BaseModel):
    id: uuid.UUID
    license_number: str
    product_name: str
    vendor_name: str
    signed_at: date
    expires_at: date
    status: str
    transfer_status: str
    days_to_expiry: int | None = None
    contract_number: str | None = None

    model_config = {"from_attributes": True}


class ProductShort(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    vendor_name: str
    status: UniversityProductStatus
    license: LicenseShort | None = None

    model_config = {"from_attributes": True}


class ContractShort(BaseModel):
    """Additive P1-04-03 field on UniversityPassport (never frozen-removal)."""

    id: uuid.UUID
    contract_number: str
    signed_at: date
    expires_at: date | None = None
    status: str
    vendor_name: str

    model_config = {"from_attributes": True}


class DocumentShort(BaseModel):
    id: uuid.UUID
    document_type: str
    title: str
    file_name: str
    file_available: bool = False
    file_size: int = 0
    mime_type: str = ""
    signed_at: date | None = None
    expires_at: date | None = None
    status: str
    uploaded_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDocuments(BaseModel):
    items: list[DocumentShort]
    total: int
    page: int
    page_size: int
    types: list[str]


class MeetingShort(BaseModel):
    id: uuid.UUID
    meeting_type: str
    subject: str
    participants: list[str] = Field(default_factory=list)
    outcome: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    meeting_at: datetime
    created_by: str

    model_config = {"from_attributes": True}


class ResponsibleShort(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None = None
    role: str = ""

    model_config = {"from_attributes": True}


class TimelineItem(BaseModel):
    id: str
    type: str  # meeting | document | note | workflow_transition
    title: str
    description: str | None = None
    author: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowSummary(BaseModel):
    """P2 integration adapter shape.

    When P2 workflow instances are unavailable the service returns a safe
    fallback (all-None/zero) instead of fabricating engine data.
    """

    instance_id: str | None = None
    template_name: str | None = None
    # Legacy mocks carry the richer ``{code, name}`` pointer while the
    # evolved passport service may emit a stage name.  Accept both wire
    # shapes during the compatibility window; P2 owns the full stage DTO.
    current_stage: str | dict[str, str] | None = None
    progress_percent: float = 0.0
    overdue_stages: int = 0
    next_due_date: date | None = None

    model_config = {"from_attributes": True}


class UniversityBrief(CityLocation):
    id: uuid.UUID
    name: str
    city: str | None = None

    model_config = {"from_attributes": True}


class AuditEventShort(BaseModel):
    """P1-04-05 optional block item (``?include=audit``).

    Field set mirrors the P5 canonical UUID audit identity while retaining
    the P1 optional block's field names and shape.
    """

    id: uuid.UUID
    user_id: str
    entity_type: str
    entity_id: uuid.UUID
    action: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedPrograms(BaseModel):
    """P1-04-06 paginated subresource (SQL LIMIT/OFFSET + COUNT)."""

    items: list[ProgramShort] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0

    model_config = {"from_attributes": True}


class UniversityPassport(BaseModel):
    university: UniversityBrief
    programs: list[ProgramShort] = Field(default_factory=list)
    products: list[ProductShort] = Field(default_factory=list)
    licenses: list[LicenseShort] = Field(default_factory=list)
    contracts: list[ContractShort] = Field(default_factory=list)
    documents: list[DocumentShort] = Field(default_factory=list)
    meetings: list[MeetingShort] = Field(default_factory=list)
    responsibles: list[ResponsibleShort] = Field(default_factory=list)
    workflow_summary: WorkflowSummary = Field(default_factory=WorkflowSummary)
    last_interactions: list[TimelineItem] = Field(default_factory=list)
    # Optional blocks (only populated via ?include=...).
    recent_audit: list[AuditEventShort] | None = None

    model_config = {"from_attributes": True}
