"""P4-01-02 analytics boundary: shared entry point for filtered university sets.

The production ``GET /analytics/overview`` endpoint itself belongs to P4-07
and is intentionally NOT implemented here. This module pins the boundary so
the future overview accepts the frozen :class:`UnifiedFilter` with the same
semantics as the P1 list and the P4-02 report dataset (one filter -> one
university set everywhere).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import University
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter

__all__ = ["AnalyticsService"]


class AnalyticsService:
    """Service-level consistency pin for analytics consumers."""

    @staticmethod
    def filtered_university_ids(
        db: Session,
        filters: UnifiedFilter,
        *,
        user: Any | None = None,
        today: date | None = None,
    ) -> list[uuid.UUID]:
        """University ids matching ``filters`` (1 SELECT, deterministic order).

        Same predicates (``UnifiedFilterService``) and same security
        intersection (``apply_security_scope``) as the P1 list and the
        report dataset: identical filters yield identical university sets.
        """
        stmt = UnifiedFilterService.apply_to_universities(
            select(University.id), filters, today=today
        )
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        stmt = stmt.order_by(University.id.asc())
        return list(db.execute(stmt).scalars().all())
