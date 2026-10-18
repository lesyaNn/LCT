"""Response variants produced by the bounded file preview renderer."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ImagePreview(BaseModel):
    kind: Literal["image"]
    src: str = Field(description="Изображение PNG/JPEG в виде data URI")
    width: int
    height: int
    message: str | None = None
    format: str | None = None


class TablePreview(BaseModel):
    kind: Literal["table"]
    rows: list[list[str]]
    sheet: str
    message: str


class DocumentBlock(BaseModel):
    text: str
    style: Literal["heading", "list", "paragraph"]


class DocumentPreview(BaseModel):
    kind: Literal["document"]
    blocks: list[DocumentBlock]
    message: str


class ArchiveEntry(BaseModel):
    name: str
    size: int | None
    directory: bool
    extension: str


class ArchivePreview(BaseModel):
    kind: Literal["archive"]
    entries: list[ArchiveEntry]
    total: int
    offset: int
    message: str | None = None


class UnavailablePreview(BaseModel):
    kind: Literal["unsupported", "error"]
    message: str


FilePreview = Annotated[
    ImagePreview | TablePreview | DocumentPreview | ArchivePreview | UnavailablePreview,
    Field(discriminator="kind"),
]
