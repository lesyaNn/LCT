"""P4 report statistics API: charts/graphs of the filtered selection.

``POST /api/v1/reports/statistics`` returns the aggregated view of exactly the
rows the table shows for the same ``UnifiedFilter`` — see
:mod:`app.modules.analytics.stats` for the aggregation and grain rules.

It is a POST because the filter is a JSON body with UUID lists, matching
``POST /api/v1/reports/preview``; the existing ``GET /analytics/overview`` is
left alone because it serves a different (dashboard) contract and is used by
code outside the report flow.

The endpoint reuses the report permission model (``reports.read``) and the
same security scope as the export, so statistics can never widen access.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.analytics.columns import DEFAULT_COLUMNS
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ColumnsField
from app.modules.analytics.report_request import ReportGroupBy
from app.modules.analytics.report_service import REPORTS_READ_PERMISSION
from app.modules.analytics.stats import (
    DIMENSION_TITLES,
    STAT_DIMENSIONS,
    ReportStats,
    ReportStatsService,
    StatSlice,
)
from app.modules.audit.service import get_audit_db
from app.schemas.common import ErrorResponse
from app.schemas.errors import ErrorCode

__all__ = ["ReportStatsResponse", "router", "stats_response"]

router = APIRouter(prefix="/reports/statistics", tags=["Reports"])


class StatBucketRead(BaseModel):
    """One bar: a human-readable label (never a raw id) and its count."""

    label: str
    count: int = Field(ge=0, description="Universities or rows in this bucket.")


class StatSliceRead(BaseModel):
    """One dimension of the selection."""

    dimension: str = Field(description="Machine key, e.g. by_direction.")
    title: str = Field(description="Human-readable chart title.")
    unit: str = Field(
        description="What the counts mean: rows (report rows) or universities."
    )
    total: int = Field(description="Sum of the bucket counts.")
    buckets: list[StatBucketRead]


class ReportStatsResponse(BaseModel):
    """Aggregated selection: same filters as the table, counted in SQL."""

    university_count: int = Field(description="Distinct universities selected.")
    row_count: int = Field(description="Report rows at the dataset grain.")
    columns: list[str] = Field(
        description="Effective output columns, so a client can label a bucket."
    )
    slices: list[StatSliceRead]
    grouped: StatSliceRead | None = None

    @property
    def dimensions(self) -> list[str]:
        return list(STAT_DIMENSIONS)


def stats_response(stats: ReportStats, columns: list[str], grouped: StatSlice | None = None) -> ReportStatsResponse:
    """Map the service result to the API shape (one place, no duplication)."""
    return ReportStatsResponse(
        university_count=stats.university_count,
        row_count=stats.row_count,
        columns=list(columns),
        slices=[
            StatSliceRead(
                dimension=item.dimension,
                title=item.title or DIMENSION_TITLES.get(item.dimension, item.dimension),
                unit=item.unit,
                total=item.total,
                buckets=[StatBucketRead(label=b.label, count=b.count) for b in item.buckets],
            )
            for item in stats.slices
        ],
        grouped=StatSliceRead(dimension=grouped.dimension, title=grouped.title, unit=grouped.unit, total=grouped.total, buckets=[StatBucketRead(label=b.label, count=b.count) for b in grouped.buckets]) if grouped else None,
    )


class StatisticsRequest(BaseModel):
    """Filter for the statistics (columns only affect labels, not the counts)."""

    filters: UnifiedFilter = Field(
        default_factory=UnifiedFilter,
        description="Same UnifiedFilter as the report/preview endpoints.",
    )
    columns: ColumnsField = Field(
        default=None,
        description="Optional column selection, echoed back for labelling. "
        "The aggregation itself always uses the full registry.",
    )
    group_by: ReportGroupBy | None = None

    @property
    def resolved_columns(self) -> list[str]:
        if self.columns is None:
            return list(DEFAULT_COLUMNS)
        return list(self.columns)


@router.post(
    "",
    response_model=ReportStatsResponse,
    summary="Статистика по выбранной выборке",
    description="Считает агрегаты (срезы по измерениям) для того же UnifiedFilter, что таблица и предпросмотр. Требуется право reports.read.",
    responses={
        401: {"model": ErrorResponse, "description": "AUTH_REQUIRED"},
        403: {"model": ErrorResponse, "description": "FORBIDDEN"},
        422: {"model": ErrorResponse, "description": "Ошибка валидации фильтра"},
    },
)
def report_statistics(
    request: StatisticsRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission(REPORTS_READ_PERMISSION)),
) -> ReportStatsResponse:
    """Aggregate the filtered selection for the charts.

    Thin HTTP adapter: the filter application, the security scope and the SQL
    aggregation live in the dataset/filter/stats modules, so this endpoint and
    the export can never disagree about what "the selection" means.
    """
    try:
        stats = ReportStatsService.build(db, request.filters, user=user)
        grouped = ReportStatsService.group_slice(db, request.filters, request.group_by, columns=request.resolved_columns, user=user) if request.group_by else None
    except BusinessException:
        raise
    except ValueError as exc:
        raise BusinessException(ErrorCode.VALIDATION_ERROR) from exc
    return stats_response(stats, request.resolved_columns, grouped)
