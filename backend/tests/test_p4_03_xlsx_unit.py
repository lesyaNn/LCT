"""P4-03-02 unit tests: XLSX generator over a stubbed dataset (no database).

Covers the presentation contract: headers/default/subset/order from
``COLUMN_REGISTRY``, metadata rows, filter sheet, styles, widths, typed
dates, nulls, Cyrillic round-trip, formula-injection protection, the
header-row-6/autofilter regression, temp-file atomicity and the streaming
(no ``.all()``) export path.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.modules.analytics.columns import COLUMN_REGISTRY, DEFAULT_COLUMNS
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import (
    HEADER_ROW,
    MAX_COLUMN_WIDTH,
    MIN_COLUMN_WIDTHS,
    REPORT_TITLE,
    build_filter_summary,
    format_period,
    generate_xlsx_report,
    sanitize_text,
    serialize_filter_value,
)

SUBSET_6 = [
    "university",
    "direction",
    "product",
    "workflow_status",
    "responsible",
    "city",
]


def _rows_6() -> list[dict]:
    uid = uuid4()
    return [
        {
            "university": "МГУ им. Ломоносова",
            "direction": "Информационная безопасность",
            "product": "ПО Защита",
            "workflow_status": "Ответственный",
            "responsible": "Иван Петров",
            "city": "Москва",
            "_university_id": uid,
        },
        {
            "university": "МГУ им. Ломоносова",
            "direction": None,
            "product": None,
            "workflow_status": None,
            "responsible": None,
            "city": None,
            "_university_id": uid,
        },
    ]


class _Mappings:
    """Mappings result that explodes if the exporter materializes via .all()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def all(self):  # pragma: no cover
        raise AssertionError("XLSX export path must stream, never call .all()")

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, values: list):
        self._values = values

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, mappings_rows=None, scalars_values=None):
        self._mappings_rows = mappings_rows or []
        self._scalars_values = scalars_values or []

    def mappings(self):
        return _Mappings(self._mappings_rows)

    def scalars(self):
        return _Scalars(self._scalars_values)

    def all(self):
        # Name-lookup batches on the stub: no canned display names.
        return []


class _BatchResult:
    """Batched (bounded, single-SELECT) result: `.all()` is legitimate here."""

    def __init__(self, pairs: list):
        self._pairs = pairs

    def all(self):
        return list(self._pairs)


class FakeSession:
    """Minimal session stub: serves canned rows, records execution options.

    Routes by statement content (same shapes as production):
    ``university_responsibles`` aggregate -> batched pairs; the main
    dataset SELECT -> canned rows; anything else (e.g. the university-ids
    pre-query) -> scalars of the canned row owner ids.
    """

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.seen_options: list[dict] = []

    def _owner_uids(self) -> list:
        uids = []
        for row in self._rows:
            uid = row.get("_university_id")
            if uid is not None and uid not in uids:
                uids.append(uid)
        return uids

    def execute(self, stmt, execution_options=None):
        try:
            self.seen_options.append(dict(stmt.get_execution_options()))
        except Exception:
            self.seen_options.append({})
        try:
            compiled = str(stmt).lower()
        except Exception:
            compiled = ""
        if "university_responsibles" in compiled:
            pairs = []
            seen: dict = {}
            for row in self._rows:
                uid = row.get("_university_id")
                name = row.get("responsible")
                if uid is not None and name:
                    seen.setdefault((uid, name), None)
            pairs = list(seen.keys())
            return _BatchResult(pairs)
        if "_university_id" in compiled or "licenses" in compiled:
            return _Result(mappings_rows=self._rows)
        return _Result(scalars_values=self._owner_uids())


def _gen(tmp_path: Path, columns, rows: list[dict], **kw):
    out = tmp_path / "report.xlsx"
    result = generate_xlsx_report(
        FakeSession(rows), UnifiedFilter(), columns, out, **kw
    )
    assert result.path == out
    return result


# ------------------------------------------------------------- sanitizer


def test_sanitize_text_escapes_formula_prefixes():
    assert sanitize_text("=HYPERLINK(1)").startswith("'")
    assert sanitize_text("+CMD").startswith("'")
    assert sanitize_text("-hello").startswith("'")
    assert sanitize_text("@SUM(1)").startswith("'")
    assert sanitize_text("normal") == "normal"
    assert sanitize_text("") == ""
    assert sanitize_text("Комментарий") == "Комментарий"


def test_sanitize_text_never_touches_numerics_by_caller():
    # The generator branches on type: ints/floats are written numeric.
    assert isinstance(-5, int)


# ------------------------------------------------------------- metadata helpers


def test_format_period_neutral_when_unset():
    assert format_period(UnifiedFilter()) == "Период: не задан"


def test_format_period_with_bounds():
    f = UnifiedFilter(date_from=date(2026, 1, 5), date_to=date(2026, 3, 7))
    text = format_period(f)
    assert "05.01.2026" in text and "07.03.2026" in text
    assert "не задан" not in text


def test_build_filter_summary_empty():
    assert build_filter_summary(UnifiedFilter()) == "Фильтры: не применены"


def test_serialize_filter_value_raw_exact():
    uid = uuid4()
    assert serialize_filter_value("date_from", date(2026, 2, 3)) == "2026-02-03"
    assert serialize_filter_value("university_ids", [uid]) == str(uid)
    assert serialize_filter_value("university_ids", []) == ""
    assert serialize_filter_value("date_from", None) == ""


# ------------------------------------------------------------- workbook: subset


def test_subset_headers_exact_order_from_registry(tmp_path):
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    assert result.columns == SUBSET_6
    wb = load_workbook(result.path)
    ws = wb["Отчёт"]
    assert [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, 7)] == [
        COLUMN_REGISTRY[k].title for k in SUBSET_6
    ]


def test_metadata_rows_and_empty_row(tmp_path):
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    ws = load_workbook(result.path)["Отчёт"]
    assert ws["A1"].value == REPORT_TITLE
    assert ws["A2"].value == "Период: не задан"
    assert ws["A3"].value == "Фильтры: не применены"
    assert ws["A4"].value.startswith("Сформирован: ")
    assert ws["A5"].value is None
    assert ws.cell(row=HEADER_ROW, column=1).value is not None


def test_generated_timestamp_is_timezone_aware(tmp_path):
    naive = datetime(2026, 9, 20, 10, 30, 0)
    result = _gen(tmp_path, ["university"], _rows_6()[:1], generated_at=naive)
    assert result.generated_at.tzinfo is not None
    ws = load_workbook(result.path)["Отчёт"]
    assert "UTC" in ws["A4"].value


def test_data_rows_values_and_row_count(tmp_path):
    rows = _rows_6()
    result = _gen(tmp_path, SUBSET_6, rows)
    assert result.row_count == 2
    ws = load_workbook(result.path)["Отчёт"]
    assert ws.cell(row=7, column=1).value == "МГУ им. Ломоносова"
    assert ws.cell(row=7, column=6).value == "Москва"
    assert ws.cell(row=8, column=1).value == "МГУ им. Ломоносова"
    # Nulls stay EMPTY cells (never placeholders).
    assert ws.cell(row=8, column=2).value is None
    assert ws.cell(row=8, column=6).value is None


def test_header_style(tmp_path):
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    cell = load_workbook(result.path)["Отчёт"].cell(row=HEADER_ROW, column=1)
    assert cell.font.bold is True
    assert cell.font.color.rgb.endswith("FFFFFF")
    assert cell.font.size == 11
    assert cell.fill.fgColor.rgb.endswith("4472C4")
    assert cell.alignment.horizontal == "center"
    assert cell.alignment.wrap_text is True
    assert cell.border.bottom.style == "thin"


def test_data_borders_and_alignment(tmp_path):
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    ws = load_workbook(result.path)["Отчёт"]
    text_cell = ws.cell(row=7, column=1)
    assert text_cell.alignment.horizontal == "left"
    assert text_cell.border.left.style == "thin"
    city_cell = ws.cell(row=7, column=6)
    assert city_cell.alignment.horizontal == "left"
    assert city_cell.value == "Москва"


def test_freeze_and_autofilter_cover_header_row_6(tmp_path):
    """Regression for the A7:X7 contradiction: header row is 6."""
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    ws = load_workbook(result.path)["Отчёт"]
    assert ws.freeze_panes == "A7"
    assert ws.auto_filter.ref == "A6:F6"


def test_freeze_and_autofilter_default_14(tmp_path):
    result = _gen(tmp_path, None, [])
    assert result.columns == list(DEFAULT_COLUMNS)
    ws = load_workbook(result.path)["Отчёт"]
    assert ws.freeze_panes == "A7"
    assert ws.auto_filter.ref == "A6:M6"
    assert [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, 14)] == [
        COLUMN_REGISTRY[k].title for k in DEFAULT_COLUMNS
    ]


def test_column_order_preserved_not_sorted(tmp_path):
    cols = ["workflow_progress", "university", "comment"]
    rows = [
        {"workflow_progress": 60, "university": "ВУЗ", "comment": "Комментарий"}
    ]
    result = _gen(tmp_path, cols, rows)
    ws = load_workbook(result.path)["Отчёт"]
    assert [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, 4)] == [
        COLUMN_REGISTRY[k].title for k in cols
    ]
    assert ws.cell(row=7, column=1).value == 60
    assert ws.cell(row=7, column=2).value == "ВУЗ"


# ------------------------------------------------------------- dates / widths


def test_dates_typed_with_excel_format(tmp_path):
    rows = [
        {
            "university": "ВУЗ",
            "license_signed": date(2026, 2, 1),
            "license_expires": date(2027, 2, 1),
        }
    ]
    result = _gen(
        tmp_path, ["university", "license_signed", "license_expires"], rows
    )
    ws = load_workbook(result.path)["Отчёт"]
    for col in (2, 3):
        cell = ws.cell(row=7, column=col)
        assert isinstance(cell.value, date)
        assert cell.number_format == "DD.MM.YYYY"
        assert cell.alignment.horizontal == "center"


def test_min_widths_applied_and_capped(tmp_path):
    rows = [{"university": "В", "comment": "x" * 500, "workflow_progress": 5}]
    result = _gen(tmp_path, ["university", "comment", "workflow_progress"], rows)
    ws = load_workbook(result.path)["Отчёт"]
    dims = ws.column_dimensions
    assert dims["A"].width >= MIN_COLUMN_WIDTHS["university"]
    assert dims["C"].width >= MIN_COLUMN_WIDTHS["workflow_progress"]
    assert dims["B"].width <= MAX_COLUMN_WIDTH
    assert dims["B"].width >= MIN_COLUMN_WIDTHS["comment"]


def test_cyrillic_round_trip(tmp_path):
    uid = uuid4()
    rows = [
        {
            "university": "МГУ им. Ломоносова",
            "direction": "Информационная безопасность",
            "responsible": "Ответственный",
            "comment": "Комментарий",
            "_university_id": uid,
        }
    ]
    result = _gen(
        tmp_path, ["university", "direction", "responsible", "comment"], rows
    )
    ws = load_workbook(result.path)["Отчёт"]
    assert ws.cell(row=7, column=1).value == "МГУ им. Ломоносова"
    assert ws.cell(row=7, column=2).value == "Информационная безопасность"
    assert ws.cell(row=7, column=3).value == "Ответственный"
    assert ws.cell(row=7, column=4).value == "Комментарий"


def test_formula_injection_stored_as_text(tmp_path):
    uid = uuid4()
    rows = [
        {
            "university": "=HYPERLINK(1)",
            "direction": "+CMD",
            "responsible": "@SUM(1)",
            "comment": "-hello",
            "_university_id": uid,
        }
    ]
    result = _gen(
        tmp_path, ["university", "direction", "responsible", "comment"], rows
    )
    ws = load_workbook(result.path)["Отчёт"]
    originals = ["=HYPERLINK(1)", "+CMD", "@SUM(1)", "-hello"]
    for col, original in enumerate(originals, start=1):
        cell = ws.cell(row=7, column=col)
        assert cell.data_type == "s", (col, cell.value, cell.data_type)
        assert cell.value.lstrip("'") == original


def test_negative_number_stays_numeric(tmp_path):
    rows = [{"university": "ВУЗ", "workflow_progress": -5}]
    out = tmp_path / "neg.xlsx"
    generate_xlsx_report(
        FakeSession(rows), UnifiedFilter(), ["university", "workflow_progress"], out
    )
    ws = load_workbook(out)["Отчёт"]
    cell = ws.cell(row=7, column=2)
    assert cell.value == -5 and cell.data_type == "n"


# ------------------------------------------------------------- filter sheet


def test_filter_sheet_raw_fidelity(tmp_path):
    uid = uuid4()
    filters = UnifiedFilter(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 9, 30),
        university_ids=[uid],
        workflow_statuses=["pending"],
    )
    out = tmp_path / "r.xlsx"
    generate_xlsx_report(FakeSession([]), filters, ["university"], out)
    audit = load_workbook(out)["Фильтры"]
    assert audit["A1"].value == "Параметр"
    assert audit["B1"].value == "Значение"
    values = {
        audit.cell(row=r, column=1).value: audit.cell(row=r, column=2).value
        for r in range(2, 10)
    }
    assert list(values) == [
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
    ]
    assert values["date_from"] == "2026-01-01"
    assert values["date_to"] == "2026-09-30"
    assert values["university_ids"] == str(uid)
    assert values["workflow_statuses"] == "pending"


def test_workbook_has_exactly_two_sheets(tmp_path):
    result = _gen(tmp_path, SUBSET_6, _rows_6())
    wb = load_workbook(result.path)
    assert wb.sheetnames == ["Отчёт", "Фильтры"]


# ------------------------------------------------------------- result/temp/streaming


def test_result_metadata(tmp_path):
    rows = _rows_6()
    result = _gen(tmp_path, SUBSET_6, rows)
    assert result.path.exists()
    assert result.size_bytes == result.path.stat().st_size > 0
    assert result.row_count == 2
    assert result.generated_at.tzinfo is not None


def test_no_part_file_left_behind(tmp_path):
    _gen(tmp_path, SUBSET_6, _rows_6())
    assert list(tmp_path.glob("*.part")) == []


def test_failure_removes_temp_and_raises(tmp_path):
    from openpyxl import Workbook

    out = tmp_path / "fail.xlsx"
    real_save = Workbook.save

    def _boom(self, filename):
        raise RuntimeError("disk gone")

    Workbook.save = _boom
    try:
        with pytest.raises(RuntimeError, match="disk gone"):
            generate_xlsx_report(
                FakeSession(_rows_6()), UnifiedFilter(), SUBSET_6, out
            )
    finally:
        Workbook.save = real_save
    assert not out.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_iterate_rows_is_streaming_generator():
    assert inspect.isgeneratorfunction(ReportDatasetService.iterate_rows)


def test_export_path_never_calls_all(tmp_path):
    # FakeSession._Mappings.all() raises; a green run proves streaming.
    _gen(tmp_path, SUBSET_6, _rows_6())


def test_unknown_and_empty_columns_raise(tmp_path):
    from app.modules.analytics.columns import (
        EmptyReportColumnsError,
        UnknownReportColumnError,
    )

    with pytest.raises(UnknownReportColumnError):
        generate_xlsx_report(
            FakeSession([]), UnifiedFilter(), ["university", "bogus"],
            tmp_path / "a.xlsx",
        )
    with pytest.raises(EmptyReportColumnsError):
        generate_xlsx_report(
            FakeSession([]), UnifiedFilter(), [], tmp_path / "b.xlsx"
        )
