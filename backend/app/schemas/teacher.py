"""Teacher DTOs + teacher passport (P1-02-03).

``readiness``/``readiness_reasons`` are computed on the backend with
``app.services.teacher_readiness.compute_teacher_readiness`` and filled by
the service at read time — never sent from the frontend, never stored.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.catalog import ProgramShort
from app.schemas.common import TeacherReadiness


# ------------------------------------------------------- nested short DTOs


class TrainingShort(BaseModel):
    id: uuid.UUID
    name: str
    completed_at: date | None = None
    expires_at: date | None = None

    model_config = {"from_attributes": True}


class CertificateShort(BaseModel):
    id: uuid.UUID
    name: str
    issued_by: str = ""
    issued_at: date
    expires_at: date | None = None
    is_mandatory: bool = False
    program_name: str | None = None

    model_config = {"from_attributes": True}


class QualificationShort(BaseModel):
    id: uuid.UUID
    name: str
    obtained_at: date
    expires_at: date | None = None

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ base


class TeacherBase(BaseModel):
    university_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=512, examples=["Петрова А. И."])
    email: str = Field(max_length=512, examples=["petrova@university.local"])
    phone: str | None = Field(default=None, max_length=64)
    position: str = Field(default="", max_length=256, examples=["Доцент"])


class TeacherCreate(TeacherBase):
    pass


class TeacherUpdate(BaseModel):
    """All fields optional — partial update (PATCH)."""

    university_id: uuid.UUID | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=512)
    email: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    position: str | None = Field(default=None, max_length=256)


# ------------------------------------------------------------------ reads


class TeacherList(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    university_name: str | None = None
    full_name: str
    email: str
    position: str = ""
    readiness: TeacherReadiness = TeacherReadiness.READY
    next_qualification_date: date | None = None

    model_config = {"from_attributes": True}


class TeacherDetail(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    university_name: str | None = None
    full_name: str
    email: str
    phone: str | None = None
    position: str = ""
    readiness: TeacherReadiness = TeacherReadiness.READY
    next_qualification_date: date | None = None
    qualifications: list[QualificationShort] = Field(default_factory=list)
    certificates: list[CertificateShort] = Field(default_factory=list)
    allowed_programs: list[ProgramShort] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeacherPassport(BaseModel):
    """Aggregated schema for GET /teachers/{id}/passport."""

    teacher: TeacherDetail
    trainings: list[TrainingShort] = Field(default_factory=list)
    certificates: list[CertificateShort] = Field(default_factory=list)
    qualifications: list[QualificationShort] = Field(default_factory=list)
    allowed_programs: list[ProgramShort] = Field(default_factory=list)
    next_qualification_date: date | None = None
    readiness: TeacherReadiness = TeacherReadiness.READY
    readiness_reasons: list[str] = Field(default_factory=list)


__all__ = [
    "CertificateShort",
    "QualificationShort",
    "TeacherBase",
    "TeacherCreate",
    "TeacherDetail",
    "TeacherList",
    "TeacherPassport",
    "TeacherUpdate",
    "TrainingShort",
]
