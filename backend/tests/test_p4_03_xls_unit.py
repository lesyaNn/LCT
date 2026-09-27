"""Unit tests for the legacy XLS (BIFF8) report generator (no database).

The generator is verified against the *content* of the produced workbook by
reading it back with ``xlrd`` (the reader for BIFF8), so the assertions are
about what a user actually sees in Excel, not about internal calls.
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import xlrd

from app.modules.analytics.columns import COLUMN_REGISTRY, DEFAULT_COLUMNS
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import (
    DATA_START_ROW,
    FILTER_FIELD_ORDER,
    FILTERS_SHEET,
    HEADER_ROW,
    REPORT_SHEET,
    REPORT_TITLE,
)
from app.modules.analytics.xls import XlsCapacityError, generate_xls_report
from tests.test_p4_03_xlsx_unit import FakeSession

MOMENT = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _gen(tmp_path: Path, columns, rows: list[dict], **kw):
    out = tmp_path / "report.xls"
    result = generate_xls_report(FakeSession(rows), UnifiedFilter(), columns, out, **kw)
    assert result.path == out
    return result


def _read(tmp_path: Path, rows: list[dict], columns=None, **kw):
    """Generate + read back, returning (result, book)."""
    result = _gen(tmp_path, columns, rows, generated_at=MOMENT, **kw)
    return result, xlrd.open_workbook(str(result.path), formatting_info=False)


def _cell(book, sheet_name, row: int, col: int):
    return book.sheet_by_name(sheet_name).cell(row, col)


# ------------------------------------------------------------- basic structure


def test_generates_a_real_legacy_biff8_file(tmp_path):
    result = _gen(tmp_path, None, [{"university": "МГУ"}], generated_at=MOMENT)
    assert result.path.exists()
    assert result.size_bytes > 0
    assert result.columns == list(DEFAULT_COLUMNS)
    # BIFF8 magic: OLE2 compound file, not a ZIP (which is what XLSX is).
    assert result.path.read_bytes()[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def test_sheet_names_and_header_row_match_xlsx_contract(tmp_path):
    _result, book = _read(tmp_path, [{"university": "МГУ"}])
    assert book.sheet_names() == [REPORT_SHEET, FILTERS_SHEET]
    sheet = book.sheet_by_name(REPORT_SHEET)
    assert sheet.cell(0, 0).value == REPORT_TITLE
    assert sheet.cell(1, 0).value == "Период: не задан"
    assert sheet.cell(3, 0).value.startswith("Сформирован:")
    # Row 5 is empty by contract; xlrd indexes from 0, so it is index 4.
    assert sheet.cell(4, 0).value == ""
    titles = [sheet.cell(HEADER_ROW - 1, i).value for i in range(len(DEFAULT_COLUMNS))]
    assert titles == [COLUMN_REGISTRY[k].title for k in DEFAULT_COLUMNS]


def test_data_starts_on_row_seven_and_keeps_requested_order(tmp_path):
    cols = ["workflow_status", "university", "comment"]
    _result, book = _read(
        tmp_path,
        [{"workflow_status": "Согласование", "university": "ВУЗ", "comment": "Текст"}],
        columns=cols,
    )
    sheet = book.sheet_by_name(REPORT_SHEET)
    header = HEADER_ROW - 1          # 0-based index of the 1-based header row 6
    first_data = DATA_START_ROW - 1  # 0-based index of the 1-based first data row 7
    assert [sheet.cell(header, i).value for i in range(3)] == [
        COLUMN_REGISTRY["workflow_status"].title,
        COLUMN_REGISTRY["university"].title,
        COLUMN_REGISTRY["comment"].title,
    ]
    assert [sheet.cell(first_data, i).value for i in range(3)] == [
        "Согласование",
        "ВУЗ",
        "Текст",
    ]


def test_row_count_matches_rows_written(tmp_path):
    rows = [{"university": f"ВУЗ {i}"} for i in range(7)]
    result = _gen(tmp_path, None, rows, generated_at=MOMENT)
    assert result.row_count == 7
    _book = xlrd.open_workbook(str(result.path))
    assert _book.sheet_by_name(REPORT_SHEET).nrows == DATA_START_ROW - 1 + 7


# ------------------------------------------------------------- cell semantics


def test_missing_values_stay_empty_cells(tmp_path):
    """Never "N/A" / "null" / "-": an absent relation is a blank cell."""
    _result, book = _read(tmp_path, [{"university": "МГУ", "product": None}])
    sheet = book.sheet_by_name(REPORT_SHEET)
    row = DATA_START_ROW - 1
    assert sheet.cell(row, 0).value == "МГУ"
    assert sheet.cell(row, 2).value == ""


def test_dates_are_typed_date_cells_not_strings(tmp_path):
    _result, book = _read(
        tmp_path,
        [{"university": "МГУ", "license_signed": date(2026, 3, 15)}],
        columns=["university", "license_signed"],
    )
    cell = _cell(book, REPORT_SHEET, DATA_START_ROW - 1, 1)
    assert cell.ctype == xlrd.XL_CELL_DATE
    y, m, d, *_ = xlrd.xldate_as_tuple(cell.value, book.datemode)
    assert (y, m, d) == (2026, 3, 15)


def test_datetimes_keep_their_time_of_day(tmp_path):
    _result, book = _read(
        tmp_path,
        [
            {
                "university": "МГУ",
                "last_interaction": datetime(2026, 3, 15, 14, 30, tzinfo=timezone.utc),
            }
        ],
        columns=["university", "last_interaction"],
    )
    cell = _cell(book, REPORT_SHEET, DATA_START_ROW - 1, 1)
    assert cell.ctype == xlrd.XL_CELL_DATE
    y, m, d, hh, mm, _ = xlrd.xldate_as_tuple(cell.value, book.datemode)
    assert (y, m, d, hh, mm) == (2026, 3, 15, 14, 30)


def test_numbers_stay_numeric(tmp_path):
    _result, book = _read(
        tmp_path,
        [{"university": "МГУ", "workflow_progress": 60, "overdue_tasks": 0}],
        columns=["university", "workflow_progress", "overdue_tasks"],
    )
    sheet = book.sheet_by_name(REPORT_SHEET)
    row = DATA_START_ROW - 1
    assert sheet.cell(row, 1).ctype == xlrd.XL_CELL_NUMBER
    assert sheet.cell(row, 1).value == 60
    # 0 is a real value and must not be confused with a missing one.
    assert sheet.cell(row, 2).ctype == xlrd.XL_CELL_NUMBER
    assert sheet.cell(row, 2).value == 0


def test_cyrillic_survives_the_encoding(tmp_path):
    """BIFF8 is a byte format; UTF-8 handling must not mangle Cyrillic."""
    value = "МГУ имени Ломоносова — ИТ-направление «Программирование»"
    _result, book = _read(tmp_path, [{"university": value}])
    assert _cell(book, REPORT_SHEET, DATA_START_ROW - 1, 0).value == value


def test_formula_injection_is_escaped(tmp_path):
    _result, book = _read(tmp_path, [{"university": "=HYPERLINK(\"evil\")"}])
    value = _cell(book, REPORT_SHEET, DATA_START_ROW - 1, 0).value
    assert value.startswith("'=")
    assert value == "'=HYPERLINK(\"evil\")"


def test_negative_numbers_are_not_escaped_as_text(tmp_path):
    """A leading '-' is only dangerous in text; numbers must stay numeric."""
    _result, book = _read(
        tmp_path, [{"university": "МГУ", "workflow_progress": -5}],
        columns=["university", "workflow_progress"],
    )
    cell = _cell(book, REPORT_SHEET, DATA_START_ROW - 1, 1)
    assert cell.ctype == xlrd.XL_CELL_NUMBER
    assert cell.value == -5


# ------------------------------------------------------------- filters sheet


def test_filters_sheet_lists_every_frozen_filter_dimension(tmp_path):
    moment = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    filters = UnifiedFilter(
        date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)
    )
    out = tmp_path / "report.xls"
    generate_xls_report(FakeSession([]), filters, None, out, generated_at=moment)
    book = xlrd.open_workbook(str(out))
    sheet = book.sheet_by_name(FILTERS_SHEET)
    assert sheet.cell(0, 0).value == "Параметр"
    assert sheet.cell(0, 1).value == "Значение"
    listed = {sheet.cell(r, 0).value: sheet.cell(r, 1).value for r in range(1, sheet.nrows)}
    assert list(listed) == list(FILTER_FIELD_ORDER)
    assert listed["date_from"] == "2026-09-01"
    assert listed["date_to"] == "2026-09-30"
    assert listed["university_ids"] == ""


def test_period_line_reflects_the_filter(tmp_path):
    out = tmp_path / "report.xls"
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    generate_xls_report(FakeSession([]), filters, None, out, generated_at=MOMENT)
    book = xlrd.open_workbook(str(out))
    assert book.sheet_by_name(REPORT_SHEET).cell(1, 0).value == "Период: с 01.09.2026 по 30.09.2026"


# ----------------------------------------------------------------- validation


def test_unknown_column_rejected(tmp_path):
    from app.modules.analytics.columns import UnknownReportColumnError

    with pytest.raises(UnknownReportColumnError):
        _gen(tmp_path, ["university", "bogus"], [])


def test_empty_column_selection_rejected(tmp_path):
    from app.modules.analytics.columns import EmptyReportColumnsError

    with pytest.raises(EmptyReportColumnsError):
        _gen(tmp_path, [], [])


def test_biff8_column_limit_is_enforced_not_truncated(tmp_path, monkeypatch):
    """Too many columns must raise before anything is written."""
    from app.modules.analytics import xls as xls_module

    monkeypatch.setattr(xls_module, "XLS_MAX_COLUMNS", 3)
    out = tmp_path / "wide.xls"
    with pytest.raises(XlsCapacityError, match="at most 3 columns"):
        generate_xls_report(
            FakeSession([]), UnifiedFilter(), list(DEFAULT_COLUMNS), out, generated_at=MOMENT
        )
    assert not out.exists()
    assert not (tmp_path / "wide.xls.part").exists()


def test_row_overflow_fails_the_job_instead_of_truncating(tmp_path, monkeypatch):
    """Exceeding the BIFF8 row cap must raise, never write a partial file."""
    from app.modules.analytics import xls as xls_module

    monkeypatch.setattr(xls_module, "XLS_MAX_ROWS", 12)
    out = tmp_path / "overflow.xls"
    rows = [{"university": f"ВУЗ {i}"} for i in range(20)]
    with pytest.raises(XlsCapacityError, match="data rows"):
        generate_xls_report(FakeSession(rows), UnifiedFilter(), None, out, generated_at=MOMENT)
    assert not out.exists(), "no partial file may be left behind"
    assert not (tmp_path / "overflow.xls.part").exists()


def test_failed_generation_cleans_up_the_part_file(tmp_path, monkeypatch):
    """A crash mid-generation must not leave a .part artifact behind."""
    from app.modules.analytics import xls as xls_module

    def _explode(*args, **kwargs):
        raise RuntimeError("db went away")

    monkeypatch.setattr(xls_module.ReportDatasetService, "iterate_rows", _explode)
    out = tmp_path / "boom.xls"
    with pytest.raises(RuntimeError, match="db went away"):
        generate_xls_report(FakeSession([]), UnifiedFilter(), None, out, generated_at=MOMENT)
    assert not out.exists()
    assert not (tmp_path / "boom.xls.part").exists()
