"""P4-04-01/02 PDF report generator (production exporter, no SQL inside).

Data comes ONLY from :class:`ReportDatasetService` (same filters, same row
grain, same selected columns, same workflow values as the dataset).
Column titles come ONLY from ``COLUMN_REGISTRY`` — there is no second
``PDF_COLUMN_MAPPING``. ``UnifiedFilter`` semantics stay frozen (date bounds
on the interaction period — meetings / interaction notes, AND between
dimensions, OR/IN within).

Presentation helpers (title text, period text, human-readable filter
summary, result metadata, width ratios) are reused from
:mod:`app.modules.analytics.xlsx` so XLSX/PDF metadata can never drift;
only the rendering backend differs (reportlab platypus, landscape A4).

Layout (frozen)::

    1. title (``Аналитический отчёт по взаимодействию с ВУЗами``)
    2. period (same text as XLSX, neutral ``Период: не задан`` when unset)
    3. applied filters (human-readable summary, UUID names batched, no N+1)
    4. ``Сформирован: <tz-aware timestamp>``
    5. KPI block (same filtered dataset: universities / rows / avg score / overdue)
    6. table (selected columns in ``ReportRequest.columns`` order, titles
       from ``COLUMN_REGISTRY``, header repeated on every page)
    7. charts (score pie with frozen 85/60 thresholds + distributions by
       workflow status / direction / product / responsible when those columns
       are selected, reportlab native drawings — no matplotlib runtime
       dependency; only real dataset values, never mocks)

Cyrillic (P4-04-02): every string is rendered with ``DejaVuSans`` /
``DejaVuSans-Bold`` registered ONCE via :func:`ensure_pdf_fonts`
(never per cell/row). Font files are discovered at runtime (Debian
``fonts-dejavu-core`` path, ``REPORT_PDF_FONT_DIR`` override, matplotlib
bundle as a best-effort dev fallback) — no font binary lives in the repo
and no font file is served to users. Without a usable font the generator
raises :class:`PDFFontUnavailableError` instead of producing mojibake
with Helvetica.

Charts render only real dataset values (no mocks, no invented learners/flows).
Empty datasets still produce a valid PDF: chart sections render
``Нет данных для построения графика``.

PDF metadata (title/author) is set; no secrets or tokens are embedded.

Output is written to ``<final>.part`` first and atomically replaced to
the final ``.pdf`` only after a successful build; on failure the temp
file is removed and no partial file is left behind.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from sqlalchemy.orm import Session

from app.modules.analytics import xlsx as _xlsx
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.stats import ReportStatsService

__all__ = [
    "FONT_BOLD",
    "FONT_REGULAR",
    "NO_CHART_DATA_TEXT",
    "PDF_PAGE_SIZE_ORIENTATION",
    "PDFFontUnavailableError",
    "ReportKpi",
    "ensure_pdf_fonts",
    "find_dejavu_font_files",
    "format_cell_value",
    "generate_pdf_report",
]

#: Centralized reportlab font names (registered once, used everywhere).
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

#: Deterministic page geometry (single layout for any column count).
PDF_PAGE_SIZE_ORIENTATION = "landscape A4"

#: Placeholder rendered instead of a chart when there is nothing to plot.
NO_CHART_DATA_TEXT = "Нет данных для построения графика"

#: Max distinct workflow statuses drawn on chart 2 (bounded drawing).
_MAX_WORKFLOW_SLICES = 10


class PDFFontUnavailableError(RuntimeError):
    """No usable DejaVu Sans font found at runtime (Cyrillic unsafe)."""


# ---------------------------------------------------------------------------
# Font discovery + centralized registration (P4-04-02)
# ---------------------------------------------------------------------------


def find_dejavu_font_files() -> tuple[Path | None, Path | None]:
    """Locate DejaVuSans regular/bold TTFs without shipping binaries.

    Search order: ``REPORT_PDF_FONT_DIR`` override, Debian
    ``fonts-dejavu-core`` paths, generic ``/usr/share/fonts`` tree walk,
    matplotlib-bundled copy (dev fallback), Windows fonts dir.
    Returns ``(regular, bold)`` paths (either may be ``None``).
    """
    candidates: list[Path] = []
    override = os.getenv("REPORT_PDF_FONT_DIR")
    if override:
        base = Path(override)
        candidates += [base / "DejaVuSans.ttf", base / "DejaVuSans-Bold.ttf"]
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for root in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts")):
        if root.is_dir():
            candidates += sorted(root.rglob("DejaVuSans.ttf"))
            candidates += sorted(root.rglob("DejaVuSans-Bold.ttf"))
    try:  # best-effort dev fallback: matplotlib ships DejaVu Sans
        import matplotlib  # type: ignore[import-not-found]

        mpl_dir = Path(matplotlib.__file__).resolve().parent / "mpl-data" / "fonts" / "ttf"
        candidates += [mpl_dir / "DejaVuSans.ttf", mpl_dir / "DejaVuSans-Bold.ttf"]
    except Exception:  # pragma: no cover - optional dependency absent
        pass
    windir = os.getenv("WINDIR") or r"C:\Windows"
    candidates += [
        Path(windir) / "Fonts" / "DejaVuSans.ttf",
        Path(windir) / "Fonts" / "DejaVuSans-Bold.ttf",
    ]
    regular = next((p for p in candidates if p.name == "DejaVuSans.ttf" and p.is_file()), None)
    bold = next((p for p in candidates if p.name == "DejaVuSans-Bold.ttf" and p.is_file()), None)
    return regular, bold


def ensure_pdf_fonts() -> dict[str, str]:
    """Register ``DejaVuSans`` / ``DejaVuSans-Bold`` exactly once.

    Idempotent: repeated calls reuse the registered fonts. Returns the
    ``{"regular": ..., "bold": ...}`` source paths (single source of
    truth for tests and the Docker runtime check).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    registered = set(pdfmetrics.getRegisteredFontNames())
    if FONT_REGULAR in registered and FONT_BOLD in registered:
        return _registered_font_paths()
    regular, bold = find_dejavu_font_files()
    if regular is None:
        raise PDFFontUnavailableError(
            "DejaVuSans.ttf not found: install the 'fonts-dejavu-core' OS package "
            "(Debian slim images) or set REPORT_PDF_FONT_DIR to a directory "
            "containing DejaVuSans.ttf / DejaVuSans-Bold.ttf"
        )
    if FONT_REGULAR not in registered:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
    if bold is not None and FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    elif bold is None and FONT_BOLD not in registered:  # pragma: no cover
        # Bold file missing (regular covers Cyrillic too): alias bold to
        # regular so platypus never falls back to Helvetica mid-document.
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(regular)))
    return _registered_font_paths()


def _registered_font_paths() -> dict[str, str]:
    regular, bold = find_dejavu_font_files()
    return {"regular": str(regular) if regular else "", "bold": str(bold) if bold else ""}


# ---------------------------------------------------------------------------
# Presentation (titles from COLUMN_REGISTRY only; literal text, no escaping)
# ---------------------------------------------------------------------------


def format_cell_value(key: str, value: Any) -> str:
    """Render one dataset value as PDF cell text.

    * ``None`` -> ``""`` (empty cell, never ``None``/``null``/``N/A``/``-``);
    * ``date``/``datetime`` -> ``DD.MM.YYYY`` (semantics untouched);
    * integers stay numeric text (``overdue_tasks`` is 0 when none, never null);
    * user text is literal (PDF executes no formulas, so no XLSX-style
      apostrophe escaping is applied).
    """
    _ = key  # titles/order come from COLUMN_REGISTRY; values need no key branch
    if value is None:
        return ""
    if isinstance(value, datetime):
        return f"{value:%d.%m.%Y}"
    if isinstance(value, date):
        return f"{value:%d.%m.%Y}"
    if isinstance(value, bool):
        return str(int(value))
    return str(value)


@dataclass
class ReportKpi:
    """KPI counters accumulated while streaming the report dataset.

    The PDF renders one filtered dataset, so the KPI block must be derived
    from exactly those rows. Accumulating inline during the single streaming
    pass keeps that guarantee (no second query, no second dataset object)
    and removes the previous duplicate implementation, which was dead code
    that the generator never called and which disagreed with it on the
    average-score key.

    ``avg_workflow_progress`` is the mean of the non-null
    ``workflow_progress`` values (percent), or ``None`` when no row carries
    a progress value — never 0, so "нет данных" stays distinguishable from
    "нулевой прогресс".
    """

    row_count: int = 0
    overdue_total: int = 0
    progress_sum: float = 0.0
    progress_rows: int = 0
    _university_names: set[str] = field(default_factory=set, repr=False)

    def add_row(self, row: dict[str, Any]) -> None:
        self.row_count += 1
        name = row.get("university")
        if isinstance(name, str) and name:
            self._university_names.add(name)
        overdue = row.get("overdue_tasks")
        if isinstance(overdue, (int, float)) and not isinstance(overdue, bool):
            self.overdue_total += int(overdue)
        progress = row.get("workflow_progress")
        if isinstance(progress, (int, float)) and not isinstance(progress, bool):
            self.progress_sum += float(progress)
            self.progress_rows += 1

    @property
    def university_count(self) -> int:
        """Distinct universities seen in the streamed rows."""
        return len(self._university_names)

    def resolve_university_count(self, fallback: int) -> int:
        """Use the streamed names when available, else the scope-wide count.

        When the ``university`` column is not selected the rows carry no
        name, so the distinct set stays empty and the caller supplies the
        filtered university count instead of reporting a wrong 0.
        """
        return len(self._university_names) or fallback

    @property
    def avg_workflow_progress(self) -> float | None:
        """Mean progress in percent, or ``None`` when nothing was measured."""
        if not self.progress_rows:
            return None
        return round(self.progress_sum / self.progress_rows, 1)


def _scope_university_count(db: Any, filters: Any, user: Any) -> int:
    """Universities matching the filter, used when rows carry no name.

    Needed only when the ``university`` column is not selected, so the KPI
    still reports the real selection size instead of 0. A failure here must
    not break the export: the count degrades to 0 rather than 500.
    """
    from app.modules.analytics.analytics import AnalyticsService

    try:
        return len(AnalyticsService.filtered_university_ids(db, filters, user=user))
    except Exception:
        return 0


def _ensure_tz_aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


# ---------------------------------------------------------------------------
# Charts (reportlab native drawings; only real dataset values)
# ---------------------------------------------------------------------------

#: Progress thresholds for the pie (frozen: green >= 85, yellow >= 60).
_PROGRESS_GREEN_MIN = 85
_PROGRESS_YELLOW_MIN = 60


def _progress_value(row: dict[str, Any]) -> float | None:
    """Workflow progress of a row in percent (numeric 0..100, never bool).

    The only source is the ``workflow_progress`` column. Looking up a column
    that is not in the registry is pointless: the lookup would always fall
    through, while the label and the KPI would claim a metric the report
    never resolved.
    """
    value = row.get("workflow_progress")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _progress_status(progress: float) -> str:
    """green / yellow / red bucket for one progress value (frozen thresholds)."""
    if progress >= _PROGRESS_GREEN_MIN:
        return "green"
    if progress >= _PROGRESS_YELLOW_MIN:
        return "yellow"
    return "red"


def _progress_distribution(
    rows: list[dict[str, Any]], resolved: list[str]
) -> tuple[dict[str, int], str]:
    """Count green/yellow/red progress values (frozen 85/60 thresholds).

    Per-university grain when the ``university`` column is selected
    (first non-null progress per university name), else row grain. The
    returned grain label is rendered in the chart title (honest label).
    """
    per_university = "university" in resolved
    if per_university:
        seen: dict[str, float] = {}
        for row in rows:
            name = row.get("university")
            progress = _progress_value(row)
            if name is None or progress is None:
                continue
            key = str(name)
            if key not in seen:
                seen[key] = progress
        values = list(seen.values())
        grain = "по ВУЗам"
    else:
        values = [
            progress
            for row in rows
            if (progress := _progress_value(row)) is not None
        ]
        grain = "по строкам отчёта"
    counts = {"green": 0, "yellow": 0, "red": 0}
    for progress in values:
        counts[_progress_status(progress)] += 1
    return counts, grain


def _column_distribution(
    rows: list[dict[str, Any]], resolved: list[str], column: str
) -> list[tuple[str, int]]:
    """Count rows per non-null value of ``column`` (bounded, stable order).

    Returns [] when the column is not selected — the caller then renders
    the honest ``NO_CHART_DATA_TEXT`` placeholder instead of inventing data.
    """
    if column not in resolved:
        return []
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        label = str(value)
        if label:
            counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) > _MAX_WORKFLOW_SLICES:
        head = ordered[: _MAX_WORKFLOW_SLICES - 1]
        rest = sum(n for _, n in ordered[_MAX_WORKFLOW_SLICES - 1 :])
        head.append(("Прочее", rest))
        return head
    return ordered


def _workflow_distribution(
    rows: list[dict[str, Any]], resolved: list[str]
) -> list[tuple[str, int]]:
    """Count rows per non-null ``workflow_status`` (bounded, stable order)."""
    return _column_distribution(rows, resolved, "workflow_status")


def _progress_chart(counts: dict[str, int], grain: str) -> Any:
    """Pie drawing: progress-status distribution (DejaVu labels)."""
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib.colors import HexColor

    labels = (
        f"Зелёный (green): {counts['green']}",
        f"Жёлтый (yellow): {counts['yellow']}",
        f"Красный (red): {counts['red']}",
    )
    drawing = Drawing(460, 170)
    title = String(
        230,
        155,
        f"Распределение {grain} по прогрессу workflow, %",
        fontName=FONT_BOLD,
        fontSize=10,
        textAnchor="middle",
    )
    drawing.add(title)
    pie = Pie()
    pie.x = 150
    pie.y = 10
    pie.width = 130
    pie.height = 130
    pie.data = [counts["green"], counts["yellow"], counts["red"]]
    pie.labels = [label if value else "" for label, value in zip(labels, pie.data, strict=True)]
    pie.slices.fontName = FONT_REGULAR
    pie.slices.fontSize = 8
    pie.slices.strokeWidth = 1
    pie.slices.strokeColor = HexColor("#FFFFFF")
    pie.slices[0].fillColor = HexColor("#43A047")
    pie.slices[1].fillColor = HexColor("#FBC02D")
    pie.slices[2].fillColor = HexColor("#E53935")
    pie.sideLabels = True
    drawing.add(pie)
    return drawing


def _workflow_chart(distribution: list[tuple[str, int]]) -> Any:
    """Horizontal bar drawing: rows per workflow status (DejaVu labels)."""
    return _bar_chart("Распределение строк по статусу работы", distribution)


def _bar_chart(heading: str, distribution: list[tuple[str, int]]) -> Any:
    """Horizontal bar drawing for a generic distribution (DejaVu labels)."""
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib.colors import HexColor

    names = [label for label, _ in distribution]
    values = [[count for _, count in distribution]]
    height = max(120, 40 + 22 * len(names))
    drawing = Drawing(460, height + 40)
    title = String(
        230,
        height + 22,
        heading,
        fontName=FONT_BOLD,
        fontSize=10,
        textAnchor="middle",
    )
    drawing.add(title)
    chart = HorizontalBarChart()
    chart.x = 150
    chart.y = 10
    chart.width = 280
    chart.height = height
    chart.data = values
    chart.categoryAxis.categoryNames = names
    chart.categoryAxis.labels.fontName = FONT_REGULAR
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = FONT_REGULAR
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = HexColor("#4472C4")
    chart.bars[0].strokeColor = HexColor("#2F5597")
    chart.barLabels.fontName = FONT_REGULAR
    chart.barLabels.fontSize = 8
    drawing.add(chart)
    return drawing


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def _footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 20, f"Страница {doc.page}")
    canvas.restoreState()


def generate_pdf_report(
    db: Session,
    filters: UnifiedFilter,
    columns: list[str] | tuple[str, ...] | None,
    output_path: str | Path,
    *,
    user: Any | None = None,
    generated_at: datetime | None = None,
    group_by: str | None = None,
) -> _xlsx.GeneratedReport:
    """Generate the frozen PDF report from the report dataset.

    ``columns=None`` selects the ТЗ default ``DEFAULT_COLUMNS``;
    otherwise the resolved/deduped ``ReportRequest.columns`` order is kept
    verbatim (never sorted). Raises ``UnknownReportColumnError`` /
    ``EmptyReportColumnsError`` (both ``ValueError``) for invalid
    selections — the future P4-03-01 endpoint maps them to 422 — and
    :class:`PDFFontUnavailableError` when no Cyrillic font is available.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    resolved = resolve_columns(columns)
    ensure_pdf_fonts()  # centralized, once — never per cell/row
    moment = _ensure_tz_aware(generated_at)

    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(final_path.name + ".part")

    try:
        # Stream the dataset cursor. We retain only transformed table rows for
        # ReportLab's LongTable; ORM mappings are never materialized by
        # fetch_rows or list(iterator). KPI counters are accumulated inline.
        # university_count uses distinct university names when the column is
        # selected, else the filtered university scope (same predicate set).
        rows: list[dict[str, Any]] = []
        kpi = ReportKpi()
        for row in ReportDatasetService.iterate_rows(db, filters, resolved, user=user):
            rows.append(row)
            kpi.add_row(row)
        university_count = kpi.resolve_university_count(
            _scope_university_count(db, filters, user)
        )

        page = landscape(A4)
        margin = 12 * mm
        doc = SimpleDocTemplate(
            str(tmp_path),
            pagesize=page,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=18 * mm,
            title=_xlsx.REPORT_TITLE,
            author="RTK CRM Analytics",
            subject="Аналитический отчёт по взаимодействию с ВУЗами",
        )

        body_style = ParagraphStyle("p4-body", fontName=FONT_REGULAR, fontSize=10, leading=13)
        title_style = ParagraphStyle(
            "p4-title", fontName=FONT_BOLD, fontSize=16, leading=19, spaceAfter=6
        )
        heading_style = ParagraphStyle(
            "p4-heading",
            fontName=FONT_BOLD,
            fontSize=12,
            leading=15,
            spaceBefore=10,
            spaceAfter=6,
        )
        cell_style = ParagraphStyle("p4-cell", fontName=FONT_REGULAR, fontSize=7, leading=9)
        cell_header_style = ParagraphStyle(
            "p4-cell-header",
            fontName=FONT_BOLD,
            fontSize=7,
            leading=9,
            textColor=colors.white,
        )
        names = _xlsx._lookup_names(db, filters)  # noqa: SLF001 - single name-resolution source

        story: list[Any] = [
            Paragraph(_xml_escape(_xlsx.REPORT_TITLE), title_style),
            Paragraph(_xml_escape(_xlsx.format_period(filters)), body_style),
            Paragraph(_xml_escape(_xlsx.build_filter_summary(filters, names)), body_style),
            Paragraph(f"Сформирован: {moment:%d.%m.%Y %H:%M %Z}", body_style),
            Spacer(1, 4 * mm),
            Paragraph("Ключевые показатели", heading_style),
        ]
        avg_progress = kpi.avg_workflow_progress
        kpi_lines = (
            f"Количество ВУЗов: {university_count}",
            f"Строк в отчёте: {kpi.row_count}",
            f"Средний прогресс workflow, %: "
            f"{avg_progress if avg_progress is not None else '—'}",
            f"Просроченные задачи: {kpi.overdue_total}",
        )
        for line in kpi_lines:
            story.append(Paragraph(_xml_escape(line), body_style))

        if group_by:
            summary = ReportStatsService.group_slice(db, filters, group_by, columns=resolved, user=user)
            story.append(Paragraph(_xml_escape(summary.title), heading_style))
            group_rows = [[
                Paragraph("Группа", cell_header_style),
                Paragraph("Вузов" if summary.unit == "universities" else "Строк", cell_header_style),
            ], *[[Paragraph(_xml_escape(bucket.label), cell_style), bucket.count] for bucket in summary.buckets]]
            group_table = LongTable(group_rows, colWidths=[(page[0] - 2 * margin) * .8, (page[0] - 2 * margin) * .2], repeatRows=1)
            group_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#BFBFBF")),
            ]))
            story.append(group_table)

        story.append(Paragraph("Данные", heading_style))
        header = [
            Paragraph(_xml_escape(COLUMN_REGISTRY[key].title), cell_header_style)
            for key in resolved
        ]
        body = [
            [
                Paragraph(_xml_escape(format_cell_value(key, row.get(key))), cell_style)
                for key in resolved
            ]
            for row in rows
        ]
        avail = page[0] - 2 * margin
        weights = [
            float(_xlsx.MIN_COLUMN_WIDTHS.get(key, _xlsx.DEFAULT_MIN_WIDTH)) for key in resolved
        ]
        total_weight = sum(weights) or float(len(resolved))
        col_widths = [avail * w / total_weight for w in weights]
        table = LongTable([header, *body], colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#EAF0FA")],
                    ),
                ]
            )
        )
        story.append(table)

        story.append(Paragraph("Графики", heading_style))
        counts, grain = _progress_distribution(rows, resolved)
        if sum(counts.values()) > 0:
            story.append(_progress_chart(counts, grain))
        else:
            story.append(
                Paragraph(
                    _xml_escape(f"{NO_CHART_DATA_TEXT} (нет измеренного прогресса workflow)"),
                    body_style,
                )
            )
        story.append(Spacer(1, 4 * mm))
        chart_specs = (
            ("Распределение строк по статусу работы", "workflow_status"),
            ("Распределение строк по ИТ-направлениям", "direction"),
            ("Распределение строк по ИТ-продуктам", "product"),
            ("Нагрузка на ответственных", "responsible"),
        )
        for heading, column in chart_specs:
            distribution = _column_distribution(rows, resolved, column)
            if distribution:
                story.append(_bar_chart(heading, distribution))
            else:
                reason = (
                    "колонка не выбрана"
                    if column not in resolved
                    else "нет данных"
                )
                story.append(
                    Paragraph(
                        _xml_escape(f"{heading}: {NO_CHART_DATA_TEXT} ({reason})"),
                        body_style,
                    )
                )
            story.append(Spacer(1, 4 * mm))

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        tmp_path.replace(final_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise

    return _xlsx.GeneratedReport(
        path=final_path,
        size_bytes=final_path.stat().st_size,
        row_count=len(rows),
        generated_at=moment,
        columns=resolved,
    )
