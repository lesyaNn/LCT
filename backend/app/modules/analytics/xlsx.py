"""P4-03-02 XLSX report generator (production exporter, no SQL inside).

Data comes ONLY from :class:`ReportDatasetService` (same filters, same row
grain, same selected columns, same health/workflow values as the dataset).
Column titles come ONLY from ``COLUMN_REGISTRY`` — there is no second
``XLSX_COLUMN_MAPPING``. ``UnifiedFilter`` semantics stay frozen (date bounds
on ``universities.created_at``, AND between dimensions, OR/IN within).

Workbook layout (frozen)::

    Sheet "Отчёт":
        Row 1: title (``Аналитический отчёт по взаимодействию с ВУЗами``)
        Row 2: period (``Период: ...`` / ``Период: не задан``)
        Row 3: applied filters (human-readable summary)
        Row 4: ``Сформирован: <tz-aware timestamp>``
        Row 5: empty
        Row 6: column headers (titles from ``COLUMN_REGISTRY``)
        Row 7+: data rows in ``ReportRequest.columns`` order
    Sheet "Фильтры": ``Параметр | Значение`` with the EXACT serialized
        filter request (all 8 ``UnifiedFilter`` fields, stable order).

Source-task contradiction resolution (regression-tested): the header row is
6, so ``freeze_panes = "A7"`` and ``auto_filter`` covers the header row
(``A6:<last>6``) — never ``A7:X7``. Metadata rows are excluded from the
filter range.

Memory model (honest): an ordinary ``openpyxl`` workbook (styles, freeze
panes, autofilter and widths require it; ``write_only`` mode cannot do
them) combined with a bounded DB iteration
(:meth:`ReportDatasetService.iterate_rows` streams rows one by one via a
server-side cursor). No fake "batch save every 1000 frees memory" claim:
the workbook itself stays in memory while DB access stays O(batch).

Output is written to ``<final>.part`` first and atomically replaced to the
final ``.xlsx`` only after a successful save; on failure the temp file is
removed and no partial file is left behind.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    Responsible,
    University,
)
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter

__all__ = [
    "FILTER_FIELD_ORDER",
    "HEADER_ROW",
    "MAX_COLUMN_WIDTH",
    "MIN_COLUMN_WIDTHS",
    "REPORT_SHEET",
    "FILTERS_SHEET",
    "REPORT_TITLE",
    "GeneratedReport",
    "build_filter_summary",
    "default_reports_dir",
    "format_period",
    "generate_xlsx_report",
    "sanitize_text",
    "serialize_filter_value",
]

#: Frozen workbook structure.
REPORT_TITLE = "Аналитический отчёт по взаимодействию с ВУЗами"
REPORT_SHEET = "Отчёт"
FILTERS_SHEET = "Фильтры"
HEADER_ROW = 6
DATA_START_ROW = 7

#: Stable audit order of the 8 frozen filter dimensions.
FILTER_FIELD_ORDER: tuple[str, ...] = (
    "date_from",
    "date_to",
    "university_ids",
    "direction_ids",
    "program_ids",
    "product_ids",
    "responsible_ids",
    "workflow_statuses",
)

#: XLSX *presentation* config only (key -> minimal width). This is not a
#: business/column registry: titles/types/sources stay single-sourced in
#: ``COLUMN_REGISTRY``. Optional columns carry a reasonable default here.
MIN_COLUMN_WIDTHS: dict[str, int | float] = {
    "university": 30,
    "direction": 25,
    "program": 30,
    "product": 25,
    "workflow_status": 20,
    "responsible": 20,
    "vendor": 20,
    "software": 25,
    "contract_number": 18,
    "license_signed": 14,
    "license_expires": 14,
    "transfer_status": 16,
    "comment": 40,
    "workflow_progress": 12,
    "city": 15,
    "current_stage": 20,
}
DEFAULT_MIN_WIDTH: int | float = 15
MAX_COLUMN_WIDTH: int | float = 60

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
HEADER_BORDER = Border(bottom=Side(style="thin", color="2F5597"))
THIN_BORDER = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)
TEXT_ALIGNMENT = Alignment(horizontal="left", vertical="center")
CENTER_ALIGNMENT = Alignment(horizontal="center", vertical="center")
DATE_NUMBER_FORMAT = "DD.MM.YYYY"

#: Cell-text prefixes that spreadsheet apps may interpret as formulas.
_FORMULA_PREFIXES = ("=", "+", "-", "@")
#: Max names per filter dimension in the human-readable summary (bounded).
_SUMMARY_NAMES_PER_DIMENSION = 5


@dataclass(frozen=True)
class GeneratedReport:
    """Result metadata for the job layer (P4-06-01 seam)."""

    path: Path
    size_bytes: int
    row_count: int
    generated_at: datetime
    columns: list[str]


def default_reports_dir() -> Path:
    """Configurable reports storage root (never the public static root)."""
    return Path(os.getenv("REPORTS_DIR", "/app/reports"))


def sanitize_text(value: str) -> str:
    """Escape formula-injection prefixes in user-controlled text.

    ``=...`` would otherwise be stored by openpyxl as a real formula cell
    (``data_type == "f"``); ``+``/``-``/``@`` prefixes are evaluated by
    some spreadsheet apps on open. A leading apostrophe keeps the value a
    plain-text cell while Excel displays it without the marker. Only
    ``str`` instances are touched — numeric values (including negative
    numbers) pass through unchanged by the caller, which branches on type.
    """
    if value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def format_period(filters: UnifiedFilter) -> str:
    """Row 2 text. Neutral when both bounds are absent (never invented)."""
    if filters.date_from is None and filters.date_to is None:
        return "Период: не задан"
    parts: list[str] = []
    if filters.date_from is not None:
        parts.append(f"с {filters.date_from:%d.%m.%Y}")
    if filters.date_to is not None:
        parts.append(f"по {filters.date_to:%d.%m.%Y}")
    return "Период: " + " ".join(parts)


def serialize_filter_value(field: str, value: Any) -> str:
    """EXACT raw serialization of one filter field for the audit sheet."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for item in value:
            items.append(item.value if hasattr(item, "value") else str(item))
        return ", ".join(items)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _short_names(names: list[str]) -> str:
    if len(names) <= _SUMMARY_NAMES_PER_DIMENSION:
        return ", ".join(names)
    head = ", ".join(names[:_SUMMARY_NAMES_PER_DIMENSION])
    return f"{head}… (+{len(names) - _SUMMARY_NAMES_PER_DIMENSION} ещё)"


def build_filter_summary(
    filters: UnifiedFilter, names: dict[str, dict[str, str]] | None = None,
) -> str:
    """Row 3 human-readable summary (raw values stay on sheet "Фильтры").

    UUID dimensions prefer display names from ``names`` (bounded/batched
    lookup); unknown ids fall back to short ``xxxx…`` forms — never N+1.
    """
    names = names or {}
    segments: list[str] = []
    labels = {
        "university_ids": "ВУЗы",
        "direction_ids": "Направления",
        "program_ids": "Программы",
        "product_ids": "Продукты",
        "responsible_ids": "Ответственные",
    }
    for field, label in labels.items():
        ids = list(getattr(filters, field))
        if not ids:
            continue
        known = names.get(field, {})
        display = [known.get(str(i), f"{str(i)[:8]}…") for i in ids]
        segments.append(f"{label}: {_short_names(display)}")
    if filters.workflow_statuses:
        statuses = [s.value for s in filters.workflow_statuses]
        segments.append(f"Статусы: {', '.join(statuses)}")
    if not segments:
        return "Фильтры: не применены"
    return "Фильтры: " + "; ".join(segments)


def _lookup_names(db: Session, filters: UnifiedFilter) -> dict[str, dict[str, str]]:
    """Batched id -> display-name maps (≤5 SELECTs, never N+1)."""
    out: dict[str, dict[str, str]] = {}
    specs = (
        ("university_ids", University, University.name),
        ("direction_ids", ITDirection, ITDirection.name),
        ("program_ids", ITProgram, ITProgram.name),
        ("product_ids", ITProduct, ITProduct.name),
        ("responsible_ids", Responsible, Responsible.full_name),
    )
    for field, model, label_col in specs:
        ids = list(getattr(filters, field))
        if not ids:
            continue
        rows = db.execute(
            select(model.id, label_col).where(model.id.in_(ids))
        ).all()
        out[field] = {str(row[0]): row[1] for row in rows}
    return out


def _ensure_tz_aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def generate_xlsx_report(
    db: Session,
    filters: UnifiedFilter,
    columns: list[str] | tuple[str, ...] | None,
    output_path: str | Path,
    *,
    user: Any | None = None,
    generated_at: datetime | None = None,
    batch_size: int = 1000,
) -> GeneratedReport:
    """Generate the frozen XLSX workbook from the report dataset.

    ``columns=None`` selects the frozen 14 mandatory ``DEFAULT_COLUMNS``;
    otherwise the resolved/deduped ``ReportRequest.columns`` order is kept
    verbatim (never sorted). Raises ``UnknownReportColumnError`` /
    ``EmptyReportColumnsError`` (both ``ValueError``) for invalid
    selections — the future P4-03-01 endpoint maps them to 422.
    """
    from openpyxl import Workbook

    resolved = resolve_columns(columns)
    moment = _ensure_tz_aware(generated_at)

    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(final_path.name + ".part")

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = REPORT_SHEET

        last_col = get_column_letter(len(resolved))
        ws.merge_cells(f"A1:{last_col}1")
        ws["A1"] = REPORT_TITLE
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = format_period(filters)
        names = _lookup_names(db, filters)
        ws["A3"] = build_filter_summary(filters, names)
        ws["A4"] = f"Сформирован: {moment:%d.%m.%Y %H:%M %Z}"
        # Row 5 stays empty by contract.

        for idx, key in enumerate(resolved, start=1):
            cell = ws.cell(row=HEADER_ROW, column=idx, value=COLUMN_REGISTRY[key].title)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = HEADER_BORDER

        widths: list[float] = [
            float(MIN_COLUMN_WIDTHS.get(key, DEFAULT_MIN_WIDTH)) for key in resolved
        ]
        for idx, key in enumerate(resolved):
            title_len = min(len(COLUMN_REGISTRY[key].title), 50)
            if title_len > widths[idx]:
                widths[idx] = float(title_len)

        row_count = 0
        for row in ReportDatasetService.iterate_rows(
            db, filters, resolved, user=user, batch_size=batch_size
        ):
            row_count += 1
            excel_row = DATA_START_ROW + row_count - 1
            for idx, key in enumerate(resolved, start=1):
                value = row.get(key)
                if value is None:
                    # Contract: missing relations stay EMPTY cells
                    # (never "N/A" / "null" / "-").
                    cell = ws.cell(row=excel_row, column=idx)
                    cell.border = THIN_BORDER
                    continue
                if isinstance(value, datetime):
                    cell = ws.cell(row=excel_row, column=idx, value=value)
                    cell.number_format = DATE_NUMBER_FORMAT
                    cell.alignment = CENTER_ALIGNMENT
                    estimate = 16
                elif isinstance(value, date):
                    cell = ws.cell(row=excel_row, column=idx, value=value)
                    cell.number_format = DATE_NUMBER_FORMAT
                    cell.alignment = CENTER_ALIGNMENT
                    estimate = 10
                elif isinstance(value, bool):
                    cell = ws.cell(row=excel_row, column=idx, value=int(value))
                    cell.alignment = CENTER_ALIGNMENT
                    estimate = 1
                elif isinstance(value, (int, float)):
                    # Numeric health score etc. stay numeric (never strings).
                    cell = ws.cell(row=excel_row, column=idx, value=value)
                    cell.alignment = CENTER_ALIGNMENT
                    estimate = len(str(value))
                else:
                    text = sanitize_text(str(value))
                    cell = ws.cell(row=excel_row, column=idx, value=text)
                    cell.alignment = TEXT_ALIGNMENT
                    estimate = min(len(text), 50)
                cell.border = THIN_BORDER
                col = idx - 1
                if estimate > widths[col]:
                    widths[col] = float(estimate)

        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = min(
                width, float(MAX_COLUMN_WIDTH)
            )

        # Frozen panes/filter geometry (see module docstring for the
        # A7:X7 contradiction): header row is 6.
        ws.freeze_panes = f"A{DATA_START_ROW}"
        ws.auto_filter.ref = f"A{HEADER_ROW}:{last_col}{HEADER_ROW}"

        audit = wb.create_sheet(FILTERS_SHEET)
        audit["A1"] = "Параметр"
        audit["B1"] = "Значение"
        for header_cell in (audit["A1"], audit["B1"]):
            header_cell.font = HEADER_FONT
            header_cell.fill = HEADER_FILL
            header_cell.alignment = HEADER_ALIGNMENT
            header_cell.border = HEADER_BORDER
        for offset, field in enumerate(FILTER_FIELD_ORDER, start=2):
            key_cell = audit.cell(row=offset, column=1, value=field)
            key_cell.border = THIN_BORDER
            val_cell = audit.cell(
                row=offset,
                column=2,
                value=serialize_filter_value(field, getattr(filters, field)),
            )
            val_cell.alignment = TEXT_ALIGNMENT
            val_cell.border = THIN_BORDER
        audit.column_dimensions["A"].width = 20
        audit.column_dimensions["B"].width = 60

        wb.save(tmp_path)
        tmp_path.replace(final_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    return GeneratedReport(
        path=final_path,
        size_bytes=final_path.stat().st_size,
        row_count=row_count,
        generated_at=moment,
        columns=resolved,
    )
