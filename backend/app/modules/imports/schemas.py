"""Import v2 DTOs: whole-file upload, single-sheet preview/execute, journal.

Flow: ``POST /upload`` (file -> sheets) -> user picks ONE sheet ->
``POST /sheets/preview`` (headers + first rows) -> ``POST /execute``
(async ``xlsx_import`` job, dry-run supported) -> journal polling.
Column mapping is server-owned (sheet structures are fixed), so the
client never sends a mapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportSheetInfo(BaseModel):
    id: str = Field(description="Sheet identifier (workbook sheet title).")
    label: str = Field(description="Human-readable sheet label.")
    row_count: int = Field(description="Non-empty data rows (header excluded).")


class ImportUploadResponse(BaseModel):
    file_id: str = Field(description="Staging id for preview/execute calls.")
    filename: str = Field(description="Original client filename.")
    sheets: list[ImportSheetInfo] = Field(description="Sheets with data.")


class SheetPreviewRequest(BaseModel):
    file_id: str
    sheet: str


class ImportSheetPreview(BaseModel):
    file_id: str
    sheet: str
    headers: list[str]
    preview: list[dict[str, Any]]
    row_count: int


class ImportExecuteRequest(BaseModel):
    file_id: str
    sheet: str | None = None
    sheets: list[str] | None = None
    dry_run: bool = False
    update_existing: bool = True
    filename: str | None = None


class ImportExecuteResponse(BaseModel):
    job_id: uuid.UUID


class ImportRowError(BaseModel):
    row: int
    field: str
    error: str


class ImportSummary(BaseModel):
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ImportRowError] = Field(default_factory=list)
    dry_run: bool = False
    errors_total: int = 0
    truncated: bool = False
    sheets: list[ImportSheetResult] = Field(default_factory=list)


class ImportSheetResult(BaseModel):
    sheet: str
    summary: ImportSummary | None = None
    error: str | None = None


class ImportJobRead(BaseModel):
    """Journal view of an ``xlsx_import`` job (never a filesystem path)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    type: str = "xlsx_import"
    status: str
    progress: int | None = None
    dry_run: bool = False
    created_at: datetime
    created_by: str | None = None
    filename: str | None = None
    sheet: str | None = None
    result: ImportSummary | None = None
    error: str | None = None
    error_report_url: str | None = None
