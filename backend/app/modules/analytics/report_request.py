"""P4-02 report request contract: format + frozen UnifiedFilter + columns.

No export generation lives here (XLSX/PDF/JSON writers belong to P4-03+);
this module only freezes the request shape so every producer/consumer
shares one validation path.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

from app.modules.analytics.columns import (
    DEFAULT_COLUMNS,
    UnknownReportColumnError,
    resolve_columns,
)
from app.modules.analytics.filters import UnifiedFilter
from app.schemas.common import ReportFormat

__all__ = ["ReportFormat", "ReportGroupBy", "ReportRequest"]

ReportGroupBy = Literal["university", "direction", "program", "product", "responsible", "workflow_status"]


def _validate_columns(value: list[str] | None) -> list[str] | None:
    """Normalize column selection; Pydantic maps ValueError to 422."""
    if value is None:
        return None
    try:
        return resolve_columns(value)
    except (UnknownReportColumnError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


ColumnsField = Annotated[list[str] | None, BeforeValidator(_validate_columns)]


class ReportRequest(BaseModel):
    """Canonical report request (P4-02): one format, one frozen filter."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "format": "xlsx",
                "filters": {
                    "date_from": None,
                    "date_to": None,
                    "university_ids": [],
                    "direction_ids": [],
                    "program_ids": [],
                    "product_ids": [],
                    "responsible_ids": [],
                    "workflow_statuses": [],
                },
                "columns": list(DEFAULT_COLUMNS),
            }
        }
    }

    format: ReportFormat = Field(description="Report output format: xlsx | pdf | json.")
    filters: UnifiedFilter = Field(
        default_factory=UnifiedFilter,
        description="Frozen P4-01-01 filter (same semantics as P1 list and dataset).",
    )
    columns: ColumnsField = Field(
        default=None,
        description="Output column keys (registry). None = the ТЗ default columns "
        "(университет, ИТ-направление, ИТ-продукт, статус работы, ответственный); "
        "duplicates are deduped preserving order; unknown keys are 422; "
        "[] is 422 (at least one column required).",
    )
    group_by: ReportGroupBy | None = Field(default=None, description="Optional summary breakdown; detail rows remain unchanged.")

    @property
    def resolved_columns(self) -> list[str]:
        """Effective output columns (default applied, order preserved)."""
        if self.columns is None:
            return list(DEFAULT_COLUMNS)
        return list(self.columns)
