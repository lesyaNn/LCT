from pydantic import BaseModel


class MeOut(BaseModel):
    id: str
    username: str | None = None
    email: str | None = None
    name: str | None = None
    roles: list[str] = []
    permissions: list[str] = []
    scope: dict[str, str | list[str]]
