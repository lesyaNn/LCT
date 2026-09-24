"""Dev-1 filter adapter for the Dev-2 analytics boundary (P4-07-01/P4-09-01).

Implements :class:`FilterProvider` over the frozen Dev-1 ``UnifiedFilter`` +
``UnifiedFilterService``/``AnalyticsService``: identical predicates as the P1
list and the P4-02 report dataset (one filter -> one university set
everywhere). Wire it with::

    P4_FILTER_PROVIDER=app.modules.analytics.dev1_provider:provider

Without it only the empty filter works (fail-closed ``503`` from
``UnfilteredProvider``).

Child narrowing (frozen here, mirrors the university-level EXISTS rules):
* ``program_ids`` -> program universe as given;
* ``direction_ids`` -> programs with ``direction_id`` in the filter;
* no program/direction filter -> ALL programs (matrix universe as before);
* ``product_ids`` -> ``license_ids`` of selected universities with a filtered
  product (``None`` otherwise);
* ``workflow_statuses`` -> ``workflow_instance_ids`` of selected
  universities matching the same stored/current/overdue branches as
  ``UnifiedFilterService`` (``None`` otherwise);
* ``responsible_ids`` / dates bind universities only (children inherit via
  the university set); ``university_program_ids`` stays ``None``.

``Selection`` lists are deterministic (sorted by id).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.catalog import ITProgram, License
from app.models.interactions import UniversityProgram
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.analytics.analytics import AnalyticsService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.filter_service import (
    CLOSED_STAGE_STATUSES,
    STORED_STAGE_STATUSES,
)
from app.modules.analytics.integration import Selection, data_scope, restrict_selection
from app.schemas.common import WorkflowStageStatus

__all__ = ["Dev1FilterProvider", "provider"]


def _sorted_ids(values) -> list[UUID]:
    return sorted({v for v in values if isinstance(v, uuid.UUID)})


class Dev1FilterProvider:
    """``FilterProvider`` over the frozen Dev-1 filter stack."""

    version = "dev1-unified-v1"

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate via ``UnifiedFilter``; 422 with details on bad input.

        Unknown fields are rejected (``UnifiedFilter`` itself ignores
        extras) — same fail-closed contract as ``UnfilteredProvider``.
        """
        from app.modules.analytics.integration import FILTER_KEYS

        unknown = set(raw or {}) - FILTER_KEYS
        if unknown:
            raise BusinessException(ErrorCode.VALIDATION_ERROR)
        try:
            filters = UnifiedFilter.model_validate(raw or {})
        except ValidationError as exc:
            raise BusinessException(ErrorCode.VALIDATION_ERROR) from exc
        return filters.model_dump(mode="json")

    def select(
        self, db: Session, filters: dict[str, Any], *, today: date | None = None,
        user=None,
    ) -> Selection:
        """Select IDs with Dev-1 semantics (same university set as list/dataset)."""
        dto = UnifiedFilter.model_validate(filters or {})
        day = today or date.today()
        uni_ids = AnalyticsService.filtered_university_ids(db, dto, today=day, user=user)

        if dto.program_ids:
            program_ids = _sorted_ids(dto.program_ids)
        elif dto.direction_ids:
            program_ids = _sorted_ids(
                db.scalars(
                    select(ITProgram.id).where(
                        ITProgram.direction_id.in_(list(dto.direction_ids))
                    )
                ).all()
            )
        elif user is not None and data_scope(user) is not None:
            program_ids = _sorted_ids(db.scalars(
                select(UniversityProgram.program_id).distinct().where(
                    UniversityProgram.university_id.in_(uni_ids)
                )
            ))
        else:
            program_ids = _sorted_ids(db.scalars(select(ITProgram.id)))

        license_ids: list[UUID] | None = None
        if dto.product_ids:
            license_ids = _sorted_ids(
                db.scalars(
                    select(License.id).where(
                        License.university_id.in_(uni_ids),
                        License.product_id.in_(list(dto.product_ids)),
                    )
                ).all()
            )

        instance_ids: list[UUID] | None = None
        if dto.workflow_statuses:
            instance_ids = _sorted_ids(
                db.scalars(
                    select(WorkflowInstance.id).where(
                        WorkflowInstance.university_id.in_(uni_ids),
                        self._instance_branches(list(dto.workflow_statuses), day),
                    )
                ).all()
            )

        selection = Selection(
            university_ids=_sorted_ids(uni_ids),
            program_ids=program_ids,
            university_program_ids=None,
            license_ids=license_ids,
            workflow_instance_ids=instance_ids,
        )
        # An empty scoped university set must remain an explicit empty
        # selection for every child dimension.  ``None`` means "all children"
        # to the analytics loader and would otherwise make an empty scope
        # indistinguishable from a global selection for callers that inspect
        # child IDs before loading data.
        if user is not None and data_scope(user) is not None and not uni_ids:
            selection = selection.model_copy(update={
                "program_ids": [],
                "university_program_ids": [],
                "license_ids": [],
                "workflow_instance_ids": [],
            })
        return restrict_selection(selection, data_scope(user), db) if user is not None else selection

    def select_scoped(self, db: Session, filters: dict[str, Any], user) -> Selection:
        return self.select(db, filters, user=user)

    @staticmethod
    def _instance_branches(statuses: list[WorkflowStageStatus], day: date):
        """Instance-level mirror of ``UnifiedFilterService._workflow_exists``."""
        stored = sorted({s.value for s in statuses} & STORED_STAGE_STATUSES)
        ors = []
        if stored:
            ors.append(
                WorkflowInstance.id.in_(
                    select(InstanceStage.instance_id).where(
                        InstanceStage.status.in_(stored)
                    )
                )
            )
        if WorkflowStageStatus.CURRENT in statuses:
            ors.append(WorkflowInstance.current_instance_stage_id.is_not(None))
        if WorkflowStageStatus.OVERDUE in statuses:
            ors.append(
                WorkflowInstance.id.in_(
                    select(InstanceStage.instance_id).where(
                        InstanceStage.status.notin_(sorted(CLOSED_STAGE_STATUSES)),
                        InstanceStage.due_date.is_not(None),
                        InstanceStage.due_date < day,
                        InstanceStage.completed_at.is_(None),
                    )
                )
            )
        if not ors:
            return True
        return or_(*ors)


provider = Dev1FilterProvider()
