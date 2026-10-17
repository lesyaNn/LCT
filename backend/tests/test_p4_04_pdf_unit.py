"""P4-04-01/02 unit tests: PDF generator over a stubbed dataset (no database).

Covers: metadata/title/period/filters/timestamp/KPI, selected/default
column order from ``COLUMN_REGISTRY``, DD.MM.YYYY dates, nulls, literal
text, centralized DejaVu font registration, embedded Cyrillic (proven by
decoding the embedded ToUnicode CMaps with stdlib only — no PDF text
extraction dependency), multi-page tables, empty datasets (charts
skipped), chart builders, temp-file atomicity and failure cleanup.
"""

from __future__ import annotations

import base64
import re
import zlib
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

reportlab = pytest.importorskip("reportlab", reason="reportlab not installed")
from reportlab.pdfbase import pdfmetrics

from app.modules.analytics.columns import COLUMN_REGISTRY, DEFAULT_COLUMNS
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.pdf import (
    FONT_BOLD,
    FONT_REGULAR,
    NO_CHART_DATA_TEXT,
    PDFFontUnavailableError,
    PDF_PAGE_SIZE_ORIENTATION,
    ReportKpi,
    ensure_pdf_fonts,
    find_dejavu_font_files,
    format_cell_value,
    generate_pdf_report,
)
from app.modules.analytics.xlsx import REPORT_TITLE

SUBSET_5 = ["university", "product", "workflow_status", "responsible", "workflow_progress"]


def _rows_5() -> list[dict]:
    uid = uuid4()
    beta = uuid4()
    return [
        {
            "university": "МГУ им. Ломоносова",
            "product": "ПО Защита",
            "workflow_status": "Этап 2",
            "responsible": "Иван Петров",
            "workflow_progress": 85,
            "_university_id": uid,
        },
        {
            "university": "МГУ им. Ломоносова",
            "product": None,
            "workflow_status": None,
            "responsible": None,
            "workflow_progress": None,
            "_university_id": uid,
        },
        {
            "university": "ВУЗ Бета",
            "product": "ПО Второе",
            "workflow_status": "Этап 1",
            "responsible": "Пётр Второй",
            "workflow_progress": 55,
            "_university_id": beta,
        },
    ]


class _Mappings:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Scalars:
    def __init__(self, values: list):
        self._values = values

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, mappings_rows=None, scalars_values=None, pairs=None):
        self._mappings_rows = mappings_rows or []
        self._scalars_values = scalars_values or []
        self._pairs = pairs if pairs is not None else []

    def mappings(self):
        return _Mappings(self._mappings_rows)

    def scalars(self):
        return _Scalars(self._scalars_values)

    def all(self):
        return list(self._pairs)


class FakeSession:
    """Routes by statement shape (same shapes as production).

    ``map_columns`` opts in to serving the batched university-grain queries
    that compute ``workflow_progress`` / ``overdue_tasks``: without it those
    columns come back NULL, exactly like a university with no workflow rows.
    """

    def __init__(
        self,
        rows: list[dict],
        names: dict | None = None,
        map_columns: tuple[str, ...] = (),
    ):
        self._rows = rows
        self._names = names or {}
        self._map_columns = set(map_columns)

    def _owner_uids(self) -> list:
        uids = []
        for row in self._rows:
            uid = row.get("_university_id")
            if uid is not None and uid not in uids:
                uids.append(uid)
        return uids

    def _stage_rows(self) -> list:
        """(university_id, stage_status) rows reproducing the target percent.

        The dataset computes ``completed / non_skipped * 100``. Emitting
        exactly 100 eligible stages per university, ``value`` of them
        completed, reproduces the requested percentage to the integer.
        """
        rows = []
        for row in self._rows:
            uid = row.get("_university_id")
            value = row.get("workflow_progress")
            if uid is None or value is None:
                continue
            done = int(value)
            rows += [(uid, "completed")] * done
            rows += [(uid, "pending")] * (100 - done)
        return rows

    def execute(self, stmt, execution_options=None):
        try:
            compiled = str(stmt).lower()
        except Exception:
            compiled = ""
        if "university_responsibles" in compiled:
            pairs = []
            for row in self._rows:
                uid = row.get("_university_id")
                name = row.get("responsible")
                if uid is not None and name and (uid, name) not in pairs:
                    pairs.append((uid, name))
            return _Result(pairs=pairs)
        if "instance_stages" in compiled and "workflow_progress" in self._map_columns:
            return _Result(pairs=self._stage_rows())
        if "workflow_tasks" in compiled and "overdue_tasks" in self._map_columns:
            # (university_id, count) rows for the overdue-task aggregate.
            return _Result(pairs=[(r["_university_id"], r["overdue_tasks"])
                                  for r in self._rows
                                  if r.get("_university_id") is not None
                                  and r.get("overdue_tasks") is not None])
        if "workflow_instances" in compiled and "instance_stages" not in compiled:
            # The active-instance lookup, shared by both map columns.
            if self._map_columns & {"workflow_progress", "overdue_tasks"}:
                return _Result(
                    pairs=[(r["_university_id"], f"i-{i}")
                           for i, r in enumerate(self._rows)
                           if r.get("_university_id") is not None]
                )
            return _Result(scalars_values=self._owner_uids())
        if "licenses" in compiled or "_university_id" in compiled:
            return _Result(mappings_rows=self._rows)
        return _Result(scalars_values=self._owner_uids())


def _gen(tmp_path: Path, columns, rows: list[dict], **kw):
    out = tmp_path / "report.pdf"
    result = generate_pdf_report(FakeSession(rows), UnifiedFilter(), columns, out, **kw)
    assert result.path == out
    return result


def test_selected_grouping_appears_in_pdf(tmp_path, monkeypatch):
    from app.modules.analytics.stats import ReportStatsService, StatBucket, StatSlice

    if find_dejavu_font_files()[0] is None:
        pytest.skip("PDF font is not installed on this host")

    summary = StatSlice("by_university", "Распределение строк по вузам", "rows", 1, (StatBucket("МГУ", 1),))
    monkeypatch.setattr(ReportStatsService, "group_slice", staticmethod(lambda *args, **kwargs: summary))
    result = _gen(tmp_path, ["university"], [{"university": "МГУ"}], group_by="university")
    text = extract_pdf_text(result.path.read_bytes())
    assert "Распределение строк по вузам" in text
    assert "МГУ" in text


# ------------------------------------------------------- PDF text extraction
# (stdlib only: decode embedded ToUnicode CMaps, then content Tj strings —
# proves Cyrillic is really embedded/renderable, not just "file generated").


def _decode_streams(data: bytes) -> list[bytes]:
    out: list[bytes] = []
    obj_body = r"(?:(?!endobj).)*?"
    pattern = re.compile(
        rb"(\d+ \d+ obj)\s*<<"
        + obj_body.encode()
        + rb"/Length (\d+)"
        + obj_body.encode()
        + rb"stream\r?\n",
        re.S,
    )
    for match in pattern.finditer(data):
        raw = data[match.end() : match.end() + int(match.group(2))].strip()
        for attempt in (
            lambda: zlib.decompress(base64.a85decode(raw, adobe=True)),
            lambda: zlib.decompress(raw),
        ):
            try:
                out.append(attempt())
                break
            except Exception:
                continue
    return out


def _font_resources(data: bytes) -> dict[str, str]:
    """Map content-stream font keys (``F2+0``) to base names (``DejaVuSans``)."""
    targets: dict[str, str] = {}
    for key, num in re.findall(rb"/(F\d+(?:\+\d+)?) (\d+) 0 R", data):
        targets[key.decode("ascii")] = num.decode("ascii")
    resolved: dict[str, str] = {}
    for key, num in targets.items():
        match = re.search(
            rb"%s 0 obj.*?/BaseFont\s*/(?:[A-Z0-9]+\+)?([A-Za-z\-]+)" % num.encode(),
            data,
            re.S,
        )
        if match:
            resolved[key] = match.group(1).decode("ascii")
    return resolved


def _cmap_per_font(data: bytes) -> dict[str, dict[int, str]]:
    cmaps: dict[str, dict[int, str]] = {}
    for stream in _decode_streams(data):
        if b"beginbfchar" not in stream:
            continue
        reg = re.search(rb"Registry \([A-Z]*\+?([^)]+)\)", stream)
        if not reg:
            continue
        font = reg.group(1).decode("ascii")
        mapping = {
            int(src, 16): chr(int(dst, 16))
            for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", stream)
        }
        if mapping:
            cmaps[font] = mapping
    return cmaps


def _pdf_string_bytes(raw: bytes) -> bytes:
    """Decode one PDF literal string body (octal + simple escapes)."""
    out = bytearray()
    i = 0
    simple = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < len(raw):
        byte = raw[i]
        if byte == 0x5C:  # backslash
            nxt = raw[i + 1 : i + 2]
            if nxt and nxt[0] in b"01234567":
                octal = nxt
                i += 1
                for _ in range(2):
                    if raw[i + 1 : i + 2] and raw[i + 1] in b"01234567":
                        octal += bytes([raw[i + 1]])
                        i += 1
                out.append(int(octal, 8) & 0xFF)
                i += 1
                continue
            if nxt and nxt[0] in simple:
                out.append(simple[nxt[0]])
            elif nxt:
                out.append(nxt[0])
            i += 2
            continue
        out.append(byte)
        i += 1
    return bytes(out)


def extract_pdf_text(data: bytes) -> str:
    """Best-effort visible-text extraction via embedded ToUnicode CMaps."""
    cmaps = _cmap_per_font(data)
    resources = _font_resources(data)
    texts: list[str] = []
    for stream in _decode_streams(data):
        if b"BT" not in stream:
            continue
        current: str | None = None
        for block in re.findall(rb"BT(.*?)ET", stream, re.S):
            font_match = re.search(rb"/(F\S+) \d+(?:\.\d+)? Tf", block)
            if font_match:
                current = resources.get(font_match.group(1).decode("ascii"))
            if current is None:
                continue
            cmap = cmaps.get(current, {})
            if not cmap:
                continue
            parts: list[str] = []
            for literal in re.findall(rb"\((?:\\.|[^\\()])*\) Tj", block):
                parts.append(_pdf_string_bytes(literal[1:-4]))
            for array in re.findall(rb"\[(.*?)\] TJ", block, re.S):
                for literal in re.findall(rb"\((?:\\.|[^\\()])*\)", array):
                    parts.append(_pdf_string_bytes(literal[1:-1]))
            texts.append("".join(cmap.get(byte, "") for part in parts for byte in part))
    return "".join(texts)


def _nospace(text: str) -> str:
    """Compare ignoring spaces: table header wrap splits titles across lines
    (the wrap space itself is consumed by reportlab), so ``'Наименование' +
    'ВУЗа'`` must still match ``'Наименование ВУЗа'``."""
    return text.replace(" ", "")


def _info_string(data: bytes, key: bytes) -> str:
    """Decode a PDF Info-dict string (octal escapes + UTF-16BE BOM aware)."""
    match = re.search(rb"/" + key + rb" \((?:\\.|[^\\()])*\)", data)
    assert match, f"/{key.decode()} missing in PDF metadata"
    raw = _pdf_string_bytes(match.group(0).split(b"(", 1)[1][:-1])
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be")
    return raw.decode("latin-1")


def _fonts_used_for_text(data: bytes) -> dict[str, int]:
    """Map font name -> count of Tj strings drawn with it (all streams)."""
    resources = _font_resources(data)
    used: dict[str, int] = {}
    for stream in _decode_streams(data):
        if b"BT" not in stream:
            continue
        current: str | None = None
        for block in re.findall(rb"BT(.*?)ET", stream, re.S):
            font_match = re.search(rb"/(F\S+) \d+(?:\.\d+)? Tf", block)
            if font_match:
                current = resources.get(
                    font_match.group(1).decode("ascii"), font_match.group(1).decode("ascii")
                )
            count = len(re.findall(rb"\) Tj", block)) + len(re.findall(rb"\] TJ", block))
            if count and current:
                used[current] = used.get(current, 0) + count
    return used


# ------------------------------------------------------- cell formatting / KPI


def test_format_cell_value_null_dates_numbers_literal():
    assert format_cell_value("comment", None) == ""
    assert format_cell_value("license_signed", date(2026, 2, 1)) == "01.02.2026"
    assert format_cell_value("license_signed", datetime(2026, 2, 1, 10, 30)) == "01.02.2026"
    assert format_cell_value("workflow_progress", 85) == "85"
    assert format_cell_value("workflow_progress", None) == ""
    # PDF executes no formulas: user text stays literal (no apostrophe).
    assert format_cell_value("comment", "=HYPERLINK(1)") == "=HYPERLINK(1)"
    assert format_cell_value("university", "МГУ им. Ломоносова") == "МГУ им. Ломоносова"


def test_kpi_accumulates_from_the_streamed_rows():
    """KPI comes from the same streamed rows as the table (no second query)."""
    kpi = ReportKpi()
    for row in (
        {"university": "A", "workflow_progress": 90, "overdue_tasks": 1},
        {"university": "A", "workflow_progress": 70, "overdue_tasks": 0},
        {"university": "B", "workflow_progress": None, "overdue_tasks": 2},
    ):
        kpi.add_row(row)
    assert kpi.row_count == 3
    assert kpi.university_count == 2
    assert kpi.overdue_total == 3
    assert kpi.avg_workflow_progress == 80.0
    assert kpi.progress_rows == 2


def test_kpi_without_progress_is_none_not_zero():
    """"Нет данных" must stay distinguishable from "нулевой прогресс"."""
    kpi = ReportKpi()
    kpi.add_row({"university": "A", "workflow_progress": None})
    assert kpi.avg_workflow_progress is None
    assert kpi.progress_rows == 0


def test_kpi_counts_zero_progress_distinctly_from_missing():
    zero = ReportKpi()
    zero.add_row({"university": "A", "workflow_progress": 0})
    assert zero.avg_workflow_progress == 0.0
    assert zero.progress_rows == 1


def test_kpi_university_count_falls_back_when_column_absent():
    """Without the university column the rows carry no name: use the scope."""
    kpi = ReportKpi()
    kpi.add_row({"workflow_progress": 50})
    assert kpi.university_count == 0
    assert kpi.resolve_university_count(7) == 7
    kpi.add_row({"university": "A", "workflow_progress": 50})
    assert kpi.resolve_university_count(7) == 1


# ------------------------------------------------------- fonts (P4-04-02)


def test_find_dejavu_font_files_exist():
    regular, bold = find_dejavu_font_files()
    assert regular is not None and regular.is_file(), (
        "DejaVuSans.ttf must be discoverable (install fonts-dejavu-core "
        "or expose REPORT_PDF_FONT_DIR)"
    )
    assert bold is not None and bold.is_file()


def test_ensure_pdf_fonts_registers_once_centrally():
    paths = ensure_pdf_fonts()
    names = set(pdfmetrics.getRegisteredFontNames())
    assert FONT_REGULAR in names
    assert FONT_BOLD in names
    assert paths["regular"].endswith("DejaVuSans.ttf")
    # Idempotent: second call reuses registration (no per-cell re-register).
    assert ensure_pdf_fonts() == paths


def test_missing_font_raises_actionable_error(monkeypatch):
    import app.modules.analytics.pdf as pdfmod

    monkeypatch.setattr(pdfmod, "find_dejavu_font_files", lambda: (None, None))
    from reportlab.pdfbase import pdfmetrics as _pm

    monkeypatch.setattr(_pm, "getRegisteredFontNames", lambda: [])
    with pytest.raises(PDFFontUnavailableError, match="fonts-dejavu-core"):
        ensure_pdf_fonts()


def test_page_geometry_is_landscape_a4():
    assert PDF_PAGE_SIZE_ORIENTATION == "landscape A4"


# ------------------------------------------------------- document structure


def test_pdf_header_and_metadata(tmp_path):
    result = _gen(tmp_path, SUBSET_5, _rows_5())
    data = result.path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 0
    assert result.row_count == 3
    assert result.columns == SUBSET_5
    assert result.generated_at.tzinfo is not None
    # PDF metadata: title/author embedded, no secrets.
    assert _info_string(data, b"Title") == REPORT_TITLE
    assert _info_string(data, b"Author") == "RTK CRM Analytics"
    assert b"token" not in data.lower()


def test_pdf_default_columns_are_the_five_tz_columns(tmp_path):
    result = _gen(tmp_path, None, [])
    assert result.columns == list(DEFAULT_COLUMNS)
    assert len(result.columns) == 5
    text = extract_pdf_text(result.path.read_bytes())
    compact = _nospace(text)
    for key in DEFAULT_COLUMNS:
        assert _nospace(COLUMN_REGISTRY[key].title) in compact, key


def test_pdf_subset_order_and_content(tmp_path):
    result = _gen(tmp_path, SUBSET_5, _rows_5())
    text = extract_pdf_text(result.path.read_bytes())
    assert REPORT_TITLE in text
    assert "МГУ им. Ломоносова" in text
    assert "ВУЗ Бета" in text
    # Request order preserved in the header row (never sorted): chained
    # search (the KPI block may mention a title word earlier in the text;
    # wrapped titles are compared space-insensitively, see _nospace).
    compact = _nospace(text)
    pos = 0
    for key in SUBSET_5:
        pos = compact.index(_nospace(COLUMN_REGISTRY[key].title), pos) + 1
    assert pos > 0


def test_pdf_metadata_rows_period_filters_timestamp_kpi(tmp_path):
    filters = UnifiedFilter(date_from=date(2026, 1, 5), date_to=date(2026, 3, 7))
    out = tmp_path / "meta.pdf"
    generate_pdf_report(FakeSession(_rows_5()), filters, SUBSET_5, out)
    text = extract_pdf_text(out.read_bytes())
    assert REPORT_TITLE in text
    assert "05.01.2026" in text and "07.03.2026" in text
    assert "Сформирован" in text
    assert "Ключевые показатели" in text
    assert "Количество ВУЗов: 2" in text
    assert "Количество строк" in text
    assert "Средний прогресс workflow" in text


def test_pdf_neutral_period_when_unset(tmp_path):
    result = _gen(tmp_path, SUBSET_5, _rows_5())
    assert "не задан" in extract_pdf_text(result.path.read_bytes())


def test_pdf_dates_formatted_nulls_empty(tmp_path):
    rows = [
        {
            "university": "ВУЗ",
            "license_signed": date(2026, 2, 1),
            "license_expires": None,
            "comment": None,
            "_university_id": uuid4(),
        }
    ]
    out = tmp_path / "dates.pdf"
    generate_pdf_report(
        FakeSession(rows),
        UnifiedFilter(),
        ["university", "license_signed", "license_expires", "comment"],
        out,
    )
    text = extract_pdf_text(out.read_bytes())
    assert "01.02.2026" in text
    assert "None" not in text
    assert "N/A" not in text


def test_pdf_formula_probe_stays_literal(tmp_path):
    rows = [{"university": "=HYPERLINK(1)", "comment": "+CMD", "_university_id": uuid4()}]
    out = tmp_path / "lit.pdf"
    generate_pdf_report(FakeSession(rows), UnifiedFilter(), ["university", "comment"], out)
    text = extract_pdf_text(out.read_bytes())
    assert "=HYPERLINK(1)" in text
    assert "'=HYPERLINK" not in text  # no XLSX apostrophe escaping in PDF


def test_pdf_generated_timestamp_timezone_aware(tmp_path):
    naive = datetime(2026, 9, 20, 10, 30, 0)
    result = _gen(tmp_path, ["university"], _rows_5()[:1], generated_at=naive)
    assert result.generated_at.tzinfo is not None


# ------------------------------------------------------- Cyrillic proof


def test_pdf_cyrillic_embedded_via_tounicode_cmap(tmp_path):
    result = _gen(tmp_path, SUBSET_5, _rows_5())
    data = result.path.read_bytes()
    # Font really registered + embedded (not just "file generated").
    assert FONT_REGULAR.encode() in data or b"DejaVuSans" in data
    assert b"FontFile2" in data  # TTF subset embedded
    text = extract_pdf_text(data)
    assert "МГУ им. Ломоносова" in text
    assert "Аналитический" in text
    # Chart labels are Cyrillic too. The progress pie itself has no data here
    # (``workflow_progress`` is a batched university-map column, and the stub
    # session serves NULL for it), so the honest expectation is the
    # "no data" placeholder; the drawn pie is covered by
    # test_progress_distribution_* / test_progress_chart_* below.
    assert "Нет данных для построения графика" in text


def test_pdf_renders_the_progress_pie_when_progress_exists(tmp_path):
    """With real progress values the pie is drawn, not replaced by a notice."""
    rows = [
        {
            "university": "МГУ",
            "workflow_status": "Этап 1",
            "workflow_progress": 90,
            "overdue_tasks": 0,
            "_university_id": uuid4(),
        },
        {
            "university": "ВУЗ Бета",
            "workflow_status": "Этап 1",
            "workflow_progress": 10,
            "overdue_tasks": 3,
            "_university_id": uuid4(),
        },
    ]
    # The progress column is computed by the batched university-map query, so
    # the stub session is told to serve the per-column maps for it.
    session = FakeSession(rows, map_columns=("workflow_progress", "overdue_tasks"))
    out = tmp_path / "pie.pdf"
    generate_pdf_report(
        session, UnifiedFilter(), ["university", "workflow_progress", "overdue_tasks"], out
    )
    text = extract_pdf_text(out.read_bytes())
    # The progress pie is drawn from real values...
    assert "прогрессу workflow" in text
    assert "Зелёный" in text and "Красный" in text
    # ...and it is NOT replaced by the no-data notice (the bar charts for
    # unselected columns legitimately do show that notice).
    assert "нет измеренного прогресса" not in text
    assert "Распределение строк по ИТ-направлениям: Нет данных" in text
    # The KPI average must come from the same rows the table shows.
    assert "Средний прогресс workflow, %: 50.0" in text
    assert "Просроченные задачи: 3" in text


def test_pdf_all_visible_text_uses_dejavu_never_helvetica(tmp_path):
    result = _gen(tmp_path, None, _rows_5())
    used = _fonts_used_for_text(result.path.read_bytes())
    assert used, "expected visible text in the document"
    assert set(used) <= {"DejaVuSans", "DejaVuSans-Bold"}, used


# ------------------------------------------------------- pagination / empty


def test_pdf_multi_page_table(tmp_path):
    uid = uuid4()
    rows = [
        {
            "university": f"ВУЗ {i:04d}",
            "product": "ПО",
            "workflow_status": "Этап 1",
            "responsible": "Ответственный",
            "workflow_progress": 70,
            "_university_id": uuid4() if i % 7 else uid,
        }
        for i in range(250)
    ]
    result = _gen(tmp_path, SUBSET_5, rows)
    assert result.row_count == 250
    data = result.path.read_bytes()
    counts = [int(n) for n in re.findall(rb"/Count (\d+)", data)]
    assert counts and max(counts) >= 2, "250 rows must paginate"
    text = extract_pdf_text(data)
    assert "ВУЗ 0001" in text and "ВУЗ 0249" in text  # no clipped rows


def test_pdf_empty_dataset_still_valid_with_chart_placeholder(tmp_path):
    result = _gen(tmp_path, SUBSET_5, [])
    assert result.row_count == 0
    data = result.path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 0
    counts = [int(n) for n in re.findall(rb"/Count (\d+)", data)]
    assert counts and max(counts) >= 1
    text = extract_pdf_text(data)
    assert REPORT_TITLE in text
    assert NO_CHART_DATA_TEXT in text


def test_pdf_empty_progress_and_workflow_skip_charts(tmp_path):
    rows = [
        {
            "university": "ВУЗ Без Данных",
            "product": None,
            "workflow_status": None,
            "responsible": None,
            "workflow_progress": None,
            "_university_id": uuid4(),
        }
    ]
    result = _gen(tmp_path, SUBSET_5, rows)
    text = extract_pdf_text(result.path.read_bytes())
    assert NO_CHART_DATA_TEXT in text


# ------------------------------------------------------- charts


def test_progress_distribution_uses_canonical_thresholds():
    from app.modules.analytics.pdf import _progress_distribution

    rows = [
        {"university": "A", "workflow_progress": 85},  # green boundary
        {"university": "B", "workflow_progress": 84},  # yellow boundary
        {"university": "C", "workflow_progress": 60},  # yellow boundary
        {"university": "D", "workflow_progress": 59},  # red boundary
        {"university": "E", "workflow_progress": None},
    ]
    counts, grain = _progress_distribution(rows, ["university", "workflow_progress"])
    assert counts == {"green": 1, "yellow": 2, "red": 1}
    assert "ВУЗ" in grain


def test_progress_distribution_row_grain_without_university_column():
    from app.modules.analytics.pdf import _progress_distribution

    rows = [{"workflow_progress": 90}, {"workflow_progress": 90}, {"workflow_progress": None}]
    counts, grain = _progress_distribution(rows, ["workflow_progress"])
    assert counts == {"green": 2, "yellow": 0, "red": 0}
    assert "строк" in grain


def test_workflow_distribution_bounded_and_ordered():
    from app.modules.analytics.pdf import _workflow_distribution

    rows = [{"workflow_status": s} for s in ["B", "A", "B", None, "A", "B", "C"]]
    assert _workflow_distribution(rows, ["workflow_status", "university"]) == [
        ("B", 3),
        ("A", 2),
        ("C", 1),
    ]
    assert _workflow_distribution(rows, ["university"]) == []


def test_chart_builders_return_dejavu_drawings():
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing

    from app.modules.analytics.pdf import _progress_chart, _workflow_chart

    drawing = _progress_chart({"green": 2, "yellow": 1, "red": 0}, "по ВУЗам")
    assert isinstance(drawing, Drawing)
    pies = [el for el in drawing.contents if isinstance(el, Pie)]
    assert len(pies) == 1
    assert pies[0].slices.fontName == FONT_REGULAR
    assert any("Зелёный" in label for label in pies[0].labels)

    bars = _workflow_chart([("Этап 2", 3), ("Этап 1", 1)])
    assert isinstance(bars, Drawing)
    charts = [el for el in bars.contents if isinstance(el, HorizontalBarChart)]
    assert len(charts) == 1
    assert charts[0].categoryAxis.labels.fontName == FONT_REGULAR
    assert list(charts[0].categoryAxis.categoryNames) == ["Этап 2", "Этап 1"]


# ------------------------------------------------------- result / temp / errors


def test_pdf_result_metadata(tmp_path):
    result = _gen(tmp_path, SUBSET_5, _rows_5())
    assert result.path.exists()
    assert result.size_bytes == result.path.stat().st_size > 0
    assert result.generated_at.tzinfo is not None


def test_no_part_file_left_behind(tmp_path):
    _gen(tmp_path, SUBSET_5, _rows_5())
    assert list(tmp_path.glob("*.part")) == []


def test_failure_removes_temp_and_raises(tmp_path):
    import reportlab.platypus

    out = tmp_path / "fail.pdf"
    with pytest.raises(RuntimeError, match="build gone"):
        with _patched_build(reportlab.platypus, "build gone"):
            generate_pdf_report(FakeSession(_rows_5()), UnifiedFilter(), SUBSET_5, out)
    assert not out.exists()
    assert list(tmp_path.glob("*.part")) == []


class _patched_build:
    def __init__(self, module, message: str):
        self._module = module
        self._message = message
        self._real = module.SimpleDocTemplate.build

    def __enter__(self):
        message = self._message

        def _boom(self_, *args, **kwargs):
            raise RuntimeError(message)

        self._module.SimpleDocTemplate.build = _boom
        return self

    def __exit__(self, *exc):
        self._module.SimpleDocTemplate.build = self._real
        return False


def test_unknown_and_empty_columns_raise(tmp_path):
    from app.modules.analytics.columns import (
        EmptyReportColumnsError,
        UnknownReportColumnError,
    )

    with pytest.raises(UnknownReportColumnError):
        generate_pdf_report(
            FakeSession([]), UnifiedFilter(), ["university", "bogus"], tmp_path / "a.pdf"
        )
    with pytest.raises(EmptyReportColumnsError):
        generate_pdf_report(FakeSession([]), UnifiedFilter(), [], tmp_path / "b.pdf")
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.glob("*.pdf")) == []
