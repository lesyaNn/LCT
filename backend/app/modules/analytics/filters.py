"""P4-01-01: unified frozen filter contract (single DTO for all P4 consumers).

One ``UnifiedFilter`` is shared — unchanged — by analytics, XLSX/PDF/JSON
reports, P1 list adapters and the frontend. Pagination stays a separate
contract and is deliberately NOT part of this DTO.

Field semantics (frozen):

* ``date_from`` / ``date_to`` — inclusive bounds on the report dataset row
  date. For university queries the row date is ``universities.created_at``
  (see :mod:`app.modules.analytics.filter_service` and
  ``docs/contracts/unified-filter.json``). ``date_from <= date_to`` is
  enforced; a reversed range is a 422 validation error.
* ``*_ids`` — multi-select dimensions. An empty list means "filter not
  applied" (never ``WHERE FALSE``). Duplicate IDs are deduplicated
  (first-seen order kept); semantics are unchanged for ``IN`` queries.
* ``workflow_statuses`` — reuses the frozen
  :class:`app.schemas.common.WorkflowStageStatus` API enum
  (``pending`` / ``current`` / ``completed`` / ``skipped`` / ``overdue``).
  No second enum is introduced; the alias ``WorkflowFilterStatus`` below is
  only a P4-facing name for the same single source of truth.

The same model parses FastAPI query params (via :func:`get_unified_filter`,
multi-select as repeated ``?university_ids=<uuid>&university_ids=<uuid>``)
and JSON bodies (future ``ReportRequest.filters``), and round-trips through
``model_dump`` / ``model_validate`` identically.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.schemas.common import WorkflowStageStatus

#: P4-facing name for the frozen workflow-stage status contract. This is an
#: alias, NOT a new enum: allowed values stay single-sourced in
#: ``app.schemas.common.WorkflowStageStatus`` (§4: no second enum).
WorkflowFilterStatus = WorkflowStageStatus

__all__ = [
    "ID_LIST_FIELDS",
    "UnifiedFilter",
    "WorkflowFilterStatus",
    "WorkflowStageStatus",
    "get_unified_filter",
]

#: UUID multi-select dimensions of the contract (documented order).
ID_LIST_FIELDS: tuple[str, ...] = (
    "university_ids",
    "direction_ids",
    "program_ids",
    "product_ids",
    "responsible_ids",
)


def _dedupe_preserve_order(values: list[Any]) -> list[Any]:
    """Deduplicate keeping first-seen order (semantics-safe for ``IN``)."""
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


class UnifiedFilter(BaseModel):
    """Frozen 8-dimension filter DTO (P4-01-01, v1.0.0-frozen)."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "date_from": None,
                "date_to": None,
                "university_ids": [],
                "direction_ids": [],
                "program_ids": [],
                "product_ids": [],
                "responsible_ids": [],
                "workflow_statuses": [],
            }
        }
    }

    date_from: date | None = Field(
        default=None, description="Inclusive lower bound (ISO date, YYYY-MM-DD)."
    )
    date_to: date | None = Field(
        default=None, description="Inclusive upper bound (ISO date, YYYY-MM-DD)."
    )

    university_ids: list[uuid.UUID] = Field(
        default_factory=list, description="University.id IN (...); [] = not applied."
    )
    direction_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Universities linked (via university_programs) to programs "
        "of these IT directions; [] = not applied.",
    )
    program_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Universities linked (via university_programs.program_id); "
        "[] = not applied.",
    )
    product_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Universities linked (via university_products.product_id); "
        "[] = not applied.",
    )
    responsible_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Universities linked (via university_responsibles); "
        "[] = not applied.",
    )

    workflow_statuses: list[WorkflowStageStatus] = Field(
        default_factory=list,
        description="Universities with workflow runtime in one of these stage "
        "statuses (pending/current/completed/skipped/overdue); [] = not applied.",
    )

    @field_validator(
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        mode="before",
    )
    @classmethod
    def _normalize_id_list(cls, value: Any) -> list[Any]:
        """``None`` -> ``[]``; duplicates collapsed, first-seen order kept."""
        if value is None:
            return []
        if isinstance(value, list):
            return _dedupe_preserve_order(value)
        return value

    @field_validator("workflow_statuses", mode="before")
    @classmethod
    def _normalize_status_list(cls, value: Any) -> list[Any]:
        """``None`` -> ``[]``; duplicates collapsed, first-seen order kept."""
        if value is None:
            return []
        if isinstance(value, list):
            return _dedupe_preserve_order(value)
        return value

    @model_validator(mode="after")
    def _check_date_range(self) -> UnifiedFilter:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be less than or equal to date_to")
        return self


def get_unified_filter(
    date_from: Annotated[
        date | None, Query(description="Inclusive lower bound (YYYY-MM-DD).")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Inclusive upper bound (YYYY-MM-DD).")
    ] = None,
    university_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="Repeatable: ?university_ids=<uuid>&university_ids=<uuid>."),
    ] = None,
    direction_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="Repeatable: ?direction_ids=<uuid>&direction_ids=<uuid>."),
    ] = None,
    program_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="Repeatable: ?program_ids=<uuid>&program_ids=<uuid>."),
    ] = None,
    product_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="Repeatable: ?product_ids=<uuid>&product_ids=<uuid>."),
    ] = None,
    responsible_ids: Annotated[
        list[uuid.UUID] | None,
        Query(description="Repeatable: ?responsible_ids=<uuid>&responsible_ids=<uuid>."),
    ] = None,
    workflow_statuses: Annotated[
        list[WorkflowStageStatus] | None,
        Query(
            description="Repeatable stage status: "
            "pending/current/completed/skipped/overdue."
        ),
    ] = None,
) -> UnifiedFilter:
    """Single FastAPI dependency building :class:`UnifiedFilter` from query params.

    Type-level errors (bad UUID/date/enum) are rejected by FastAPI itself
    (422); the cross-field ``date_from <= date_to`` rule is mapped here to a
    422 carrying the Pydantic error detail (never a 500).
    """
    try:
        return UnifiedFilter(
            date_from=date_from,
            date_to=date_to,
            university_ids=university_ids,
            direction_ids=direction_ids,
            program_ids=program_ids,
            product_ids=product_ids,
            responsible_ids=responsible_ids,
            workflow_statuses=workflow_statuses,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=jsonable_encoder(exc.errors(include_url=False)),
        ) from exc
