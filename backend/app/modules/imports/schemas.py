"""XLSX import DTOs (P4-10-01).

Flow: ``POST /import/preview`` (multipart) -> mapping on the frontend ->
``POST /import/execute`` (returns ``job_id``) -> ``GET /import/jobs/{id}``.
Mapping UI itself is P3-owned (P3-11-01); the backend only accepts the
``mapping`` dict. Detailed per-row validation rules live in P4-10-02.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportPreview(BaseModel):
    file_id: str
    filename: str
    headers: list[str]
    preview: list[dict[str, str | int | float | bool | None]]
    row_count: int
    detected_sheet: str


class ImportOptions(BaseModel):
    skip_header: bool = True
    update_existing: bool = True
    dry_run: bool = False


class ImportExecuteRequest(BaseModel):
    file_id: str
    mapping: dict[str, str] = Field(
        examples=[
            {
                "ВУЗ": "university.name",
                "Вендор": "vendor.name",
                "ПО": "product.name",
                "Номер договора": "contract.contract_number",
            }
        ]
    )
    options: ImportOptions = Field(default_factory=ImportOptions)


class ImportExecuteResponse(BaseModel):
    job_id: str


class RowError(BaseModel):
    row: int
    field: str
    error: str


class ImportSummary(BaseModel):
    total_rows: int
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[RowError] = Field(default_factory=list)
    dry_run: bool = False


class ImportJobStatus(BaseModel):
    id: str
    type: str
    status: str
    result: dict | None = None


__all__ = [
    "ImportExecuteRequest",
    "ImportExecuteResponse",
    "ImportJobStatus",
    "ImportOptions",
    "ImportPreview",
    "ImportSummary",
    "RowError",
]
