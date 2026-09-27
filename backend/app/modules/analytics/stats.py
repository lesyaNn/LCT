"""Report statistics: SQL aggregation over the SAME selection as the table.

ТЗ asks for charts and graphs of the filtered report. Two properties matter
more than the chart type:

* **one selection** — the statistics must be computed from exactly the rows
  the table shows. Reusing :class:`UnifiedFilter` and
  :class:`UnifiedFilterService` is what guarantees that: the period,
  universities, directions, products, responsibles and the security scope are
  interpreted in one place, never re-implemented here.
* **aggregation in the database** — counting is ``GROUP BY``, done by
  PostgreSQL. The alternative (stream every row into Python and count there)
  would make the statistics path the slowest part of the system and would
  fight the "10 parallel reports" requirement, so it is deliberately not
  implemented.

The bucket labels reuse the dataset's own label expressions
(:meth:`ReportDatasetService.direction_label` and friends), and the aliases
they are bound to are the ones the shared FROM clause joins, so a chart can
never name a bucket differently from the column it summarises.

Grain, stated honestly per dimension:

* ``by_direction`` / ``by_product`` / ``by_workflow_status`` count **report
  rows** at the ``University x License`` grain, i.e. what the table shows
  when a license-grain column is selected. Rows whose dimension is NULL are
  counted into a ``Без данных`` bucket rather than dropped, so the buckets
  always add up to the reported row count.
* ``by_responsible`` counts **distinct universities** per person. The
  ``responsible`` table cell is a ``'; '``-joined list of a university's
  responsibles, which is not a value you can group by; that chart is about
  universities, and the response says so in its ``unit`` field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import String, distinct, func, select
from sqlalchemy.orm import Session, aliased

from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
)
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter

__all__ = [
    "DIMENSION_TITLES",
    "NO_VALUE_LABEL",
    "ReportStats",
    "ReportStatsService",
    "StatBucket",
    "StatSlice",
]

#: Bucket for rows whose dimension value is NULL. Reporting the count keeps
#: the buckets equal to the total instead of quietly losing rows.
NO_VALUE_LABEL = "Без данных"

#: Datasets charts may show, in display order. The keys double as the
#: ``dimension`` values in the API response.
STAT_DIMENSIONS: tuple[str, ...] = (
    "by_direction",
    "by_product",
    "by_workflow_status",
    "by_responsible",
)

#: Human-readable dimension titles, reused by the chart exporter and the PDF.
DIMENSION_TITLES: dict[str, str] = {
    "by_direction": "Распределение строк по ИТ-направлениям",
    "by_product": "Распределение строк по ИТ-продуктам",
    "by_workflow_status": "Распределение строк по статусу работы",
    "by_responsible": "Распределение вузов по ответственным",
}


@dataclass(frozen=True)
class StatBucket:
    """One bar of a chart: a label and how many entities it holds."""

    label: str
    count: int


@dataclass(frozen=True)
class StatSlice:
    """One dimension's distribution, with its unit made explicit."""

    dimension: str
    title: str
    #: ``"rows"`` (report rows) or ``"universities"`` (distinct universities).
    unit: str
    total: int
    buckets: tuple[StatBucket, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReportStats:
    """Aggregated view of one filtered selection."""

    #: Distinct universities in the selection.
    university_count: int
    #: Report rows at the dataset grain (the table's row count).
    row_count: int
    slices: tuple[StatSlice, ...] = field(default_factory=tuple)

    def slice(self, dimension: str) -> StatSlice | None:
        for item in self.slices:
            if item.dimension == dimension:
                return item
        return None


@dataclass(frozen=True)
class _Aliases:
    """The aliased tables the shared FROM clause and the labels share.

    Passing the *same* alias objects to both is what keeps a ``GROUP BY``
    label identical to the corresponding table column; separate ``aliased()``
    instances would produce SQL that references tables outside the FROM clause.
    """

    lic_dir: Any
    prog_dir: Any
    wf_prog: Any
    wf_prog_dir: Any


class ReportStatsService:
    """SQL aggregation for the report statistics (never row-by-row)."""

    #: Max bars per dimension; the tail is folded into one bucket so a chart
    #: never becomes an unreadable wall of slivers.
    MAX_BUCKETS = 10

    @staticmethod
    def build(
        db: Session,
        filters: UnifiedFilter,
        *,
        user: Any | None = None,
        today: date | None = None,
    ) -> ReportStats:
        """Aggregate the filtered selection (one statement per dimension)."""
        university_count = int(
            db.scalar(
                select(func.count()).select_from(
                    ReportStatsService._filtered_universities(
                        filters, user=user, today=today
                    ).subquery()
                )
            )
            or 0
        )
        row_count = int(
            db.scalar(
                select(func.count()).select_from(
                    ReportStatsService._filtered_rows(
                        filters, user=user, today=today
                    ).stmt.subquery()
                )
            )
            or 0
        )

        base = ReportStatsService._filtered_rows(filters, user=user, today=today)
        slices = (
            ReportStatsService._label_distribution(
                db,
                base,
                ReportDatasetService.direction_label(
                    base.aliases.lic_dir, base.aliases.prog_dir
                ),
                "by_direction",
            ),
            ReportStatsService._label_distribution(
                db,
                base,
                ReportDatasetService.product_label(base.product),
                "by_product",
            ),
            ReportStatsService._label_distribution(
                db,
                base,
                ReportDatasetService.workflow_status_label(),
                "by_workflow_status",
            ),
            ReportStatsService._responsible_distribution(
                db, filters, user=user, today=today
            ),
        )
        return ReportStats(
            university_count=university_count,
            row_count=row_count,
            slices=tuple(slices),
        )

    # ------------------------------------------------------------- statements

    @staticmethod
    def _filtered_universities(
        filters: UnifiedFilter, *, user: Any | None, today: date | None
    ):
        """The selection at university grain (the filter's natural grain)."""
        stmt = select(University.id)
        stmt = UnifiedFilterService.apply_to_report_dataset(
            stmt, filters, today=today
        )
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        return stmt

    @staticmethod
    def _filtered_rows(
        filters: UnifiedFilter, *, user: Any | None, today: date | None
    ):
        """The selection at the dataset grain (``University x License``).

        The joins mirror :meth:`ReportDatasetService.build_query` so a
        ``GROUP BY`` on a label expression can only resolve against tables that
        are actually present.
        """
        aliases = _Aliases(
            lic_dir=aliased(ITDirection),
            prog_dir=aliased(ITDirection),
            wf_prog=aliased(ITProgram),
            wf_prog_dir=aliased(ITDirection),
        )
        product = aliased(ITProduct)
        program = aliased(ITProgram)
        stmt = (
            select(University.id)
            .select_from(University)
            .outerjoin(License, License.university_id == University.id)
            .outerjoin(product, product.id == License.product_id)
            .outerjoin(program, program.id == License.program_id)
            .outerjoin(aliases.lic_dir, aliases.lic_dir.id == License.direction_id)
            .outerjoin(aliases.prog_dir, aliases.prog_dir.id == program.direction_id)
        )
        stmt = UnifiedFilterService.apply_to_report_dataset(
            stmt, filters, today=today
        )
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        return _RowSelection(stmt=stmt, aliases=aliases, product=product)

    # ----------------------------------------------------------- aggregation

    @staticmethod
    def _label_distribution(
        db: Session,
        base: "_RowSelection",
        label: Any,
        dimension: str,
    ) -> StatSlice:
        """``GROUP BY <label>`` with the NULL bucket kept.

        The label is resolved by an **inner** query and grouped by an **outer**
        one. This is not stylistic: the label expressions are correlated scalar
        subqueries (``.correlate(University)``), and evaluating them directly
        in a ``GROUP BY`` breaks the correlation — the subquery then scans the
        whole table and multiplies rows, so the bars stop adding up to the row
        count. Resolving the label per row first keeps the expression identical
        to the table cell and the counts exact.

        One statement per dimension. ``total`` is summed from the buckets, so
        the response can never claim a total the bars do not add up to.
        """
        resolved = base.with_label(label).subquery()
        # Reference the *derived table's* column. Re-referencing the inner
        # Select's column here would make SQLAlchemy render a fresh correlated
        # subquery per outer row and multiply the counts.
        bucket = func.coalesce(
            func.nullif(func.cast(resolved.c.label, String), ""), NO_VALUE_LABEL
        )
        rows = db.execute(
            select(bucket.label("label"), func.count().label("count"))
            .select_from(resolved)
            .group_by(bucket)
            .order_by(func.count().desc(), bucket.asc())
        ).all()
        buckets = ReportStatsService._fold_tail(
            [StatBucket(str(r[0]), int(r[1])) for r in rows]
        )
        return StatSlice(
            dimension=dimension,
            title=DIMENSION_TITLES[dimension],
            unit="rows",
            total=sum(b.count for b in buckets),
            buckets=tuple(buckets),
        )

    @staticmethod
    def _responsible_distribution(
        db: Session, filters: UnifiedFilter, *, user: Any | None, today: date | None
    ) -> StatSlice:
        """Distinct universities per responsible, from the same selection."""
        selected = ReportStatsService._filtered_universities(
            filters, user=user, today=today
        ).subquery()
        count_unis = func.count(distinct(UniversityResponsible.university_id))
        rows = db.execute(
            select(Responsible.full_name, count_unis)
            .select_from(selected)
            .join(
                UniversityResponsible,
                UniversityResponsible.university_id == selected.c.id,
            )
            .join(Responsible, Responsible.id == UniversityResponsible.responsible_id)
            .group_by(Responsible.full_name)
            .order_by(count_unis.desc(), Responsible.full_name.asc())
        ).all()
        buckets = ReportStatsService._fold_tail(
            [StatBucket(str(r[0]), int(r[1])) for r in rows]
        )
        return StatSlice(
            dimension="by_responsible",
            title=DIMENSION_TITLES["by_responsible"],
            unit="universities",
            total=sum(b.count for b in buckets),
            buckets=tuple(buckets),
        )

    @staticmethod
    def _fold_tail(buckets: list[StatBucket]) -> list[StatBucket]:
        """Keep the top ``MAX_BUCKETS``; fold the rest into one honest bucket."""
        if len(buckets) <= ReportStatsService.MAX_BUCKETS:
            return buckets
        head = buckets[: ReportStatsService.MAX_BUCKETS]
        rest = buckets[ReportStatsService.MAX_BUCKETS :]
        return [*head, StatBucket("Прочее", sum(b.count for b in rest))]


@dataclass(frozen=True)
class _RowSelection:
    """A filtered statement plus the aliases its label expressions bind to."""

    stmt: Any
    aliases: _Aliases
    product: Any

    def with_label(self, label: Any) -> Any:
        """Project the label as a column, keeping the row grain intact.

        The label is selected in the same statement that produces the rows (so
        the correlated subqueries still correlate) and only then grouped by the
        caller. Adding the column does not change the number of rows, so the
        counts stay the report's row counts.
        """
        return self.stmt.add_columns(label.label("label"))
