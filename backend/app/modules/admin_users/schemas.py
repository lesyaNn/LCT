"""Public Admin Users DTOs; Keycloak remains the identity source."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.validation import ContactEmail, NonBlankText


Role = Literal["user", "manager", "admin"]


class UserScope(BaseModel):
    kind: Literal["all", "universities"]
    university_ids: list[UUID] = Field(default_factory=list, max_length=5000)


class AdminUserOut(BaseModel):
    id: UUID
    username: str
    name: str
    email: str
    role: Role
    status: Literal["active", "blocked"]
    scope: UserScope
    last_login_at: None = None  # Keycloak user endpoint has no reliable timestamp.


class AdminUsersPage(BaseModel):
    items: list[AdminUserOut]
    page: int
    page_size: int
    total: int


class UserUpdate(BaseModel):
    role: Role
    scope: UserScope

    @model_validator(mode="after")
    def scope_follows_role(self):
        if (self.role == "admin") != (self.scope.kind == "all"):
            raise ValueError("Только администратор имеет доступ ко всем ВУЗам")
        return self


class UserBlock(BaseModel):
    blocked: bool


class UserInvite(UserUpdate):
    name: NonBlankText = Field(min_length=2, max_length=256)
    username: str = Field(min_length=2, max_length=128, pattern=r"^[A-Za-z0-9._@-]+$")
    email: ContactEmail = Field(min_length=5, max_length=256)


class InviteResult(BaseModel):
    user: AdminUserOut
    status: Literal["email_sent", "invite_email_unavailable"]


class PasswordResetResult(BaseModel):
    status: Literal["requested"] = "requested"
