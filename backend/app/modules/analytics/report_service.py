"""P4-03-01 report creation contract (production; P4-06-01 LANDED).

Frozen API (``report_jobs`` + background execution)::

    POST /api/v1/reports  ->  202 Accepted  {"job_id": "uuid", "status": "queued"}

:func:`create_report_job` validates the request (any format that has a
generator), persists ``build_job_payload(...)`` (filters, resolved columns,
format, actor scope) as a ``queued`` ``ReportJob`` and returns the real
persisted id — never a fake UUID, never a silent synchronous ``200``
file. Execution is owned by the dedicated worker container
(``python -m app.modules.analytics.report_worker``); the API only creates
jobs — ``BackgroundTasks`` are banned for reports by the spec (they die
with the API process, block the loop and have no retries).

All formats (``xls`` / ``xlsx`` / ``pdf`` / ``json``) share one validation
path, one job payload shape and one worker entry point
(:func:`generate_report_file`); every generator reads ONLY from
``ReportDatasetService`` with titles ONLY from ``COLUMN_REGISTRY``.

Security note: :func:`build_job_payload` captures the actor identity
(``sub``) AND the effective university scope alongside the serialized
filter, so the worker re-applies the same security intersection
instead of re-running the filter as admin/global.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.json_export import generate_json_report
from app.modules.analytics.pdf import generate_pdf_report
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.xlsx import generate_xlsx_report
from app.modules.analytics.xls import generate_xls_report
from app.schemas.common import ReportFormat

__all__ = [
    "FORMAT_GENERATORS",
    "REPORTS_READ_PERMISSION",
    "ReportQueuedResponse",
    "build_job_payload",
    "create_report_job",
    "ensure_supported_format",
    "ensure_xlsx",
    "generate_report_file",
    "supported_formats",
]

#: Frozen report/read permission contract (see ``app/core/permissions.py`` —
#: no ``reports.write`` exists, so creation also gates on ``reports.read``;
#: held by ``admin`` + ``manager`` — access is never widened here).
REPORTS_READ_PERMISSION = "reports.read"


class ReportQueuedResponse(BaseModel):
    """Frozen ``202 Accepted`` body for ``POST /api/v1/reports``."""

    job_id: str = Field(description="Persistent P4-06-01 ReportJob id (uuid).")
    status: Literal["queued"] = Field(
        default="queued", description="Lifecycle state right after enqueue."
    )


def supported_formats() -> frozenset[ReportFormat]:
    """Formats with a real generator (derived, never a second hardcoded set)."""
    return frozenset(FORMAT_GENERATORS)


def ensure_supported_format(request: ReportRequest) -> None:
    """Gate a request to the formats that actually have a generator.

    The dispatch table below IS the format list — there is no second
    hardcoded set to fall out of sync with it.
    """
    if request.format not in FORMAT_GENERATORS:
        supported = ", ".join(sorted(f.value for f in FORMAT_GENERATORS))
        raise ValueError(
            f"unsupported report format: {request.format.value!r} "
            f"(expected one of: {supported})"
        )


def ensure_xlsx(request: ReportRequest) -> None:
    """Gate this work block to ``format == xlsx`` (else: never run XLSX gen)."""
    if request.format is not ReportFormat.XLSX:
        raise ValueError(
            f"unsupported report format for the XLSX generator: {request.format!r} "
            "(expected 'xlsx')"
        )


#: Worker-facing dispatch table (P4-06-01 seam): format -> file generator.
#: Every generator shares the signature
#: ``(db, filters, columns, output_path, *, user, generated_at)`` and
#: returns ``GeneratedReport``. This mapping is also the single source of
#: truth for which formats the API accepts.
FORMAT_GENERATORS: dict[ReportFormat, Callable[..., Any]] = {
    ReportFormat.XLS: generate_xls_report,
    ReportFormat.XLSX: generate_xlsx_report,
    ReportFormat.PDF: generate_pdf_report,
    ReportFormat.JSON: generate_json_report,
}


def generate_report_file(
    db: Session,
    request: ReportRequest,
    output_path: str | Path,
    *,
    user: Any | None = None,
    generated_at: Any | None = None,
) -> Any:
    """Synchronous worker entry point for the P4-06-01 background job.

    Dispatches ``request.format`` to the matching file generator (all read
    ONLY from ``ReportDatasetService``). Pure file generation — no job
    persistence, no queue; P4-06-01 calls this inside the worker with the
    re-applied actor scope. Raises ``ValueError`` for unknown formats.
    """
    ensure_supported_format(request)
    generate = FORMAT_GENERATORS[request.format]
    return generate(
        db,
        request.filters,
        request.resolved_columns,
        output_path,
        user=user,
        generated_at=generated_at,
    )


def build_job_payload(request: ReportRequest, user: Any) -> dict[str, Any]:
    """Persistence-ready job body for the future P4-06-01 ``ReportJob``.

    Pure function (no DB, no queue): serializes the validated request plus
    the actor scope the worker must re-apply. ``columns`` are the resolved
    output columns (ТЗ default applied, order preserved). Identical shape
    for every format (only ``format`` differs).
    """
    roles = sorted(getattr(user, "roles", None) or [])
    from app.core.policies import get_data_scope

    policy = get_data_scope(user)
    scope = None if policy.is_all else tuple(sorted(str(v) for v in policy.university_ids))
    return {
        "format": request.format.value,
        "filters": request.filters.model_dump(mode="json"),
        "columns": request.resolved_columns,
        "actor": {
            "sub": getattr(user, "id", ""),
            "roles": roles,
            "university_ids": list(scope) if scope is not None else None,
        },
    }


def create_report_job(db: Session, request: ReportRequest, user: Any) -> ReportQueuedResponse:
    """Validate + persist a report job (``status=queued``) and return its id.

    Ordering (never a fake id): validate -> persist -> commit -> return the
    persisted ``job.id``. The dedicated worker container picks the job up
    via ``claim_next_job``; a persistence failure raises before any
    worker is ever started. ``columns`` are stored already resolved
    (default applied, order preserved, deduped) so the worker never
    depends on a changed client request.

    Dedup (ТЗ §7): an identical queued/building job of the same actor is
    returned as-is instead of persisting a duplicate row.
    """
    from app.modules.analytics import report_jobs as jobs

    ensure_supported_format(request)
    UnifiedFilter.model_validate(request.filters.model_dump(mode="json"))
    payload = build_job_payload(request, user)
    actor = payload["actor"]
    duplicate = jobs.find_inflight_duplicate(
        db,
        format=payload["format"],
        filters=payload["filters"],
        columns=payload["columns"],
        actor_sub=actor["sub"],
    )
    if duplicate is not None:
        return ReportQueuedResponse(job_id=str(duplicate.id), status="queued")
    job = jobs.create_job(
        db,
        format=payload["format"],
        filters=payload["filters"],
        columns=payload["columns"],
        actor_sub=actor["sub"],
        actor_name=getattr(user, "name", None) or getattr(user, "username", None) or "",
        actor_roles=actor["roles"],
        effective_university_ids=actor["university_ids"],
    )
    return ReportQueuedResponse(job_id=str(job.id), status="queued")
