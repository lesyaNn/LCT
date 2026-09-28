"""University-scoped educator API contracts."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TeacherCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=512)
    email: str = Field(min_length=3, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    position: str = Field(default="", max_length=256)


class TeacherUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=512)
    email: str | None = Field(default=None, min_length=3, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    position: str | None = Field(default=None, max_length=256)


class QualificationCreate(BaseModel):
    qualification_name: str = Field(min_length=1, max_length=512)
    obtained_at: date
    expires_at: date | None = None
    document_ref: str | None = Field(default=None, max_length=1024)


class CertificateCreate(BaseModel):
    certificate_name: str = Field(min_length=1, max_length=512)
    issued_by: str = Field(default="", max_length=512)
    issued_at: date
    expires_at: date | None = None
    is_mandatory: bool = False
    program_id: UUID | None = None
    document_ref: str | None = Field(default=None, max_length=1024)


class TeacherProgramCreate(BaseModel):
    program_id: UUID
    can_teach: bool = True
    assigned_at: date


class QualificationRead(QualificationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class CertificateRead(CertificateCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class TeacherProgramRead(TeacherProgramCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TeacherRead(TeacherCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    university_id: UUID
    created_at: datetime
    updated_at: datetime
    qualifications: list[QualificationRead] = Field(default_factory=list)
    certificates: list[CertificateRead] = Field(default_factory=list)
    teacher_programs: list[TeacherProgramRead] = Field(default_factory=list)
