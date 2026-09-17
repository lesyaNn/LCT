from datetime import datetime

from pydantic import BaseModel


class StatusOut(BaseModel):
    id: int
    code: str
    name: str
    position: int

    model_config = {"from_attributes": True}


class WorkflowOut(BaseModel):
    id: int
    university_id: int
    program_id: int | None
    status_id: int

    model_config = {"from_attributes": True}


class WorkflowCreate(BaseModel):
    university_id: int
    program_id: int | None = None
    status_code: str = "new"


class ChangeStatus(BaseModel):
    to_status_code: str


class TaskIn(BaseModel):
    university_id: int | None = None
    workflow_id: int | None = None
    title: str
    description: str = ""
    responsible_id: int | None = None
    deadline: datetime | None = None


class TaskOut(TaskIn):
    id: int
    status: str

    model_config = {"from_attributes": True}
