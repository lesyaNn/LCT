"""University DTOs: list/detail/create/update + passport (P1-02-01).

Contract for frontend (P3) and other services. Counter/aggregate fields
(``programs_count``-style, passport lists) are populated by services at
read time — never stored. Statuses use the shared enums from
``app.schemas.common``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.catalog import ProductShort, ProgramShort
from app.schemas.common import (
    DocumentStatus,
    DocumentType,
    HealthScoreStatus,
    LicenseStatus,
    MeetingType,
    TeacherReadiness,
)


# ------------------------------------------------------- nested short DTOs


class ResponsibleShort(BaseModel):
    id: uuid.UUID
    full_name: str

    model_config = {"from_attributes": True}


class ResponsibleDetail(ResponsibleShort):
    email: str | None = None
    phone: str | None = None
    role: str | None = None


class StageShort(BaseModel):
    """Workflow stage pointer. Full stage schemas are owned by P2."""

    code: str = Field(examples=["negotiation"])
    name: str = Field(examples=["Переговоры"])


class TeacherShort(BaseModel):
    id: uuid.UUID
    full_name: str
    position: str | None = None
    readiness: TeacherReadiness | None = None

    model_config = {"from_attributes": True}


class StudentsSummary(BaseModel):
    total: int = 0
    active: int = 0
    graduated: int = 0
    expelled: int = 0
    academic_leave: int = 0


class LicenseShort(BaseModel):
    """Passport-oriented license row. ``status``/``days_to_expiry`` are
    derived (P1-06-02) and filled by the service at serialization time."""

    id: uuid.UUID
    license_number: str
    product_name: str | None = None
    status: LicenseStatus = LicenseStatus.ACTIVE
    expires_at: date | None = None
    days_to_expiry: int | None = None

    model_config = {"from_attributes": True}


class ContractShort(BaseModel):
    id: uuid.UUID
    contract_number: str
    status: str = "active"
    expires_at: date | None = None
    days_to_expiry: int | None = None

    model_config = {"from_attributes": True}


class DocumentShort(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    title: str
    status: DocumentStatus | None = None
    expires_at: date | None = None

    model_config = {"from_attributes": True}


class MeetingShort(BaseModel):
    id: uuid.UUID
    meeting_type: MeetingType = MeetingType.ONLINE
    subject: str
    meeting_at: datetime

    model_config = {"from_attributes": True}


class InteractionShort(BaseModel):
    id: uuid.UUID
    content: str
    is_internal: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowSummary(BaseModel):
    """Aggregated workflow state. Full workflow schemas are owned by P2."""

    current_stage: StageShort | None = None
    stages_total: int = 0
    stages_completed: int = 0


# ------------------------------------------------------------------ base


class UniversityBase(BaseModel):
    name: str = Field(min_length=1, max_length=512, examples=["МГТУ им. Баумана"])
    city: str | None = Field(default=None, max_length=256, examples=["Москва"])


class UniversityCreate(UniversityBase):
    pass


class UniversityUpdate(BaseModel):
    """All fields optional — partial update (PATCH)."""

    name: str | None = Field(default=None, min_length=1, max_length=512)
    city: str | None = Field(default=None, max_length=256)


# ------------------------------------------------------------------ reads


class UniversityList(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None = None
    responsible: ResponsibleShort | None = None
    current_stage: StageShort | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_status: str | None = None
    last_interaction_at: datetime | None = None

    model_config = {"from_attributes": True}


class UniversityDetail(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None = None
    responsible: ResponsibleDetail | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_status: HealthScoreStatus | str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UniversityPassport(BaseModel):
    """Aggregated schema for GET /universities/{id}/passport."""

    university: UniversityDetail
    programs: list[ProgramShort] = Field(default_factory=list)
    teachers: list[TeacherShort] = Field(default_factory=list)
    students_summary: StudentsSummary = Field(default_factory=StudentsSummary)
    products: list[ProductShort] = Field(default_factory=list)
    licenses: list[LicenseShort] = Field(default_factory=list)
    contracts: list[ContractShort] = Field(default_factory=list)
    documents: list[DocumentShort] = Field(default_factory=list)
    meetings: list[MeetingShort] = Field(default_factory=list)
    responsibles: list[ResponsibleShort] = Field(default_factory=list)
    workflow_summary: WorkflowSummary = Field(default_factory=WorkflowSummary)
    last_interactions: list[InteractionShort] = Field(default_factory=list)


__all__ = [
    "ContractShort",
    "DocumentShort",
    "InteractionShort",
    "LicenseShort",
    "MeetingShort",
    "ResponsibleDetail",
    "ResponsibleShort",
    "StageShort",
    "StudentsSummary",
    "TeacherShort",
    "UniversityBase",
    "UniversityCreate",
    "UniversityDetail",
    "UniversityList",
    "UniversityPassport",
    "UniversityUpdate",
    "WorkflowSummary",
]
