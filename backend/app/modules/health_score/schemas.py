"""Public operational Health Score response."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

HealthLevel = Literal["stable", "attention", "critical", "no_data"]


class HealthFactor(BaseModel):
    label: str


class HealthObservation(BaseModel):
    date: datetime
    score: int | None = Field(ge=0, le=100)
    level: HealthLevel


class ProgramHealth(BaseModel):
    program_id: UUID
    program_name: str
    state: Literal["HEALTHY", "ATTENTION", "CRITICAL", "NOT_STARTED", "COMPLETED"]
    score: int | None = Field(ge=0, le=100)
    workflow_instance_id: UUID | None
    current_stage: str | None
    factors: list[str]
    workflow_progress: float | None
    stages_completed: int
    stages_total: int
    deadline: date | None
    overdue_days: int


class UniversityHealthScore(BaseModel):
    university_id: UUID
    score: int | None = Field(ge=0, le=100)
    level: HealthLevel
    started_programs: int
    active_workflows: int
    total_programs: int
    attention_count: int
    critical_count: int
    factors: list[HealthFactor]
    positive_factors: list[HealthFactor]
    history: list[HealthObservation]
    programs: list[ProgramHealth]
    calculated_at: datetime
