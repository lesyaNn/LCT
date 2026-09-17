from datetime import date

from pydantic import BaseModel


class ProgramIn(BaseModel):
    name: str
    direction_id: str = ""
    university_id: int | None = None
    status: str = "draft"
    start_date: date | None = None
    launch_date: date | None = None
    responsible_id: int | None = None


class ProgramOut(ProgramIn):
    id: int

    model_config = {"from_attributes": True}
