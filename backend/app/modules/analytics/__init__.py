"""P4 analytics/reporting shared module (frozen filter contract lives here).

P4-01-01 introduces the single ``UnifiedFilter`` DTO plus one shared
``UnifiedFilterService``. Analytics, XLS/XLSX/PDF/JSON reports, statistics,
P1 list adapters and the frontend all reuse this contract unchanged — the
period is interpreted exactly once, in ``filters``/``filter_service``.

P4-01-02 wires the filter into the P1 universities list (additive AND with
legacy params) and pins the analytics boundary (``AnalyticsService``).
P4-02-01/02-02 add the license-grain ``ReportDatasetService``, the column
registry (``columns``) and the ``ReportRequest`` DTO (``report_request``).
P4-03-02 adds the XLSX exporter (``xlsx``) over the dataset; P4-03-01
adds the async creation contract (``report_service`` + ``reports_router``)
and P4-06-01 lands the persistent ``ReportJob`` store (``report_jobs``)
with the ``BackgroundTasks`` worker (``report_worker``).
"""

from app.modules.analytics.analytics import AnalyticsService
from app.modules.analytics.columns import (
    ADDITIONAL_COLUMNS,
    COLUMN_REGISTRY,
    DEFAULT_COLUMNS,
    MANDATORY_COLUMNS,
    PRESETS,
    TZ_COLUMNS,
    ReportColumn,
    resolve_columns,
)
from app.modules.analytics.dataset import ReportDataset, ReportDatasetService
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter, get_unified_filter
from app.models.report_job import ReportJob
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import (
    ReportQueuedResponse,
    build_job_payload,
    create_report_job,
)
from app.modules.analytics.reports_router import ReportJobRead
from app.modules.analytics.xlsx import GeneratedReport, generate_xlsx_report

__all__ = [
    "ADDITIONAL_COLUMNS",
    "COLUMN_REGISTRY",
    "DEFAULT_COLUMNS",
    "MANDATORY_COLUMNS",
    "PRESETS",
    "TZ_COLUMNS",
    "AnalyticsService",
    "GeneratedReport",
    "ReportColumn",
    "ReportDataset",
    "ReportDatasetService",
    "ReportJob",
    "ReportJobRead",
    "ReportQueuedResponse",
    "ReportRequest",
    "UnifiedFilter",
    "UnifiedFilterService",
    "build_job_payload",
    "create_report_job",
    "generate_xlsx_report",
    "get_unified_filter",
    "resolve_columns",
]
