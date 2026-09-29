"""Analytics response contract."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class KPI(BaseModel):
    universities: int = 0
    overdue_stages: int = 0
    expiring_licenses: int = 0
    active_programs: int = 0
    launched_programs: int = 0


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


class OverdueItem(BaseModel):
    type: Literal["stage", "task"]
    id: str | None = None
    university_id: UUID | None = None
    university: str
    stage: str | None = None
    task: str | None = None
    days_overdue: int


class TrendPoint(BaseModel):
    date: date
    avg_score: float = 0


class LaunchPoint(BaseModel):
    month: str
    actual: int = 0
    planned: int = 0


class Overview(BaseModel):
    kpi: KPI
    workflow_distribution: list[WorkflowBucket] = Field(default_factory=list)
    program_statuses: list[ProgramBucket] = Field(default_factory=list)
    expiring_licenses: list[LicenseWarning] = Field(default_factory=list)
    overdue_items: list[OverdueItem] = Field(default_factory=list)
    health_trend: list[TrendPoint] = Field(default_factory=list)
    launch_dynamics: list[LaunchPoint] = Field(default_factory=list)


class MatrixRow(BaseModel):
    id: UUID
    name: str
    city: str | None
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_level: Literal["stable", "attention", "critical", "no_data"] = "no_data"
    started_programs: int = 0
    total_programs: int = 0


class MatrixColumn(BaseModel):
    id: UUID
    name: str
    direction: str


class MatrixCell(BaseModel):
    university_id: UUID
    program_id: UUID
    status: Literal["not_used", "planned", "in_progress", "launched", "risk", "archived"]
    health_state: Literal["HEALTHY", "ATTENTION", "CRITICAL", "NOT_STARTED", "COMPLETED", "NOT_LINKED"] = "NOT_LINKED"
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_level: Literal["stable", "attention", "critical", "no_data"] = "no_data"
    health_factors: list[str] = Field(default_factory=list)
    risk_level: Literal["none", "low", "high"] = "none"
    license_status: str | None = None
    workflow_progress: float | None = None
    overdue_count: int = 0
    next_milestone: str | None = None
    workflow_scope: Literal["university"] = "university"


class Matrix(BaseModel):
    rows: list[MatrixRow]
    columns: list[MatrixColumn]
    cells: list[MatrixCell]
    legend: dict[str, str] = Field(default_factory=dict)
