"""Read-only education indicators from LMS and website data."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProgramEducationRead(BaseModel):
    program_id: UUID
    program_name: str
    learners_count: int
    applications_count: int
    flows_count: int
    learner_source: str | None
    learner_synced_at: datetime | None
    applications_synced_at: datetime | None


class UniversityEducationRead(BaseModel):
    university_id: UUID
    learners_count: int
    applications_count: int
    flows_count: int
    programs: list[ProgramEducationRead]
