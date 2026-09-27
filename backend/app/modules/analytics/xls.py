"""P4-03-02 XLS (BIFF8) report generator — legacy Excel format.

The ТЗ requires XLS *and* XLSX as separate export formats, so this is a
real legacy ``.xls`` workbook (BIFF8 via :mod:`xlwt`), not a renamed
``.xlsx``. It is built from the same single sources as every other exporter:

* data — :class:`~app.modules.analytics.dataset.ReportDatasetService` only,
  with the same :class:`~app.modules.analytics.filters.UnifiedFilter` and the
  same selected columns, so XLS and XLSX can never disagree about content;
* titles — ``COLUMN_REGISTRY`` only (no second column mapping);
* cell semantics (empty/date/numeric/sanitized text) —
  :mod:`app.modules.analytics.cells`, shared with the XLSX writer;
* workbook layout constants and the human-readable filter summary —
  :mod:`app.modules.analytics.xlsx`, so the metadata block cannot drift.

Only the *styling* is re-implemented, because BIFF8 and OOXML have no
shared styling API (xlwt has no autofilter and no freeze panes).

Known BIFF8 limits (see ``REPORTS_REVIEW.md``): at most 65 536 rows and 256
columns per sheet. The report block needs 6 metadata rows, so the data
capacity is ``65 536 - 6`` rows. Exceeding either limit raises
:class:`XlsCapacityError` and fails the job with a readable message instead
of writing a truncated file that would silently under-report. A CRM export
is far below that ceiling (the largest realistic selection is universities x
licenses), and XLSX remains the format to use for anything bigger.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import xlwt
from sqlalchemy.orm import Session

from app.modules.analytics.cells import classify_cell, estimate_width
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import (
    DATA_START_ROW,
    FILTER_FIELD_ORDER,
    FILTERS_SHEET,
    HEADER_ROW,
    MAX_COLUMN_WIDTH,
    MIN_COLUMN_WIDTHS,
    REPORT_SHEET,
    REPORT_TITLE,
    GeneratedReport,
    build_filter_summary,
    format_period,
    lookup_filter_names,
    serialize_filter_value,
    utc_aware,
)

__all__ = [
    "XLS_MAX_COLUMNS",
    "XLS_MAX_ROWS",
    "XlsCapacityError",
    "generate_xls_report",
]

#: Hard BIFF8 worksheet limits.
XLS_MAX_ROWS = 65_536
XLS_MAX_COLUMNS = 256

#: Header styling, matching the XLSX header (#4472C4 fill, white bold text).
_HEADER_FILL_RGB = 0x4472C4
_WHITE = 0xFFFFFF
_GREY = 0xBFBFBF

#: ``xlwt`` measures width in 1/256 of a character; 18 = 18 characters.
_WIDTH_UNIT = 256
#: xlwt number format string for DD.MM.YYYY.
_DATE_FORMAT = "DD.MM.YYYY"


class XlsCapacityError(ValueError):
    """The selection does not fit the BIFF8 sheet limits (never truncated)."""


def _border_style() -> xlwt.XFStyle:
    """Thin light-grey box: the BIFF8 equivalent of the XLSX thin border."""
    style = xlwt.XFStyle()
    style.left = style.right = style.top = style.bottom = 1
    style.left_colour = style.right_colour = _GREY
    style.top_colour = style.bottom_colour = _GREY
    return style


def _alignment(horizontal: str, *, wrap: bool = False) -> Any:
    align = xlwt.Alignment()
    align.horizontal = horizontal
    align.vertical = "center"
    align.wrap_text = wrap
    return align


def _font(*, bold: bool, height: int, colour: int) -> Any:
    font = xlwt.Font()
    font.bold = bold
    font.height = height
    font.colour = colour
    return font


def _styles() -> dict[str, Any]:
    """Build the small fixed style set once per workbook (never per row).

    Styles are constructed through the ``XFStyle``/``Font``/``Pattern``
    object API rather than ``easyxf`` spec strings, because ``easyxf``
    accepts only palette *indices* for colours and would silently paint the
    wrong colour instead of the intended RGB.
    """
    header = _border_style()
    header.font = _font(bold=True, height=220, colour=_WHITE)
    pattern = xlwt.Pattern()
    pattern.pattern = xlwt.Pattern.SOLID_PATTERN
    pattern.fore_colour = _HEADER_FILL_RGB
    header.pattern = pattern
    header.alignment = _alignment("center", wrap=True)

    title = _border_style()
    title.font = _font(bold=True, height=280, colour=0)

    text = _border_style()
    text.alignment = _alignment("left")

    center = _border_style()
    center.alignment = _alignment("center")

    dated = _border_style()
    dated.alignment = _alignment("center")
    dated.num_format_str = _DATE_FORMAT

    return {
        "header": header,
        "title": title,
        "text": text,
        "center": center,
        "date": dated,
    }


def _style_for(styles: dict[str, Any], kind: str) -> Any:
    """Map a shared cell kind to its BIFF8 style object."""
    if kind in ("date", "datetime"):
        return styles["date"]
    if kind == "number":
        return styles["center"]
    return styles["text"]


def _as_biff_datetime(value: date | datetime) -> datetime:
    """Convert a dataset date/datetime into what BIFF8 can store.

    BIFF8 date cells are plain serial numbers with **no timezone concept**,
    while the dataset hands out tz-aware ``timestamptz`` values. Writing an
    aware datetime directly raises inside ``xlwt``, and silently shifting
    the wall clock would misreport the date, so an aware value is converted
    to UTC and then made naive. A bare ``date`` becomes midnight.
    """
    if isinstance(value, datetime):
        moment = value
    else:
        return datetime.combine(value, datetime.min.time())
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment

def generate_xls_report(
    db: Session,
    filters: UnifiedFilter,
    columns: list[str] | tuple[str, ...] | None,
    output_path: str | Path,
    *,
    user: Any | None = None,
    generated_at: datetime | None = None,
    batch_size: int = 1000,
) -> GeneratedReport:
    """Generate a legacy ``.xls`` workbook from the report dataset.

    ``columns=None`` selects the ТЗ default ``DEFAULT_COLUMNS``; otherwise
    the resolved/deduped order is kept verbatim (never sorted). Raises
    ``UnknownReportColumnError`` / ``EmptyReportColumnsError`` for an invalid
    selection (the endpoint maps them to 422) and :class:`XlsCapacityError`
    when the selection exceeds the BIFF8 limits.
    """
    resolved = resolve_columns(columns)
    if len(resolved) > XLS_MAX_COLUMNS:
        raise XlsCapacityError(
            f"XLS supports at most {XLS_MAX_COLUMNS} columns, requested {len(resolved)}"
        )
    moment = utc_aware(generated_at)

    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(final_path.name + ".part")

    try:
        book = xlwt.Workbook(encoding="utf-8")
        sheet = book.add_sheet(REPORT_SHEET)
        styles = _styles()

        # Same metadata block as XLSX: title/period/filters/timestamp, row 5
        # empty, header on row 6, data from row 7.
        names = lookup_filter_names(db, filters)
        sheet.write(0, 0, REPORT_TITLE, styles["title"])
        sheet.write(1, 0, format_period(filters))
        sheet.write(2, 0, build_filter_summary(filters, names))
        sheet.write(3, 0, f"Сформирован: {moment:%d.%m.%Y %H:%M %Z}")

        widths: list[float] = []
        for idx, key in enumerate(resolved):
            sheet.write(
                HEADER_ROW - 1, idx, COLUMN_REGISTRY[key].title, styles["header"]
            )
            widths.append(
                float(max(MIN_COLUMN_WIDTHS.get(key, 15), min(len(COLUMN_REGISTRY[key].title), 50)))
            )

        row_count = 0
        for row in ReportDatasetService.iterate_rows(
            db, filters, resolved, user=user, batch_size=batch_size
        ):
            row_count += 1
            excel_row = DATA_START_ROW + row_count - 1
            if excel_row > XLS_MAX_ROWS:
                raise XlsCapacityError(
                    f"XLS supports at most {XLS_MAX_ROWS - HEADER_ROW} data rows "
                    f"(sheet limit {XLS_MAX_ROWS} including the {HEADER_ROW} "
                    "metadata rows); narrow the period or use XLSX"
                )
            for idx, key in enumerate(resolved):
                cell_value = classify_cell(row.get(key))
                if cell_value.kind == "empty":
                    # Contract: missing relations stay EMPTY cells.
                    sheet.write(excel_row - 1, idx, "", styles["text"])
                    continue
                style = _style_for(styles, cell_value.kind)
                if cell_value.kind in ("date", "datetime"):
                    sheet.write(
                        excel_row - 1, idx, _as_biff_datetime(cell_value.value), style
                    )
                else:
                    sheet.write(excel_row - 1, idx, cell_value.value, style)
                estimate = estimate_width(cell_value)
                if estimate > widths[idx]:
                    widths[idx] = float(estimate)

        for idx, width in enumerate(widths):
            sheet.col(idx).width = int(min(width, float(MAX_COLUMN_WIDTH)) * _WIDTH_UNIT)

        _write_filters_sheet(book, filters, styles)
        book.save(str(tmp_path))
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
        columns=list(resolved),
    )


def _write_filters_sheet(book: Any, filters: UnifiedFilter, styles: dict[str, Any]) -> None:
    """Sheet "Фильтры" — EXACT serialized filter request, same as XLSX."""
    audit = book.add_sheet(FILTERS_SHEET)
    audit.write(0, 0, "Параметр", styles["header"])
    audit.write(0, 1, "Значение", styles["header"])
    for offset, field in enumerate(FILTER_FIELD_ORDER, start=1):
        audit.write(offset, 0, field, styles["text"])
        audit.write(
            offset,
            1,
            serialize_filter_value(field, getattr(filters, field)),
            styles["text"],
        )
    audit.col(0).width = 20 * _WIDTH_UNIT
    audit.col(1).width = 60 * _WIDTH_UNIT
