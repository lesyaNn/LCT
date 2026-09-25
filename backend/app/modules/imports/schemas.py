"""XLSX/XLS import DTOs (P4-10-01).

Flow: ``POST /import/preview`` (multipart) -> mapping on the frontend ->
``POST /import/execute`` (returns ``job_id``) -> ``GET /import/jobs/{id}``.
Mapping UI itself is P3-owned (P3-11-01); the backend only accepts the
``mapping`` dict. Detailed per-row validation rules live in P4-10-02.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Ключи — заголовки колонок файла, значения — поля БД (см. TARGET_FIELDS).
#: Заголовки — канонические имена из ТЗ (P4-10-03), чтобы дефолтный маппинг
#: срабатывал на файле от заказчика без ручного сопоставления.
#: Swagger подставляет этот пример в "Try it out" целиком.
EXAMPLE_MAPPING: dict[str, str] = {
    "ВУЗ": "university.name",
    "Вендор": "vendor.name",
    "ПО": "product.name",
    "Номер договора": "contract.contract_number",
    "Подписание лицензии": "license.signed_at",
    "Срок лицензии": "license.expires_at",
    "Статус передачи": "license.transfer_status",
    "ФИО менеджера": "responsible.full_name",
    "Ответственные от ВУЗа": "university_responsibles",
    "Комментарий": "license.comment",
    "IT направление": "direction.name",
}


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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "вставьте file_id из POST /import/preview",
                "mapping": EXAMPLE_MAPPING,
                "options": {
                    "skip_header": True,
                    "update_existing": True,
                    "dry_run": False,
                },
            }
        }
    )

    file_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    filename: str | None = Field(default=None, max_length=256)
    catalog_type: Literal["licenses", "universities", "directions", "products", "responsibles", "vendor_contacts"] = "licenses"
    mapping: dict[str, str] = Field(examples=[EXAMPLE_MAPPING])
    options: ImportOptions = Field(default_factory=ImportOptions)


class ImportExecuteResponse(BaseModel):
    job_id: str


class RowError(BaseModel):
    """P4-10-02: построчная ошибка с машиночитаемым кодом.

    Коды: REQUIRED | INVALID_FORMAT | NOT_FOUND | DUPLICATE |
    FK_VIOLATION | ROW_ERROR (прочее).
    """

    row: int
    field: str
    code: str = "ROW_ERROR"
    message: str


class ImportSummary(BaseModel):
    total_rows: int
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[RowError] = Field(default_factory=list)
    dry_run: bool = False
    truncated: bool = False
    errors_total: int = 0


class ImportJobStatus(BaseModel):
    """Polling payload for ``GET /import/jobs/{id}`` (P4-06-02).

    Statuses come from the shared ``report_jobs`` ledger (P4-06-01):
    ``queued`` → ``building`` → ``ready`` | ``failed``. The frontend polls
    until a terminal status; ``progress`` drives the progress-bar,
    ``error`` carries the sanitized failure reason, ``result`` the
    terminal summary (inserted/updated/skipped/errors with codes).
    """

    id: str
    type: str
    status: str
    progress: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: str | None = None
    created_by: str | None = None
    filename: str | None = None
    catalog_type: str | None = None
    error_report_url: str | None = None


__all__ = [
    "EXAMPLE_MAPPING",
    "ImportExecuteRequest",
    "ImportExecuteResponse",
    "ImportJobStatus",
    "ImportOptions",
    "ImportPreview",
    "ImportSummary",
    "RowError",
]
