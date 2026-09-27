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
* ``workflow_status`` and the fallback-contract fields are correlated scalar
  subqueries (columns, not statements, no fan-out).

Dynamic SELECT/JOINs (P4-02-02): only requested output columns are
selected; the ``licenses`` join tree is added only when a requested column
needs it; scalar subqueries are added only for requested columns. Filter
predicates use EXISTS independently of output columns, so e.g.
``columns=["university"]`` with ``direction_ids=[D1]`` still filters.

Null behavior: missing LEFT relations surface as ``None`` (never ``""`` /
``"N/A"``). Dates stay typed ``date`` values. Ordering is deterministic:
``University.name, University.id, License.license_number NULLS LAST,
License.id``.

Two row grains, chosen by the selected columns (not a surprise):
``University x License`` when at least one license-grain column is selected
(see :meth:`ReportDatasetService.license_grain_columns`), otherwise one row
per university — the license join is then not needed at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, datetime
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
from app.models.interactions import InteractionNote, Meeting, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask
from app.modules.analytics.analytics import AnalyticsService
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter

__all__ = [
    "ReportDataset",
    "ReportDatasetService",
    "fetch_preview",
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
    def _latest_program_id() -> Any:
        """Program chosen at workflow creation (latest instance that has one).

        The creation wizard binds direction -> program -> product and the API
        validates it (program linked to the university); the report reads it
        back here. Latest by ``updated_at`` (mirrors ``_latest_instance_id``),
        ``NULL`` when the university has no workflow with a program — the
        caller then falls through to the product catalog link.
        """
        return (
            select(WorkflowInstance.program_id)
            .where(
                WorkflowInstance.university_id == University.id,
                WorkflowInstance.program_id.is_not(None),
            )
            .order_by(WorkflowInstance.updated_at.desc(), WorkflowInstance.id.asc())
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

    # ------------------------------------------------------------ stat labels
    #
    # The label expressions below are the SINGLE definition of "what the
    # report shows in the direction / product / status column". Both the
    # tabular query (:meth:`build_query`) and the statistics aggregation
    # (:mod:`app.modules.analytics.stats`) compose these, so a chart can
    # never label a bucket differently from the table it summarises.

    @staticmethod
    def direction_label(
        lic_dir: Any = None, prog_dir: Any = None
    ) -> Any:
        """The ``direction`` cell expression (canonical chain, NULL if unset).

        ``lic_dir`` / ``prog_dir`` must be the SAME aliased tables the calling
        statement joins, otherwise the expression would reference tables that
        are not in its FROM clause.
        """
        lic_dir = lic_dir if lic_dir is not None else aliased(ITDirection)
        prog_dir = prog_dir if prog_dir is not None else aliased(ITDirection)
        wf_prog = aliased(ITProgram)
        wf_prog_dir = aliased(ITDirection)
        wf_prog_dir_name = (
            select(wf_prog_dir.name)
            .select_from(wf_prog)
            .join(wf_prog_dir, wf_prog_dir.id == wf_prog.direction_id)
            .where(wf_prog.id == ReportDatasetService._latest_program_id())
            .correlate(University)
            .scalar_subquery()
        )
        return func.coalesce(lic_dir.name, prog_dir.name, wf_prog_dir_name)

    @staticmethod
    def program_label(license_program: Any = None) -> Any:
        """The ``program`` cell expression (same join rule as above)."""
        license_program = license_program if license_program is not None else ITProgram
        wf_prog = aliased(ITProgram)
        wf_prog_name = (
            select(wf_prog.name)
            .where(wf_prog.id == ReportDatasetService._latest_program_id())
            .correlate(University)
            .scalar_subquery()
        )
        return func.coalesce(license_program.name, wf_prog_name)

    @staticmethod
    def product_label(license_product: Any = None) -> Any:
        """The ``product`` cell expression (same join rule as above)."""
        product = license_product if license_product is not None else ITProduct
        return product.name

    @staticmethod
    def workflow_status_label() -> Any:
        """The ``workflow_status`` cell expression (with program fallback)."""
        return func.coalesce(
            ReportDatasetService._current_stage_name(
                ReportDatasetService._latest_instance_id()
            ),
            ReportDatasetService._program_fallback_status(),
        )

    @staticmethod
    def license_grain_columns() -> tuple[str, ...]:
        """Columns that force the ``University x License`` row grain.

        Without any of them the dataset needs no license join and yields one
        row per university. Statistics use this to stay aligned with whatever
        the table would show.
        """
        return tuple(
            key
            for key, column in COLUMN_REGISTRY.items()
            if column.needs_license_join
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
            # Canonical chain (ТЗ): license direct link -> workflow program
            # (chosen at workflow creation). No product fallback: a university
            # without a workflow shows NULL (honest, never invented).
            # The label expressions come from the shared *_label() builders so
            # the statistics aggregation labels buckets identically.
            if "direction" in resolved:
                select_list.append(
                    ReportDatasetService.direction_label(lic_dir, prog_dir).label("direction")
                )
            if "program" in resolved:
                select_list.append(
                    ReportDatasetService.program_label(ITProgram).label("program")
                )
            if "product" in resolved:
                select_list.append(
                    ReportDatasetService.product_label(ITProduct).label("product")
                )
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
            current_name = ReportDatasetService._current_stage_name(
                ReportDatasetService._latest_instance_id()
            )
            if "workflow_status" in resolved:
                select_list.append(
                    ReportDatasetService.workflow_status_label().label("workflow_status")
                )
            if "current_stage" in resolved:
                select_list.append(current_name.label("current_stage"))

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
    ) -> ReportDataset:
        """Execute the dataset query (1 SELECT, +1 batched when needed).

        ``user`` confines the query to the caller's data scope.
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

        if any(COLUMN_REGISTRY[k].needs_university_maps for k in resolved):
            ReportDatasetService._attach_extra_maps(
                db, rows, resolved, today=today
            )


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
    def fetch_preview(
        db: Session,
        filters: UnifiedFilter,
        columns: list[str] | tuple[str, ...] | None,
        *,
        limit: int,
        user: Any | None = None,
        today: date | None = None,
    ) -> ReportDataset:
        """Bounded synchronous preview (ТЗ §7: filters + preview < 1s).

        Deliberately the SAME filters, the SAME row grain and the SAME
        selected columns as :meth:`fetch_rows` / :meth:`iterate_rows` — only
        ``LIMIT`` differs, and it applies **to the preview response only**.
        An export never goes through here, so an export is never truncated
        to the preview size.

        Two statements: one ``COUNT`` over the filtered subquery (the real
        selection size shown in the UI) and one page of rows. The row
        materialization is shared with :meth:`fetch_rows`, so the preview can
        never disagree with the exported content.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        stmt = ReportDatasetService.build_query(filters, columns, today=today)
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        resolved = list(stmt.get_execution_options().get("_report_columns", ()))
        need_resp = bool(stmt.get_execution_options().get("_need_responsible_agg"))

        # The COUNT is over the same filtered statement, so it counts the
        # export, not the preview page.
        total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

        mappings = list(db.execute(stmt.limit(limit).offset(0)).mappings().all())
        rows = [dict(mapping) for mapping in mappings]
        if need_resp:
            ReportDatasetService._attach_responsibles(db, rows)
        if any(COLUMN_REGISTRY[k].needs_university_maps for k in resolved):
            ReportDatasetService._attach_extra_maps(db, rows, resolved, today=today)
        for row in rows:
            row.pop("_license_id", None)
        universities = {
            row["_university_id"]
            for row in rows
            if isinstance(row.get("_university_id"), uuid.UUID)
        }
        public_rows = [
            {key: row[key] for key in resolved if key in row} for row in rows
        ]
        return ReportDataset(
            columns=resolved,
            rows=public_rows,
            total=total,
            # Universities on the returned page: the full selection size is
            # already carried by ``total`` rows and would need another query.
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
        need_extra = any(COLUMN_REGISTRY[k].needs_university_maps for k in resolved)

        resp_map: dict[uuid.UUID, str] = {}
        extra_maps: dict[str, dict[uuid.UUID, Any]] = {}
        if need_resp or need_extra:
            uids = AnalyticsService.filtered_university_ids(
                db, filters, user=user, today=today
            )
            if need_resp and uids:
                resp_map = ReportDatasetService._responsibles_map(db, uids)
            if need_extra and uids:
                extra_maps = ReportDatasetService._extra_maps(
                    db, uids, resolved, today=today
                )

        stmt = ReportDatasetService.build_query(filters, columns, today=today)
        if user is not None:
            stmt = UnifiedFilterService.apply_security_scope(stmt, user)
        exec_resolved = list(
            stmt.get_execution_options().get("_report_columns", resolved)
        )

        stream = db.execute(
            stmt.execution_options(yield_per=batch_size, stream_results=True)
        )
        mappings = stream.mappings()
        try:
            iterator = iter(mappings)
        except TypeError:  # lightweight unit doubles expose only `.all()`
            iterator = iter(mappings.all())
        for mapping in iterator:
            row = dict(mapping)
            if need_resp:
                uid = row.get("_university_id")
                row["responsible"] = (
                    resp_map.get(uid) if isinstance(uid, uuid.UUID) else None
                )
            if extra_maps:
                uid = row.get("_university_id")
                for col, mmap in extra_maps.items():
                    row[col] = mmap.get(uid) if isinstance(uid, uuid.UUID) else None
            # Contract parity with fetch_rows/_attach_extra_maps:
            # overdue_tasks is 0 when none (never null/missing in exports).
            if "overdue_tasks" in exec_resolved and row.get("overdue_tasks") is None:
                row["overdue_tasks"] = 0
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
    def _extra_maps(
        db: Session,
        uids: list[uuid.UUID],
        resolved: list[str],
        *,
        today: date | None = None,
    ) -> dict[str, dict[uuid.UUID, Any]]:
        """Batched university-grain maps for the P4-02-02 FULL columns.

        Frozen rules (see ``columns.py`` sources):
        * ``last_interaction`` — GREATEST(max meetings, max notes) as date;
        * ``workflow_progress`` — % completed over non-skipped stages of
          ACTIVE instances (Dev-2 matrix rule), nearest int;
        * ``overdue_tasks`` — P2 canonical overdue count on ACTIVE instances.
        Only requested columns are computed (bounded extra SELECTs, never
        per-row). Missing data -> ``None`` (``0`` for the overdue count).
        """
        day = today or date.today()
        maps: dict[str, dict[uuid.UUID, Any]] = {}

        def _as_date(value: Any) -> date | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            return None

        if "last_interaction" in resolved:
            last: dict[uuid.UUID, date] = {}
            for model, field in ((Meeting, Meeting.meeting_at),
                                 (InteractionNote, InteractionNote.created_at)):
                for uid, moment in db.execute(
                    select(model.university_id, func.max(field))
                    .where(model.university_id.in_(uids))
                    .group_by(model.university_id)
                ).all():
                    day_value = _as_date(moment)
                    if day_value is not None and day_value > last.get(uid, date.min):
                        last[uid] = day_value
            maps["last_interaction"] = last

        active_instances: dict[uuid.UUID, uuid.UUID] | None = None
        if "workflow_progress" in resolved or "overdue_tasks" in resolved:
            active_instances = {
                iid: uid
                for iid, uid in db.execute(
                    select(WorkflowInstance.id, WorkflowInstance.university_id)
                    .where(
                        WorkflowInstance.university_id.in_(uids),
                        WorkflowInstance.status == "active",
                    )
                ).all()
            }

        if "workflow_progress" in resolved:
            eligible: dict[uuid.UUID, int] = {}
            done: dict[uuid.UUID, int] = {}
            if active_instances:
                for uid, status in db.execute(
                    select(WorkflowInstance.university_id, InstanceStage.status)
                    .join(InstanceStage,
                          InstanceStage.instance_id == WorkflowInstance.id)
                    .where(WorkflowInstance.id.in_(list(active_instances)))
                ).all():
                    if status == "skipped":
                        continue
                    eligible[uid] = eligible.get(uid, 0) + 1
                    if status == "completed":
                        done[uid] = done.get(uid, 0) + 1
            maps["workflow_progress"] = {
                uid: round(done.get(uid, 0) / eligible[uid] * 100)
                for uid in eligible
            }

        if "overdue_tasks" in resolved:
            counts: dict[uuid.UUID, int] = {}
            if active_instances:
                for uid, total in db.execute(
                    select(WorkflowInstance.university_id, func.count(WorkflowTask.id))
                    .join(WorkflowTask,
                          WorkflowTask.instance_id == WorkflowInstance.id)
                    .where(
                        WorkflowInstance.id.in_(list(active_instances)),
                        WorkflowTask.status == "open",
                        WorkflowTask.deadline.is_not(None),
                        WorkflowTask.deadline < day,
                    )
                    .group_by(WorkflowInstance.university_id)
                ).all():
                    counts[uid] = int(total)
            maps["overdue_tasks"] = counts


        return maps

    @staticmethod
    def _attach_extra_maps(
        db: Session,
        rows: list[dict[str, Any]],
        resolved: list[str],
        *,
        today: date | None = None,
    ) -> None:
        """Attach FULL-column values to materialized rows (fetch path)."""
        uids = [r.get("_university_id") for r in rows]
        uids = [u for u in uids if isinstance(u, uuid.UUID)]
        maps = (
            ReportDatasetService._extra_maps(db, uids, resolved, today=today)
            if uids
            else {}
        )
        for row in rows:
            uid = row.get("_university_id")
            for col, mmap in maps.items():
                row[col] = mmap.get(uid) if isinstance(uid, uuid.UUID) else None
            if "overdue_tasks" in maps and row.get("overdue_tasks") is None:
                row["overdue_tasks"] = 0


#: Thin functional alias for :meth:`ReportDatasetService.fetch_preview`, so
#: the router does not reach into the service's private helpers.
fetch_preview = ReportDatasetService.fetch_preview
