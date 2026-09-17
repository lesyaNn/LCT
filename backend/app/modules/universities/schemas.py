from pydantic import BaseModel


class UniversityCreate(BaseModel):
    name: str
    region: str = ""
    city: str = ""
    address: str = ""
    status: str = "new"
    responsible_person_id: int | None = None


class UniversityUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    city: str | None = None
    address: str | None = None
    status: str | None = None
    responsible_person_id: int | None = None


class UniversityOut(UniversityCreate):
    id: int

    model_config = {"from_attributes": True}
