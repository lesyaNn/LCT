"""P4-02 column registry: the single source of truth for report columns.

Every consumer (XLSX/PDF/JSON writers, frontend checkbox UI via
``docs/contracts/report-columns.json``) reads key/title/type/source from
here. Nothing is duplicated per exporter.

Row-grain note (see :mod:`app.modules.analytics.dataset`): business columns
(direction/program/product/vendor/software/contract/license/transfer/comment)
are read from the report row's own ``licenses`` row (``License.program_id``,
``License.product_id``, ``License.contract_id``). ``university_programs`` /
``university_products`` stay FILTER-only inputs (``UnifiedFilter`` EXISTS
predicates): a university passes a direction filter when ANY enrollment
matches, while its rows show each license's own direction. License-less
universities produce exactly one fallback row with business columns resolved
from the latest contract (or NULL). ``responsible`` is always an aggregated
``'; '``-joined string (never a fan-out), ``workflow_status`` /
``health_score`` are per-university scalars.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "COLUMN_REGISTRY",
    "DEFAULT_COLUMNS",
    "FULL_COLUMNS",
    "MANDATORY_COLUMNS",
    "MINIMAL_COLUMNS",
    "OPTIONAL_COLUMNS",
    "PRESETS",
    "STANDARD_COLUMNS",
    "UNSUPPORTED_OPTIONAL_COLUMNS",
    "EmptyReportColumnsError",
    "ReportColumn",
    "ReportColumnError",
    "UnknownReportColumnError",
    "is_known_column",
    "resolve_columns",
]


class ReportColumnError(ValueError):
    """Base error for column-selection problems (mapped to 422 by P4-03-01)."""


class UnknownReportColumnError(ReportColumnError):
    """Raised for unknown column keys (never silently ignored)."""


class EmptyReportColumnsError(ReportColumnError):
    """Raised for ``columns=[]`` (at least one column is required)."""


@dataclass(frozen=True)
class ReportColumn:
    """One report output column (immutable registry entry)."""

    key: str
    title: str
    data_type: str  # "string" | "date" | "integer"
    mandatory: bool
    source: str  # canonical model/table.column or derived helper
    needs_license_join: bool = False
    needs_responsible_agg: bool = False
    needs_workflow_scalar: bool = False
    needs_health_scalar: bool = False
    needs_fallback_contract: bool = False
    join_dependencies: frozenset[str] = field(default_factory=frozenset)


def _col(
    key: str,
    title: str,
    data_type: str,
    source: str,
    mandatory: bool = True,
    **flags,
) -> ReportColumn:
    deps = set()
    if flags.get("needs_license_join"):
        deps.update({"licenses", "it_products", "vendors", "it_programs", "it_directions"})
    if flags.get("needs_fallback_contract"):
        deps.add("contracts")
    if flags.get("needs_responsible_agg"):
        deps.add("responsibles")
    if flags.get("needs_workflow_scalar"):
        deps.add("workflow_instances")
    if flags.get("needs_health_scalar"):
        deps.add("health_score_snapshots")
    return ReportColumn(
        key=key,
        title=title,
        data_type=data_type,
        mandatory=mandatory,
        source=source,
        join_dependencies=frozenset(deps),
        **flags,
    )


COLUMN_REGISTRY: dict[str, ReportColumn] = {}
for _c in [
    _col(
        "university",
        "Наименование ВУЗа",
        "string",
        "universities.name (University.name)",
    ),
    _col(
        "direction",
        "ИТ-направление",
        "string",
        "licenses.program_id -> it_programs.direction_id -> it_directions.name "
        "(COALESCE licenses.direction_id, program direction); NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "program",
        "ИТ-программа",
        "string",
        "licenses.program_id -> it_programs.name (ITProgram.name); NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "product",
        "ИТ-продукт",
        "string",
        "licenses.product_id -> it_products.name (ITProduct.name); NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "workflow_status",
        "Статус работы",
        "string",
        "derived: current InstanceStage.name of the latest workflow_instances row "
        "for the university; else earliest university_programs.status "
        "(by program name); else NULL. Canonical workflow_instances + "
        "instance_stages only, never legacy workflow tables",
        needs_workflow_scalar=True,
    ),
    _col(
        "responsible",
        "Ответственный",
        "string",
        "derived aggregate: university_responsibles -> responsibles.full_name, "
        "sorted ascending, joined with '; ' (one row per report row, never fan-out); "
        "NULL when no links",
        needs_responsible_agg=True,
    ),
    _col(
        "vendor",
        "Вендор",
        "string",
        "licenses.product_id -> it_products.vendor_id -> vendors.name (Vendor.name); "
        "NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "software",
        "ПО",
        "string",
        "intentional alias of product: licenses.product_id -> it_products.name "
        "(no separate software model/field exists)",
        needs_license_join=True,
    ),
    _col(
        "contract_number",
        "Номер договора",
        "string",
        "licenses.contract_id -> contracts.contract_number for license rows; "
        "latest contracts row per university (signed_at DESC, expires_at DESC "
        "NULLS LAST, id ASC) for license-less fallback rows; else NULL",
        needs_license_join=True,
        needs_fallback_contract=True,
    ),
    _col(
        "license_signed",
        "Подписание лицензии",
        "date",
        "licenses.signed_at (License.signed_at, Date); NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "license_expires",
        "Срок действия",
        "date",
        "licenses.expires_at (License.expires_at, Date); NULL for fallback rows",
        needs_license_join=True,
    ),
    _col(
        "transfer_status",
        "Статус передачи",
        "string",
        "licenses.transfer_status_raw for license rows (real raw field, no new "
        "enum/constraint); latest contract transfer_status_raw for license-less "
        "fallback rows; else NULL",
        needs_license_join=True,
        needs_fallback_contract=True,
    ),
    _col(
        "comment",
        "Комментарий",
        "string",
        "COALESCE(licenses.comment, licenses.contract_id -> contracts.comment) "
        "for license rows; latest contract comment for license-less fallback "
        "rows; else NULL (both canonical comment fields exist)",
        needs_license_join=True,
        needs_fallback_contract=True,
    ),
    _col(
        "health_score",
        "Health Score",
        "integer",
        "latest health_score_snapshots.score per university "
        "(ORDER BY calculated_at DESC); NULL when no snapshot; optional Python "
        "fallback via canonical calculate_health_score (P2-07-08), never a new "
        "formula. int 0..100, missing is NULL (never 0)",
        needs_health_scalar=True,
    ),
    _col(
        "city",
        "Город",
        "string",
        "universities.city (University.city); NULL when unset",
        mandatory=False,
    ),
    _col(
        "current_stage",
        "Текущий этап",
        "string",
        "current InstanceStage.name of the latest workflow_instances row "
        "(primary branch of workflow_status WITHOUT the university_programs "
        "fallback); NULL when no workflow",
        mandatory=False,
        needs_workflow_scalar=True,
    ),
]:
    COLUMN_REGISTRY[_c.key] = _c
del _c

#: The 14 frozen mandatory keys (documented order = default output order).
MANDATORY_COLUMNS: tuple[str, ...] = (
    "university",
    "direction",
    "program",
    "product",
    "workflow_status",
    "responsible",
    "vendor",
    "software",
    "contract_number",
    "license_signed",
    "license_expires",
    "transfer_status",
    "comment",
    "health_score",
)

#: Supported optional columns (real canonical source exists).
OPTIONAL_COLUMNS: tuple[str, ...] = ("city", "current_stage")

#: Immutable default: all 14 mandatory columns.
DEFAULT_COLUMNS: tuple[str, ...] = MANDATORY_COLUMNS

#: Backend presets. FULL == STANDARD until more canonical sources are frozen.
MINIMAL_COLUMNS: tuple[str, ...] = MANDATORY_COLUMNS
STANDARD_COLUMNS: tuple[str, ...] = MANDATORY_COLUMNS + OPTIONAL_COLUMNS
FULL_COLUMNS: tuple[str, ...] = STANDARD_COLUMNS
PRESETS: dict[str, tuple[str, ...]] = {
    "MINIMAL": MINIMAL_COLUMNS,
    "STANDARD": STANDARD_COLUMNS,
    "FULL": FULL_COLUMNS,
}

#: Candidate optional columns WITHOUT a frozen canonical source (explicit gaps).
UNSUPPORTED_OPTIONAL_COLUMNS: dict[str, str] = {
    "last_interaction": "ambiguous: meetings.meeting_at vs interaction_notes.created_at; "
    "no frozen 'last interaction' definition",
    "workflow_progress": "no frozen percentage definition over instance_stages",
    "teacher_readiness": "per-teacher grain, no frozen per-row aggregation rule",
    "overdue_tasks": "countable from workflow_tasks, but the report-level "
    "'overdue' semantics is not frozen",
}


def is_known_column(key: str) -> bool:
    """Check a column key against the registry."""
    return key in COLUMN_REGISTRY


def resolve_columns(columns: list[str] | tuple[str, ...] | None) -> list[str]:
    """Validate + normalize a column selection (P4-02-02).

    * ``None`` -> all 14 mandatory columns (immutable default copy).
    * duplicates are collapsed preserving first-seen order;
    * unknown keys raise :class:`UnknownReportColumnError` (never ignored);
    * ``[]`` raises :class:`EmptyReportColumnsError` (at least one required).
    """
    if columns is None:
        return list(DEFAULT_COLUMNS)
    if not columns:
        raise EmptyReportColumnsError("at least one column is required")
    unknown = [c for c in columns if c not in COLUMN_REGISTRY]
    if unknown:
        raise UnknownReportColumnError(f"unknown report columns: {', '.join(unknown)}")
    seen: set[str] = set()
    out: list[str] = []
    for key in columns:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out
