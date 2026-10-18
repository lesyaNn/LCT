"""Paginated, searchable PDF from the current editor document; no remote assets."""

import io
import re
import threading
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.modules.analytics.pdf import FONT_BOLD, FONT_REGULAR, ensure_pdf_fonts

_font_lock = threading.Lock()
PURPLE = colors.HexColor("#7700FF")
INK = colors.HexColor("#101828")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#E4E7EC")


def _clean(value) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value if isinstance(value, str) else "")


def _children(node):
    children = node.get("content", [])
    return [child for child in children if isinstance(child, dict)] if isinstance(children, list) else []


def _attrs(node):
    value = node.get("attrs")
    return value if isinstance(value, dict) else {}


def _integer(value, default=1):
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return default


def _fonts():
    with _font_lock:
        paths = ensure_pdf_fonts()
        base = Path(paths["regular"]).parent
        names = {}
        for suffix, file in [("Italic", "DejaVuSans-Oblique.ttf"),
                             ("BoldItalic", "DejaVuSans-BoldOblique.ttf"),
                             ("Mono", "DejaVuSansMono.ttf")]:
            name, path = f"Notes-{suffix}", base / file
            if path.is_file():
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                names[suffix] = name
            else:
                names[suffix] = FONT_BOLD if suffix == "BoldItalic" else FONT_REGULAR
        pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD,
                                      italic=names["Italic"], boldItalic=names["BoldItalic"])
        if names["Mono"] != FONT_REGULAR:
            pdfmetrics.registerFontFamily(names["Mono"], normal=names["Mono"], bold=names["Mono"],
                                          italic=names["Mono"], boldItalic=names["Mono"])
        return names["Mono"]


def generate_note_pdf(title: str, document: dict, origin: str,
                      resolve_link: Callable[[str], str | None]) -> bytes:
    mono = _fonts()
    width = A4[0] - 100
    base_style = ParagraphStyle("note", fontName=FONT_REGULAR, fontSize=10.5,
                                leading=16, textColor=INK, spaceAfter=9, splitLongWords=True)

    def style(**kwargs):
        return ParagraphStyle("note-part", parent=base_style, **kwargs)

    def href(value):
        if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f]", value):
            return None
        try:
            value = resolve_link(value)
            if not value:
                return None
            value = urljoin(origin.rstrip("/") + "/", value)
            parsed = urlsplit(value)
        except ValueError:
            return None
        return escape(value, {'"': '&quot;'}) if parsed.scheme in {"http", "https", "mailto"} else None

    def inline(node):
        kind = node.get("type")
        if kind == "hardBreak":
            return "<br/>"
        if kind == "image":
            return escape(_clean(_attrs(node).get("alt")) or "Изображение")
        if kind != "text":
            return "".join(inline(child) for child in _children(node))
        text = escape(_clean(node.get("text"))).replace("\n", "<br/>")
        marks = node.get("marks", [])
        for mark in marks if isinstance(marks, list) else []:
            if not isinstance(mark, dict):
                continue
            kind = mark.get("type")
            if kind in {"bold", "italic", "strike"}:
                tag = {"bold": "b", "italic": "i", "strike": "strike"}[kind]
                text = f"<{tag}>{text}</{tag}>"
            elif kind == "code":
                text = f'<font name="{mono}" backColor="#F2F4F7">{text}</font>'
            elif kind == "link":
                target = href(_attrs(mark).get("href"))
                if target:
                    text = f'<link href="{target}" color="#7700FF"><u>{text}</u></link>'
        return text

    def blocks(nodes, depth=0, quote=False):
        result = []
        indent = min(depth * 16, 160)
        for node in nodes:
            kind, attrs, children = node.get("type"), _attrs(node), _children(node)
            if kind in {"paragraph", "heading"}:
                markup = inline(node)
                options = {"leftIndent": indent, "textColor": MUTED if quote else INK}
                if kind == "heading":
                    level = max(1, min(3, _integer(attrs.get("level"))))
                    size = {1: 22, 2: 17, 3: 13}[level]
                    options.update(fontName=FONT_BOLD, fontSize=size, leading=size * 1.3,
                                   spaceBefore=14, spaceAfter=8, keepWithNext=True)
                result.append(Paragraph(markup, style(**options)) if markup else Spacer(1, 8))
            elif kind in {"bulletList", "orderedList", "taskList"}:
                start = max(1, _integer(attrs.get("start")))
                for index, item in enumerate(children, start):
                    label = (f"{index}." if kind == "orderedList" else
                             "☑" if kind == "taskList" and _attrs(item).get("checked") else
                             "☐" if kind == "taskList" else "•")
                    content = _children(item)
                    if content and content[0].get("type") == "paragraph":
                        result.append(Paragraph(inline(content[0]) or "&nbsp;", style(
                            leftIndent=indent + 18, bulletIndent=indent, spaceAfter=5,
                            bulletFontName=FONT_REGULAR, bulletFontSize=10.5,
                        ), bulletText=label))
                        result.extend(blocks(content[1:], depth + 1, quote))
                    else:
                        result.append(Paragraph(escape(label), style(leftIndent=indent)))
                        result.extend(blocks(content, depth + 1, quote))
                result.append(Spacer(1, 4))
            elif kind == "blockquote":
                result.extend(blocks(children, depth + 1, True))
            elif kind == "codeBlock":
                code = "".join(_clean(child.get("text")) for child in children)
                markup = escape(code).replace("\t", "    ").replace(" ", "&nbsp;").replace("\n", "<br/>")
                result.append(Paragraph(markup or "&nbsp;", style(fontName=mono, fontSize=9,
                    leading=13, backColor=colors.HexColor("#F2F4F7"), borderPadding=8,
                    leftIndent=indent + 8, rightIndent=8, spaceBefore=8, spaceAfter=14)))
            elif kind == "horizontalRule":
                result.extend([Spacer(1, 6), HRFlowable(width="100%", color=LINE), Spacer(1, 14)])
            elif kind == "table":
                rows, spans, occupied = [], [], set()
                for row_index, row in enumerate(children):
                    cells, col = {}, 0
                    for cell in _children(row):
                        while (row_index, col) in occupied:
                            col += 1
                        cell_attrs = _attrs(cell)
                        colspan = max(1, min(64, _integer(cell_attrs.get("colspan"))))
                        rowspan = max(1, min(len(children) - row_index, _integer(cell_attrs.get("rowspan"))))
                        if col + colspan > 64 or len(occupied) + colspan * rowspan > 50_000:
                            raise ValueError("Table is too large for PDF export")
                        cells[col] = blocks(_children(cell)) or [Paragraph("&nbsp;", base_style)]
                        if colspan > 1 or rowspan > 1:
                            spans.append(("SPAN", (col, row_index), (col + colspan - 1, row_index + rowspan - 1)))
                        for y in range(row_index, row_index + rowspan):
                            for x in range(col, col + colspan):
                                occupied.add((y, x))
                        col += colspan
                    rows.append(cells)
                columns = max((x + 1 for _, x in occupied), default=0)
                if rows and columns:
                    if columns > 64 or columns * len(rows) > 50_000:
                        raise ValueError("Table is too large for PDF export")
                    header = bool(_children(children[0])) and all(cell.get("type") == "tableHeader" for cell in _children(children[0]))
                    table = LongTable([[row.get(x, "") for x in range(columns)] for row in rows],
                                      colWidths=[(width - indent) / columns] * columns,
                                      repeatRows=1 if header else 0, splitInRow=1, hAlign="LEFT")
                    commands = [("GRID", (0, 0), (-1, -1), .5, LINE),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
                    if header:
                        commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4EBFF")))
                    table.setStyle(TableStyle(commands + spans))
                    result.extend([table, Spacer(1, 12)])
            elif kind == "image":
                # Do not let a note cause arbitrary HTTP or filesystem reads.
                label = escape(_clean(attrs.get("alt")) or "Изображение")
                target = href(attrs.get("src"))
                result.append(Paragraph(f'<link href="{target}">{label}</link>' if target else label,
                                        style(textColor=MUTED, leftIndent=indent)))
            else:
                result.extend(blocks(children, depth, quote))
        return result

    title = _clean(title).strip() or "Без названия"
    output = io.BytesIO()
    document_pdf = SimpleDocTemplate(output, pagesize=A4, leftMargin=44, rightMargin=44,
                                    topMargin=44, bottomMargin=48, title=title,
                                    author="CRM · ИТ Школа", pageCompression=1)

    def footer(canvas, _document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(44, 35, A4[0] - 44, 35)
        canvas.setFont(FONT_REGULAR, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(44, 22, "Заметки · CRM")
        canvas.drawRightString(A4[0] - 44, 22, str(canvas.getPageNumber()))
        canvas.restoreState()

    story = [Paragraph(escape(title), style(fontName=FONT_BOLD, fontSize=24, leading=30, spaceAfter=20))]
    story.extend(blocks(_children(document)))
    document_pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
