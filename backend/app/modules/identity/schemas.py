from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    organization_id: str = ""
    is_active: bool = True

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    organization_id: str = ""
