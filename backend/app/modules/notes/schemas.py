from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoteText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=300)
    content: str = Field(default="", max_length=200_000)


class NoteCreate(NoteText):
    # Client-generated IDs make retrying creation after a lost response safe.
    id: UUID = Field(default_factory=uuid4)


class NotePdfExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=300)
    document: dict[str, Any]

    @field_validator("document")
    @classmethod
    def bounded_document(cls, value):
        if value.get("type") != "doc":
            raise ValueError("Expected an editor document")
        stack, items, characters = [(value, 0)], 0, 0
        while stack:
            item, depth = stack.pop()
            items += 1
            if depth > 64 or items > 100_000:
                raise ValueError("Document structure is too large")
            if isinstance(item, dict):
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                stack.extend((child, depth + 1) for child in item)
            elif isinstance(item, str):
                characters += len(item)
                if characters > 1_000_000:
                    raise ValueError("Document text is too large")
        return value


class NoteUpdate(NoteText):
    revision: int = Field(ge=0)


class NoteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    snippet: str
    revision: int
    created_at: datetime
    updated_at: datetime


class NoteOut(NoteText):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    created_at: datetime
    updated_at: datetime


class NotePage(BaseModel):
    items: list[NoteSummary]
    total: int


class Mention(BaseModel):
    kind: Literal["user", "university", "direction", "program", "vendor", "workflow", "document", "contract", "license", "product", "responsible"]
    id: str
    title: str
    subtitle: str = ""
    # Only canonical CRM routes are returned. A missing route means no access.
    href: str | None = None
    university_id: UUID | None = None
