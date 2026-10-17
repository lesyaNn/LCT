"""JSON contract shared by the preview and one-page PDF."""

from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class AgendaSection(BaseModel, Generic[T]):
    items: list[T]
    total: int
    omitted: int = Field(
        ge=0, description="Rows outside this bounded preview; not silently discarded."
    )


class AgendaProgram(BaseModel):
    program_id: UUID
    name: str
    direction: str
    status: Literal["active", "launched"]
    launch_date: date | None


class AgendaLicense(BaseModel):
    license_id: UUID
    license_number: str
    product: str
    expires_at: date
    days_left: int


class AgendaQuestion(BaseModel):
    comment_id: UUID
    instance_id: UUID
    stage_id: UUID | None
    author_keycloak_sub: str | None = None
    content: str
    created_at: datetime


class MeetingAgenda(BaseModel):
    university_id: UUID
    university_name: str
    city: str | None
    instance_id: UUID
    stage_id: UUID = Field(description="Runtime instance stage, not a template stage.")
    stage_name: str
    stage_order: int
    generated_at: datetime
    as_of: date
    expires_through: date
    warning_days: int
    programs: AgendaSection[AgendaProgram]
    expiring_licenses: AgendaSection[AgendaLicense]
    open_questions: AgendaSection[AgendaQuestion]
