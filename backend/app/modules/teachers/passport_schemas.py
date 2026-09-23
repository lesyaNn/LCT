"""P1-05 teacher passport DTOs (production contract).

Source of truth for ``GET /api/v1/teachers/{id}/passport`` response shape.

Field policy: every field maps 1:1 to a real column of the canonical schema
(``teachers`` / ``teacher_qualifications`` / ``teacher_certificates`` /
``teacher_programs`` + ``it_programs`` / ``it_directions``); no invented
fields. Derived fields (``readiness``, ``readiness_reasons``,
``next_qualification_date``) come from the canonical
:func:`compute_teacher_readiness` formula — never recomputed here.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import TeacherReadiness
from app.modules.universities.passport_schemas import UniversityBrief

__all__ = [
    "UniversityBrief",
    "TeacherBlock",
    "QualificationRead",
    "CertificateProgramShort",
    "CertificateRead",
    "TeacherProgramRead",
    "TeacherProgramLink",
    "TeacherPassport",
]


class TeacherBlock(BaseModel):
    """Real ``teachers`` row (no invented fields)."""

    id: uuid.UUID
    university_id: uuid.UUID
    full_name: str
    email: str
    position: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QualificationRead(BaseModel):
    """Real ``teacher_qualifications`` row."""

    id: uuid.UUID
    qualification_name: str
    obtained_at: date
    expires_at: date | None = None
    document_ref: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CertificateProgramShort(BaseModel):
    """Brief linked ``it_programs`` row (``None`` when ``program_id`` is NULL)."""

    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class CertificateRead(BaseModel):
    """Real ``teacher_certificates`` row + optional linked program (no N+1)."""

    id: uuid.UUID
    certificate_name: str
    issued_by: str
    issued_at: date
    expires_at: date | None = None
    is_mandatory: bool = False
    program_id: uuid.UUID | None = None
    program: CertificateProgramShort | None = None
    document_ref: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeacherProgramLink(BaseModel):
    """Linked ``it_programs`` row with its ``it_directions`` name."""

    id: uuid.UUID
    name: str
    direction_name: str

    model_config = {"from_attributes": True}


class TeacherProgramRead(BaseModel):
    """Real ``teacher_programs`` link row (never ``UniversityProgram`` status)."""

    id: uuid.UUID
    program: TeacherProgramLink
    can_teach: bool = True
    assigned_at: date

    model_config = {"from_attributes": True}


class TeacherPassport(BaseModel):
    """Full teacher passport (P1-05-01/02/03).

    Decision (P1-05-02, MVP): no separate ``teacher_trainings`` table —
    professional development is covered by qualifications/certificates,
    so there is intentionally no ``trainings`` block here.
    """

    teacher: TeacherBlock
    university: UniversityBrief
    qualifications: list[QualificationRead] = Field(default_factory=list)
    certificates: list[CertificateRead] = Field(default_factory=list)
    programs: list[TeacherProgramRead] = Field(default_factory=list)
    readiness: TeacherReadiness
    readiness_reasons: list[str] = Field(default_factory=list)
    next_qualification_date: date | None = None

    model_config = {"from_attributes": True}
