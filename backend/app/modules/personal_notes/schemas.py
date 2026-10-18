from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class NoteFolderRead(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    name: str


class NoteFolderWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Folder name is required")
        return value.strip()


class NoteRead(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    title: str
    content: str
    folder_id: UUID | None
    pinned: bool
    revision: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class NoteSummary(BaseModel):
    id: UUID
    title: str
    excerpt: str
    folder_id: UUID | None
    pinned: bool
    revision: int
    updated_at: datetime
    deleted_at: datetime | None


class NoteList(BaseModel):
    items: list[NoteSummary]
    total: int
    page: int
    page_size: int


class NoteCreate(BaseModel):
    title: str = Field(default="Без названия", max_length=256)
    content: str = Field(default="", max_length=100_000)
    folder_id: UUID | None = None


class NoteUpdate(BaseModel):
    revision: int = Field(ge=0)
    title: str | None = Field(default=None, max_length=256)
    content: str | None = Field(default=None, max_length=100_000)
    folder_id: UUID | None = None
    pinned: bool | None = None


class NoteLinkOption(BaseModel):
    kind: str
    title: str
    subtitle: str | None = None
    href: str


class ResolveLinksRequest(BaseModel):
    hrefs: list[str] = Field(max_length=50)


class ResolvedLink(BaseModel):
    href: str
    title: str | None = None
    available: bool
