"""Minimal university/program teacher training contract."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TrainingStatus = Literal["not_started", "in_progress", "completed", "needs_review"]


class TeacherCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=512)
    program_id: UUID


class TeacherUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=512)


class TeacherProgramCreate(BaseModel):
    program_id: UUID
    training_status: TrainingStatus = "not_started"
    qualification_status: TrainingStatus = "not_started"
    last_training_at: date | None = None
    next_qualification_due_at: date | None = None


class TeacherProgramUpdate(BaseModel):
    training_status: TrainingStatus | None = None
    qualification_status: TrainingStatus | None = None
    last_training_at: date | None = None
    next_qualification_due_at: date | None = None

    @model_validator(mode="after")
    def statuses_cannot_be_cleared(self):
        for field in ("training_status", "qualification_status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TeacherProgramRead(TeacherProgramCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TeacherRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    university_id: UUID
    full_name: str
    teacher_programs: list[TeacherProgramRead]
