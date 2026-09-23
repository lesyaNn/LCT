"""P4-02-01 report dataset: license-grain SELECT over the frozen UnifiedFilter.

Row grain (frozen decision): **one row per (University × License)** via
``universities LEFT JOIN licenses``; universities without licenses produce
exactly one fallback row with business columns resolved from the latest
contract (or NULL). Rationale:

* business detail (direction/program/product/vendor/contract/license) lives
  on the license row itself (``License.program_id/product_id/contract_id``),
  so joining it fans out exactly once per real business line — never the
  ``programs × products × responsibles`` cartesian product;
* filter dimensions stay university-level EXISTS predicates from
  :class:`UnifiedFilterService` (shared with the P1 list), so the dataset
  university set always equals the P1 list university set for one filter;
* ``responsible`` is aggregated (``'; '``-joined, sorted) in one batched
  Python-side query — deterministic order without PG-specific
  ordered-aggregate syntax, still a constant 2nd SELECT, never per-row;
* ``workflow_status`` / ``health_score`` / fallback-contract fields are
  correlated scalar subqueries (columns, not statements, no fan-out).

Dynamic SELECT/JOINs (P4-02-02): only requested output columns are
selected; the ``licenses`` join tree is added only when a requested column
needs it; scalar subqueries are added only for requested columns. Filter
predicates use EXISTS independently of output columns, so e.g.
``columns=["university"]`` with ``direction_ids=[D1]`` still filters.

Null behavior: missing LEFT relations surface as ``None`` (never ``""`` /
``"N/A"``). Dates stay typed ``date`` values; health is ``int 0..100`` or
``None`` (missing is never 0). Ordering is deterministic:
``University.name, University.id, License.license_number NULLS LAST,
License.id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

from sqlalchemy import case, func, nulls_last, select
from sqlalchemy.orm import Session, aliased

from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.models.health_score import HealthScoreSnapshot
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.analytics.analytics import AnalyticsService
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter

__all__ = [
    "ReportDataset",
    "ReportDatasetService",
]


class ReportDataset:
    """Materialized dataset (columns dynamic, values typed).

    ``rows`` contain exactly the requested output keys (plus no hidden
    columns); the university set behind the rows is exposed separately for
    P1-list consistency checks.
    """

    def __init__(
        self,
        *,
        columns: list[str],
        rows: list[dict[str, Any]],
        total: int,
        university_count: int,
        university_ids: set[uuid.UUID] | frozenset[uuid.UUID],
    ) -> None:
        self.columns = columns
        self.rows = rows
        self.total = total
        self.university_count = university_count
        self.university_ids = frozenset(university_ids)


class ReportDatasetService:
    """Production dataset builder (query only, never XLSX/PDF writers)."""

    # ------------------------------------------------------------ internals

    @staticmethod
    def _latest_instance_id() -> Any:
        return (
            select(WorkflowInstance.id)
            .where(WorkflowInstance.university_id == University.id)
            .order_by(WorkflowInstance.updated_at.desc(), WorkflowInstance.id.asc())
            .limit(1)
            .correlate(University)
            .scalar_subquery()
        )

    @staticmethod
    def _current_stage_name(latest_instance: Any) -> Any:
        return (
            select(InstanceStage.name)
            .select_from(WorkflowInstance)
            .join(
                InstanceStage,
                InstanceStage.id == WorkflowInstance.current_instance_stage_id,
            )
            .where(WorkflowInstance.id == latest_instance)
            .correlate(University)
            .scalar_subquery()
        )

    @staticmethod
    def _program_fallback_status() -> Any:
        return (
            select(UniversityProgram.status)
            .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
            .where(UniversityProgram.university_id == University.id)
            .order_by(ITProgram.name.asc(), ITProgram.id.asc())
            .limit(1)
            .correlate(University)
            .scalar_subquery()
        )

    @staticmethod
    def _latest_snapshot_score() -> Any:
        return (
            select(HealthScoreSnapshot.score)
            .where(HealthScoreSnapshot.university_id == University.id)
            .order_by(
                HealthScoreSnapshot.calculated_at.desc(),
                HealthScoreSnapshot.period_day.desc(),
                HealthScoreSnapshot.id.asc(),
            )
            .limit(1)
            .correlate(University)
            .scalar_subquery()
        )

    @staticmethod
    def _latest_contract_id() -> Any:
        return (
            select(Contract.id)
            .where(Contract.university_id == University.id)
            .order_by(
                Contract.signed_at.desc(),
                nulls_last(Contract.expires_at.desc()),
                Contract.id.asc(),
            )
            .limit(1)
            .correlate(University)
            .scalar_subquery()
        )

    @staticmethod
    def _fallback_contract_scalar(column: Any, latest_id: Any) -> Any:
        return (
            select(column).where(Contract.id == latest_id).correlate(University).scalar_subquery()
        )

    # ---------------------------------------------------------------- build

    @staticmethod
    def build_query(
        filters: UnifiedFilter,
        columns: list[str] | tuple[str, ...] | None,
        *,
        today: date | None = None,
    ):
        """Build the dataset SELECT for ``filters`` + ``columns``.

        Raises ``UnknownReportColumnError`` / ``EmptyReportColumnsError``
        (both ``ValueError``) for invalid selections — the future P4-03-01
        endpoint maps them to 422.
        """
        resolved = resolve_columns(columns)
        need_license = any(COLUMN_REGISTRY[k].needs_license_join for k in resolved)
        need_resp = any(COLUMN_REGISTRY[k].needs_responsible_agg for k in resolved)
        need_contract_fallback = any(COLUMN_REGISTRY[k].needs_fallback_contract for k in resolved)

        lic_dir = aliased(ITDirection)
        prog_dir = aliased(ITDirection)
        lic_contract = aliased(Contract)

        select_list: list[Any] = [University.id.label("_university_id")]
        if "university" in resolved:
            select_list.append(University.name.label("university"))
        if "city" in resolved:
            select_list.append(University.city.label("city"))
        if need_license:
            select_list.append(License.id.label("_license_id"))
            if "direction" in resolved:
                select_list.append(func.coalesce(lic_dir.name, prog_dir.name).label("direction"))
            if "program" in resolved:
                select_list.append(ITProgram.name.label("program"))
            if "product" in resolved:
                select_list.append(ITProduct.name.label("product"))
            if "software" in resolved:
                select_list.append(ITProduct.name.label("software"))
            if "vendor" in resolved:
                select_list.append(Vendor.name.label("vendor"))
            if "license_signed" in resolved:
                select_list.append(License.signed_at.label("license_signed"))
            if "license_expires" in resolved:
                select_list.append(License.expires_at.label("license_expires"))
            if need_contract_fallback:
                latest_id = ReportDatasetService._latest_contract_id()
                if "contract_number" in resolved:
                    select_list.append(
                        case(
                            (
                                License.id.is_(None),
                                ReportDatasetService._fallback_contract_scalar(
                                    Contract.contract_number, latest_id
                                ),
                            ),
                            else_=lic_contract.contract_number,
                        ).label("contract_number")
                    )
                if "transfer_status" in resolved:
                    select_list.append(
                        case(
                            (
                                License.id.is_(None),
                                ReportDatasetService._fallback_contract_scalar(
                                    Contract.transfer_status_raw, latest_id
                                ),
                            ),
                            else_=License.transfer_status_raw,
                        ).label("transfer_status")
                    )
                if "comment" in resolved:
                    select_list.append(
                        case(
                            (
                                License.id.is_(None),
                                ReportDatasetService._fallback_contract_scalar(
                                    Contract.comment, latest_id
                                ),
                            ),
                            else_=func.coalesce(License.comment, lic_contract.comment),
                        ).label("comment")
                    )
        if "workflow_status" in resolved or "current_stage" in resolved:
            latest = ReportDatasetService._latest_instance_id()
            current_name = ReportDatasetService._current_stage_name(latest)
            if "workflow_status" in resolved:
                fallback_status = ReportDatasetService._program_fallback_status()
                select_list.append(
                    func.coalesce(current_name, fallback_status).label("workflow_status")
                )
            if "current_stage" in resolved:
                select_list.append(current_name.label("current_stage"))
        if "health_score" in resolved:
            select_list.append(ReportDatasetService._latest_snapshot_score().label("health_score"))

        stmt = select(*select_list).select_from(University)
        if need_license:
            stmt = (
                stmt.outerjoin(License, License.university_id == University.id)
                .outerjoin(lic_contract, lic_contract.id == License.contract_id)
                .outerjoin(ITProduct, ITProduct.id == License.product_id)
                .outerjoin(Vendor, Vendor.id == ITProduct.vendor_id)
                .outerjoin(ITProgram, ITProgram.id == License.program_id)
                .outerjoin(lic_dir, lic_dir.id == License.direction_id)
                .outerjoin(prog_dir, prog_dir.id == ITProgram.direction_id)
            )
        stmt = UnifiedFilterService.apply_to_report_dataset(stmt, filters, today=today)
        order_cols: list[Any] = [University.name.asc(), University.id.asc()]
        if need_license:
            order_cols.extend([nulls_last(License.license_number.asc()), License.id.asc()])
        stmt = stmt.order_by(*order_cols)
        return stmt.execution_options(
            _report_columns=tuple(resolved),
            _need_responsible_agg=need_resp,
        )

    # ---------------------------------------------------------------- fetch

    @staticmethod
    def fetch_rows(
        db: Session,
        filters: UnifiedFilter,
        columns: list[str] | tuple[str, ...] | None,
        *,
        user: Any | None = None,
        today: date | None = None,
        health_fallback: bool = False,
    ) -> ReportDataset:
        """Execute the dataset query (1 SELECT, +1 batched when needed).

        ``user`` confines the query to the caller's data scope (same
        intersection as the P1 list). ``health_fallback`` fills missing
        snapshot scores via the canonical ``calculate_health_score``
        (bounded extra statements, only for universities without snapshots).
        """
        stmt = ReportDatasetService.build_query(filters, columns, today=today)
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        resolved = list(stmt.get_execution_options().get("_report_columns", ()))
        need_resp = bool(stmt.get_execution_options().get("_need_responsible_agg"))

        mappings = list(db.execute(stmt).mappings().all())
        rows: list[dict[str, Any]] = []
        for mapping in mappings:
            row = dict(mapping)
            rows.append(row)

        if need_resp:
            ReportDatasetService._attach_responsibles(db, rows)

        if health_fallback and "health_score" in resolved:
            ReportDatasetService._attach_health_fallback(db, rows, today=today)

        for row in rows:
            row.pop("_license_id", None)
        universities = {
            row["_university_id"]
            for row in rows
            if isinstance(row.get("_university_id"), uuid.UUID)
        }
        public_rows = []
        for row in rows:
            public = {key: row[key] for key in resolved if key in row}
            public_rows.append(public)
        return ReportDataset(
            columns=resolved,
            rows=public_rows,
            total=len(public_rows),
            university_count=len(universities),
            university_ids=universities,
        )

    @staticmethod
    def iterate_rows(
        db: Session,
        filters: UnifiedFilter,
        columns: list[str] | tuple[str, ...] | None,
        *,
        user: Any | None = None,
        today: date | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream dataset rows with bounded memory (P4-03-02 export path).

        Uses the SAME :meth:`build_query` (same predicates, same grain,
        same ordering) as :meth:`fetch_rows`, so streamed rows are
        value-identical to the materialized dataset. Memory model (honest):

        * the main SELECT streams via a server-side cursor (``yield_per`` +
          ``stream_results``): rows are produced one by one, never
          materialized with ``.all()``;
        * the ``responsible`` aggregate needs a university-keyed map. It is
          built ONCE upfront from the matching university ids (same
          ``UnifiedFilterService`` predicates via
          :meth:`AnalyticsService.filtered_university_ids`) with ONE batched
          SELECT — bounded by the university count, never by the row count,
          never per-row (no N+1);
        * while the cursor is open NO other query runs on this session, so
          no concurrent-cursor hazard exists.

        Total statements: 1 (ids) + 1 (responsibles map, only when a
        requested column needs it) + 1 streamed main SELECT.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        resolved = resolve_columns(columns)
        need_resp = any(COLUMN_REGISTRY[k].needs_responsible_agg for k in resolved)

        resp_map: dict[uuid.UUID, str] = {}
        if need_resp:
            uids = AnalyticsService.filtered_university_ids(
                db, filters, user=user, today=today
            )
            if uids:
                resp_map = ReportDatasetService._responsibles_map(db, uids)

        stmt = ReportDatasetService.build_query(filters, columns, today=today)
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        exec_resolved = list(
            stmt.get_execution_options().get("_report_columns", resolved)
        )

        stream = db.execute(
            stmt.execution_options(yield_per=batch_size, stream_results=True)
        )
        for mapping in stream.mappings():
            row = dict(mapping)
            if need_resp:
                uid = row.get("_university_id")
                row["responsible"] = (
                    resp_map.get(uid) if isinstance(uid, uuid.UUID) else None
                )
            row.pop("_license_id", None)
            yield {key: row[key] for key in exec_resolved if key in row}

    @staticmethod
    def _responsibles_map(
        db: Session, uids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """One batched ``university_id -> 'a; b'`` map (no per-row queries)."""
        pairs = list(
            db.execute(
                select(UniversityResponsible.university_id, Responsible.full_name)
                .join(
                    Responsible,
                    Responsible.id == UniversityResponsible.responsible_id,
                )
                .where(UniversityResponsible.university_id.in_(uids))
            ).all()
        )
        grouped: dict[uuid.UUID, list[str]] = {}
        for uid, name in pairs:
            grouped.setdefault(uid, []).append(name)
        return {uid: "; ".join(sorted(names)) for uid, names in grouped.items()}

    @staticmethod
    def _attach_responsibles(db: Session, rows: list[dict[str, Any]]) -> None:
        """One batched aggregate query (constant, never per-row).

        Deterministic ``'; '``-joined ``full_name`` ascending per university.
        """
        uids = [r.get("_university_id") for r in rows]
        uids = [u for u in uids if isinstance(u, uuid.UUID)]
        if not uids:
            for row in rows:
                row["responsible"] = None
            return
        joined = ReportDatasetService._responsibles_map(db, uids)
        for row in rows:
            uid = row.get("_university_id")
            row["responsible"] = joined.get(uid) if isinstance(uid, uuid.UUID) else None

    @staticmethod
    def _attach_health_fallback(
        db: Session, rows: list[dict[str, Any]], *, today: date | None = None
    ) -> None:
        """Fill NULL health scores via the canonical P2-07-08 calculator.

        Only universities WITHOUT a snapshot pay extra statements (bounded);
        the formula itself is never reimplemented here.
        """
        from app.modules.health_score.health_service import calculate_health_score

        missing: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for row in rows:
            if row.get("health_score") is None:
                uid = row.get("_university_id")
                if isinstance(uid, uuid.UUID):
                    missing.setdefault(uid, []).append(row)
        for uid, targets in missing.items():
            score = calculate_health_score(db, uid, today=today).score
            for target in targets:
                target["health_score"] = int(score)
