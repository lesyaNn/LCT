"""JSON contract shared with the frontend; normal replies never stream."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Basis = Literal["documentation", "inference", "insufficient"]
Page = Literal[
    "dashboard",
    "universities",
    "university",
    "workflows",
    "workflow",
    "reports",
    "audit",
    "catalogs",
    "import",
    "users",
    "workflow_templates",
    "docs",
]


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    page: Page | None = None
    expected_revision: int | None = Field(default=None, ge=0)

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Введите вопрос без нулевых символов")
        return value


class Source(BaseModel):
    id: str
    title: str
    url: str
    excerpt: str


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    basis: Basis
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class ChatOut(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    revision: int
    answer: str
    basis: Basis
    sources: list[Source]
    knowledge_version: str
    retrieval_mode: Literal["lexical", "hybrid"]
    model: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    revision: int
    created_at: datetime
    updated_at: datetime


class TurnOut(ChatOut):
    question: str


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class TurnPage(BaseModel):
    conversation: ConversationOut
    items: list[TurnOut]
    total: int
    page: int
    page_size: int


class StatusOut(BaseModel):
    enabled: bool
    ready: bool
    reason: Literal[
        "disabled", "knowledge_missing", "model_unavailable", "storage_unavailable", "ready"
    ]
    model: str
    retrieval_mode: Literal["lexical", "hybrid"]
    document_count: int
    knowledge_version: str | None
