"""Dev-2 response contract (filter DTO stays with Dev-1)."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class KPI(BaseModel):
    universities: int = 0
    average_health_score: float = 0
    red_universities: int = 0
    yellow_universities: int = 0
    green_universities: int = 0
    overdue_stages: int = 0
    expiring_licenses: int = 0
    teacher_readiness_issues: int = 0
    active_programs: int = 0
    launched_programs: int = 0


class HealthBucket(BaseModel):
    range: str
    count: int


class WorkflowBucket(BaseModel):
    stage: str
    count: int


class ProgramBucket(BaseModel):
    status: str
    count: int


class LicenseWarning(BaseModel):
    university: str
    product: str
    expires_at: date
    days_left: int


class TeacherWarning(BaseModel):
    university: str
    teacher: str
    certificate: str
    expires_at: date
    days_left: int


class OverdueItem(BaseModel):
    type: Literal["stage", "task"]
    university: str
    stage: str | None = None
    task: str | None = None
    days_overdue: int


class TrendPoint(BaseModel):
    date: date
    avg_score: float


class Overview(BaseModel):
    kpi: KPI
    health_distribution: list[HealthBucket]
    workflow_distribution: list[WorkflowBucket]
    program_statuses: list[ProgramBucket]
    expiring_licenses: list[LicenseWarning]
    teacher_readiness: list[TeacherWarning]
    overdue_items: list[OverdueItem]
    health_trend: list[TrendPoint]


class MatrixRow(BaseModel):
    id: UUID
    name: str
    city: str | None


class MatrixColumn(BaseModel):
    id: UUID
    name: str
    direction: str


class MatrixCell(BaseModel):
    university_id: UUID
    program_id: UUID
    # Archived is explicit: an existing archived link must NOT become not_used.
    status: Literal["not_used", "planned", "in_progress", "launched", "risk", "archived"]
    health_score: int | None
    risk_level: Literal["none", "unknown", "low", "medium", "high"]
    teacher_readiness: float | None
    license_status: str | None
    workflow_progress: float | None
    overdue_count: int
    next_milestone: str | None
    workflow_scope: Literal["university"] = "university"


class Matrix(BaseModel):
    rows: list[MatrixRow]
    columns: list[MatrixColumn]
    cells: list[MatrixCell]
    legend: dict[str, str] = Field(default_factory=dict)
