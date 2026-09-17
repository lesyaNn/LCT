from datetime import date

from pydantic import BaseModel


class TeacherIn(BaseModel):
    full_name: str
    university_id: int | None = None
    competencies: str = ""
    next_training_date: date | None = None


class TeacherOut(TeacherIn):
    id: int

    model_config = {"from_attributes": True}
