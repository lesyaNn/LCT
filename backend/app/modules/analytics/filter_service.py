"""P4-01-01: one shared FilterService for the frozen ``UnifiedFilter``.

There is exactly ONE filter semantics in this module — no
``XlsxFilterService`` / ``PdfFilterService`` / ``AnalyticsFilterService``.
Entity-specific entry points (``apply_to_universities``,
``paginate_universities``) all build on the same DTO and the same shared
predicate builders, so analytics, reports, P1 list adapters and the
frontend can never diverge.

Canonical relation mapping (real P1/P2 schema, no legacy tables):

* ``university_ids`` — ``universities.id IN (...)``.
* ``direction_ids`` — ``EXISTS`` a ``university_programs`` row whose
  ``it_programs.direction_id`` is selected (``University -> UniversityProgram
  -> ITProgram -> ITDirection``).
* ``program_ids`` — ``EXISTS`` ``university_programs.program_id IN (...)``.
* ``product_ids`` — ``EXISTS`` ``university_products.product_id IN (...)``
  (product, never vendor).
* ``responsible_ids`` — ``EXISTS`` ``university_responsibles`` for one of
  the selected responsibles (canonical M:N, no row duplication).
* ``date_from`` / ``date_to`` — inclusive bounds on the interaction date:
  ``EXISTS`` a ``meetings`` row in range OR a ``interaction_notes`` row in
  range (``University -> Meeting`` / ``University -> InteractionNote``).
* ``workflow_statuses`` — ``EXISTS`` a canonical ``workflow_instances`` row
  of the university whose runtime matches (canonical
  ``workflow_instances`` + ``instance_stages`` only; legacy
  ``app/modules/workflow/models.py`` is never used):

  - ``pending`` / ``completed`` / ``skipped`` — stored
    ``instance_stages.status`` matches;
  - ``current`` — the instance has a live runtime pointer
    (``current_instance_stage_id IS NOT NULL``);
  - ``overdue`` — an open stage (not ``completed``/``skipped``) with
    ``due_date < today`` and ``completed_at IS NULL``.

  Statuses reuse the frozen ``WorkflowStageStatus`` API enum; the
  ``workflow_instances.status`` header column is intentionally NOT used
  (production only ever writes ``'active'`` there, so it carries no
  filtering signal — see the P4-01-01 report).

Date semantics (centralized documented decision): ``date_from``/``date_to``
are inclusive bounds on the **interaction date** of the university. A
university enters the selection when it has at least one interaction whose
date falls inside the range — ``EXISTS`` over ``meetings.meeting_at`` OR
``interaction_notes.created_at`` (day-precision, UTC). The two interaction
sources are OR-combined inside one ``EXISTS``; no ``JOIN`` fan-out and no
row multiplication. Existing composites ``ix_meetings_univ_meeting_at`` and
``ix_interaction_notes_univ_created`` serve this predicate.

Row-grain note: the period decides **whether** a university is in the
selection, not how many rows it produces. Rows keep the dataset grain
``University LEFT JOIN License`` (one row per license + one fallback row
per license-less university), so a university with several interactions in
the range still appears as its own set of grain rows. A detailed
"one interaction = one row" journal would be a separate product decision
and a separate contract change.

A university with no interactions at all is therefore excluded as soon as
a period is set. Without a period (both bounds ``None``) nothing is
filtered by date, so interaction-less universities stay visible.

Combination: dimensions combine with ``AND``; values inside one
multi-select dimension combine with ``OR`` / ``IN``.

Security: the filter object never widens access. Apply the data scope
independently via :meth:`apply_security_scope` (conjunctive ``AND``):
a scoped user asking for a foreign university gets zero rows.

Performance: every method transforms ``Select -> Select`` with ``EXISTS``
subqueries (never ``JOIN`` fan-out, never SQL in a loop). List queries
stay at exactly 2 statements (COUNT + page), mirroring the P1 repository
convention.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import exists, func, or_, select
from sqlalchemy.sql.selectable import Select

from app.core.policies import apply_university_scope
from app.models.catalog import ITProgram, University, UniversityResponsible
from app.models.interactions import InteractionNote, Meeting, UniversityProduct, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.analytics.filters import UnifiedFilter
from app.schemas.common import WorkflowStageStatus

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.core.security import CurrentUser

#: Stored ``instance_stages.status`` values matched directly.
STORED_STAGE_STATUSES = frozenset({"pending", "completed", "skipped"})
#: Finished stages (excluded from the derived ``overdue`` branch).
CLOSED_STAGE_STATUSES = frozenset({"completed", "skipped"})

__all__ = [
    "CLOSED_STAGE_STATUSES",
    "STORED_STAGE_STATUSES",
    "UnifiedFilterService",
]


class UnifiedFilterService:
    """Single shared applicator for :class:`UnifiedFilter` (all static)."""

    # ------------------------------------------------------- shared builders

    @staticmethod
    def build_university_conditions(
        filters: UnifiedFilter, *, today: date | None = None
    ) -> list:
        """Reusable ``University`` predicates (AND-combined by the caller).

        Pure function of the DTO: no SQL is executed here, so report
        datasets (P4-01-02+) can reuse these predicates unchanged.
        """
        conds = []
        if filters.university_ids:
            conds.append(University.id.in_(list(filters.university_ids)))
        if filters.direction_ids:
            conds.append(
                exists(
                    select(1)
                    .select_from(UniversityProgram)
                    .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
                    .where(
                        UniversityProgram.university_id == University.id,
                        ITProgram.direction_id.in_(list(filters.direction_ids)),
                    )
                )
            )
        if filters.program_ids:
            conds.append(
                exists(
                    select(1)
                    .select_from(UniversityProgram)
                    .where(
                        UniversityProgram.university_id == University.id,
                        UniversityProgram.program_id.in_(list(filters.program_ids)),
                    )
                )
            )
        if filters.product_ids:
            conds.append(
                exists(
                    select(1)
                    .select_from(UniversityProduct)
                    .where(
                        UniversityProduct.university_id == University.id,
                        UniversityProduct.product_id.in_(list(filters.product_ids)),
                    )
                )
            )
        if filters.responsible_ids:
            conds.append(
                exists(
                    select(1)
                    .select_from(UniversityResponsible)
                    .where(
                        UniversityResponsible.university_id == University.id,
                        UniversityResponsible.responsible_id.in_(
                            list(filters.responsible_ids)
                        ),
                    )
                )
            )
        if filters.workflow_statuses:
            conds.append(
                UnifiedFilterService._workflow_exists(
                    list(filters.workflow_statuses), today=today
                )
            )
        if filters.date_from is not None or filters.date_to is not None:
            conds.append(
                UnifiedFilterService._interaction_in_period(
                    filters.date_from, filters.date_to
                )
            )
        return conds

    @staticmethod
    def _interaction_in_period(date_from, date_to):
        """``EXISTS`` at least one interaction inside the inclusive period.

        Two interaction sources are OR-combined: ``meetings.meeting_at`` and
        ``interaction_notes.created_at``. One open-ended bound simply omits
        that side of the range; both bounds set narrow it to the closed
        interval ``[date_from 00:00, date_to+1d 00:00)`` (UTC), which makes
        ``date_to`` inclusive at day precision. Aggregating the two sources
        into a single ``EXISTS`` keeps the university row set identical to
        every other consumer of :class:`UnifiedFilter`.
        """
        lower = (
            datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            if date_from is not None
            else None
        )
        upper = (
            datetime.combine(
                date_to + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
            if date_to is not None
            else None
        )

        def _bounded(column, value, *, closed: str):
            if value is None:
                return None
            return column >= value if closed == "ge" else column < value

        branches = []
        meeting_bounds = [
            bound
            for bound in (
                _bounded(Meeting.meeting_at, lower, closed="ge"),
                _bounded(Meeting.meeting_at, upper, closed="lt"),
            )
            if bound is not None
        ]
        if meeting_bounds:
            branches.append(
                exists(
                    select(1)
                    .select_from(Meeting)
                    .where(Meeting.university_id == University.id, *meeting_bounds)
                )
            )
        note_bounds = [
            bound
            for bound in (
                _bounded(InteractionNote.created_at, lower, closed="ge"),
                _bounded(InteractionNote.created_at, upper, closed="lt"),
            )
            if bound is not None
        ]
        if note_bounds:
            branches.append(
                exists(
                    select(1)
                    .select_from(InteractionNote)
                    .where(
                        InteractionNote.university_id == University.id, *note_bounds
                    )
                )
            )
        return or_(*branches)

    @staticmethod
    def _workflow_exists(statuses: list[WorkflowStageStatus], *, today=None):
        """One ``EXISTS`` over canonical instances; branches OR-combined."""
        day = today if today is not None else date.today()
        branches = []
        stored = sorted({s.value for s in statuses} & STORED_STAGE_STATUSES)
        if stored:
            branches.append(
                exists(
                    select(1)
                    .select_from(InstanceStage)
                    .where(
                        InstanceStage.instance_id == WorkflowInstance.id,
                        InstanceStage.status.in_(stored),
                    )
                )
            )
        if WorkflowStageStatus.CURRENT in statuses:
            branches.append(WorkflowInstance.current_instance_stage_id.is_not(None))
        if WorkflowStageStatus.OVERDUE in statuses:
            branches.append(
                exists(
                    select(1)
                    .select_from(InstanceStage)
                    .where(
                        InstanceStage.instance_id == WorkflowInstance.id,
                        InstanceStage.status.notin_(sorted(CLOSED_STAGE_STATUSES)),
                        InstanceStage.due_date.is_not(None),
                        InstanceStage.due_date < day,
                        InstanceStage.completed_at.is_(None),
                    )
                )
            )
        return exists(
            select(1)
            .select_from(WorkflowInstance)
            .where(
                WorkflowInstance.university_id == University.id,
                or_(*branches),
            )
        )

    @staticmethod
    def apply_to_report_dataset(
        stmt: Select, filters: UnifiedFilter, *, today: date | None = None
    ) -> Select:
        """Apply the filter to a P4-02 report dataset statement (Select->Select).

        The dataset grain is University LEFT JOIN licenses (one row per
        license + one fallback row per license-less university), so the SAME
        university-level predicates apply unchanged: dimensions combine with
        AND at the university level via EXISTS (never JOIN fan-out, never
        row multiplication). This keeps ``ReportDataset`` university sets
        identical to the P1 list for one filter. Date semantics: the period
        bounds the interaction date (``meetings`` / ``interaction_notes``),
        never license/contract dates and not the university creation date.
        """
        return UnifiedFilterService.apply_to_universities(stmt, filters, today=today)

    # ------------------------------------------------------- entity applicators

    @staticmethod
    def apply_to_universities(
        stmt: Select, filters: UnifiedFilter, *, today: date | None = None
    ) -> Select:
        """Apply the filter to a ``select(University ...)`` (Select->Select)."""
        conds = UnifiedFilterService.build_university_conditions(filters, today=today)
        if not conds:
            return stmt
        return stmt.where(*conds)

    @staticmethod
    def apply_security_scope(stmt: Select, user: CurrentUser) -> Select:
        """Conjunctive adapter to the canonical P5 university policy."""
        return apply_university_scope(stmt, University.id, user)

    # ------------------------------------------------- P1 list adapter (P4-01-02 seam)

    @staticmethod
    def paginate_universities(
        db: Session,
        filters: UnifiedFilter,
        *,
        page: int = 1,
        page_size: int = 20,
        today: date | None = None,
    ) -> tuple[list[University], int]:
        """Targeted P1-list adapter: filtered COUNT + one page, 2 statements.

        Proves the unified filter is usable by P1 list endpoints without
        touching the existing P1 catalog CRUD (full endpoint wiring belongs
        to P4-01-02). Deterministic order: ``name`` + ``id`` tie-break,
        mirroring the P1 repository convention.
        """
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be within 1..500")
        conds = UnifiedFilterService.build_university_conditions(filters, today=today)
        total = (
            db.execute(select(func.count()).select_from(University).where(*conds)).scalar()
            or 0
        )
        rows = (
            db.execute(
                select(University)
                .where(*conds)
                .order_by(University.name.asc(), University.id.asc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)
