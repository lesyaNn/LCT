"""P4-04-01/02 PDF report generator (production exporter, no SQL inside).

Data comes ONLY from :class:`ReportDatasetService` (same filters, same row
grain, same selected columns, same health/workflow values as the dataset).
Column titles come ONLY from ``COLUMN_REGISTRY`` — there is no second
``PDF_COLUMN_MAPPING``. ``UnifiedFilter`` semantics stay frozen (date bounds
on ``universities.created_at``, AND between dimensions, OR/IN within).

Presentation helpers (title text, period text, human-readable filter
summary, result metadata, width ratios) are reused from
:mod:`app.modules.analytics.xlsx` so XLSX/PDF metadata can never drift;
only the rendering backend differs (reportlab platypus, landscape A4).

Layout (frozen)::

    1. title (``Аналитический отчёт по взаимодействию с ВУЗами``)
    2. period (same text as XLSX, neutral ``Период: не задан`` when unset)
    3. applied filters (human-readable summary, UUID names batched, no N+1)
    4. ``Сформирован: <tz-aware timestamp>``
    5. KPI block (same filtered dataset: universities / rows / avg health)
    6. table (selected columns in ``ReportRequest.columns`` order, titles
       from ``COLUMN_REGISTRY``, header repeated on every page)
    7. charts (health-status distribution + workflow-status distribution,
       reportlab native drawings — no matplotlib runtime dependency)

Cyrillic (P4-04-02): every string is rendered with ``DejaVuSans`` /
``DejaVuSans-Bold`` registered ONCE via :func:`ensure_pdf_fonts`
(never per cell/row). Font files are discovered at runtime (Debian
``fonts-dejavu-core`` path, ``REPORT_PDF_FONT_DIR`` override, matplotlib
bundle as a best-effort dev fallback) — no font binary lives in the repo
and no font file is served to users. Without a usable font the generator
raises :class:`PDFFontUnavailableError` instead of producing mojibake
with Helvetica.

Charts use the canonical P2 thresholds via
``app.modules.health_score.status.get_health_status`` (never hardcoded
``85``/``60`` here). Chart 1 groups per university when the ``university``
column is selected (first non-null health per university name), otherwise
it falls back to row grain; the chart title always states the grain.
Empty datasets still produce a valid PDF: chart sections render
``Нет данных для построения графика``.

PDF metadata (title/author) is set; no secrets or tokens are embedded.

Output is written to ``<final>.part`` first and atomically replaced to
the final ``.pdf`` only after a successful build; on failure the temp
file is removed and no partial file is left behind.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from sqlalchemy.orm import Session

from app.modules.analytics import xlsx as _xlsx
from app.modules.analytics.columns import COLUMN_REGISTRY, resolve_columns
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.health_score.status import get_health_status

__all__ = [
    "FONT_BOLD",
    "FONT_REGULAR",
    "NO_CHART_DATA_TEXT",
    "PDF_PAGE_SIZE_ORIENTATION",
    "PDFFontUnavailableError",
    "compute_kpi",
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
    * ``health_score`` stays numeric ``0..100`` (never recomputed here);
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


def compute_kpi(dataset: Any) -> dict[str, Any]:
    """KPI block from the SAME filtered dataset as the table.

    ``Количество ВУЗов`` = ``dataset.university_count``,
    ``Количество строк`` = ``dataset.total`` (University × License grain),
    ``Средний Health Score`` = mean of non-null ``health_score`` values
    (``None`` when no scores — never 0). Security scope matches the table
    by construction (one dataset object).
    """
    rows = list(getattr(dataset, "rows", []) or [])
    scores = [
        row["health_score"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("health_score"), (int, float))
        and not isinstance(row.get("health_score"), bool)
    ]
    avg = round(sum(scores) / len(scores), 1) if scores else None
    return {
        "university_count": int(getattr(dataset, "university_count", 0) or 0),
        "row_count": int(getattr(dataset, "total", len(rows)) or 0),
        "avg_health_score": avg,
        "health_scored_rows": len(scores),
    }


def _ensure_tz_aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


# ---------------------------------------------------------------------------
# Charts (reportlab native drawings; canonical P2 thresholds only)
# ---------------------------------------------------------------------------


def _health_distribution(
    rows: list[dict[str, Any]], resolved: list[str]
) -> tuple[dict[str, int], str]:
    """Count green/yellow/red via canonical ``get_health_status``.

    Per-university grain when the ``university`` column is selected
    (first non-null health per university name), else row grain. The
    returned grain label is rendered in the chart title (honest label).
    """
    per_university = "university" in resolved
    if per_university:
        seen: dict[str, int] = {}
        for row in rows:
            name = row.get("university")
            score = row.get("health_score")
            if (
                name is None
                or score is None
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
            ):
                continue
            key = str(name)
            if key not in seen:
                seen[key] = int(score)
        scores = list(seen.values())
        grain = "по ВУЗам"
    else:
        scores = [
            int(row["health_score"])
            for row in rows
            if isinstance(row.get("health_score"), (int, float))
            and not isinstance(row.get("health_score"), bool)
        ]
        grain = "по строкам отчёта"
    counts = {"green": 0, "yellow": 0, "red": 0}
    for score in scores:
        counts[get_health_status(int(score)).value] += 1
    return counts, grain


def _workflow_distribution(
    rows: list[dict[str, Any]], resolved: list[str]
) -> list[tuple[str, int]]:
    """Count rows per non-null ``workflow_status`` (bounded, stable order)."""
    if "workflow_status" not in resolved:
        return []
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("workflow_status")
        if status is None:
            continue
        label = str(status)
        if label:
            counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) > _MAX_WORKFLOW_SLICES:
        head = ordered[: _MAX_WORKFLOW_SLICES - 1]
        rest = sum(n for _, n in ordered[_MAX_WORKFLOW_SLICES - 1 :])
        head.append(("Прочее", rest))
        return head
    return ordered


def _health_chart(counts: dict[str, int], grain: str) -> Any:
    """Pie drawing: health-status distribution (DejaVu labels)."""
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
        f"Распределение {grain} по статусу Health Score",
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
        "Распределение строк по статусу работы",
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
) -> _xlsx.GeneratedReport:
    """Generate the frozen PDF report from the report dataset.

    ``columns=None`` selects the frozen 14 mandatory ``DEFAULT_COLUMNS``;
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
        rows: list[dict[str, Any]] = []
        university_ids: set[Any] = set()
        score_sum = 0.0
        score_count = 0
        for row in ReportDatasetService.iterate_rows(db, filters, resolved, user=user):
            rows.append(row)
            if row.get("university") is not None:
                university_ids.add(row.get("university"))
            score = row.get("health_score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                score_sum += float(score)
                score_count += 1
        kpi = {
            "university_count": len(university_ids),
            "row_count": len(rows),
            "avg_health_score": round(score_sum / score_count, 2) if score_count else None,
        }

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
        avg_text = str(kpi["avg_health_score"]) if kpi["avg_health_score"] is not None else "—"
        kpi_lines = (
            f"Количество ВУЗов: {kpi['university_count']}",
            f"Количество строк (лицензий): {kpi['row_count']}",
            f"Средний Health Score: {avg_text}",
        )
        for line in kpi_lines:
            story.append(Paragraph(_xml_escape(line), body_style))

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
        counts, grain = _health_distribution(rows, resolved)
        if sum(counts.values()) > 0:
            story.append(_health_chart(counts, grain))
        else:
            story.append(Paragraph(_xml_escape(NO_CHART_DATA_TEXT), body_style))
        story.append(Spacer(1, 4 * mm))
        distribution = _workflow_distribution(rows, resolved)
        if distribution:
            story.append(_workflow_chart(distribution))
        else:
            story.append(Paragraph(_xml_escape(NO_CHART_DATA_TEXT), body_style))

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
