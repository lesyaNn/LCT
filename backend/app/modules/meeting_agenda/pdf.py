"""A bounded A4 brief. Text is measured and shortened, never drawn outside cells."""

import io
import re
import threading
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from app.modules.analytics.pdf import FONT_BOLD, FONT_REGULAR, ensure_pdf_fonts
from app.modules.meeting_agenda.schemas import MeetingAgenda

PDF_ROWS = 4
_font_lock = threading.Lock()
_DASHES = str.maketrans({char: "-" for char in "\u2010\u2011\u2012\u2013\u2014\u2212"})


def _text(value: str) -> str:
    # User input is plain text, not ReportLab markup or a remote resource.
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", value).translate(_DASHES).split())[:10000]


def _paragraph(
    text: str, width: float, height: float, *, bold=False, size=9
) -> tuple[Paragraph, float]:
    style = ParagraphStyle(
        "agenda",
        fontName=FONT_BOLD if bold else FONT_REGULAR,
        fontSize=size,
        leading=size * 1.35,
        textColor=colors.HexColor("#172b3a"),
        splitLongWords=True,
    )
    text = _text(text)
    # This is a two-line brief, not an unbounded document renderer. Bound the
    # input to the expensive line-breaking algorithm before binary search;
    # even 10,000-character comments must not make a synchronous export slow.
    if len(text) > 900:
        text = text[:900].rstrip() + "..."

    def measure(value):
        paragraph = Paragraph(escape(value), style)
        _, measured = paragraph.wrap(width, height)
        return paragraph, measured

    paragraph, measured = measure(text)
    if measured <= height:
        return paragraph, measured
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid].rstrip() + "...")[1] <= height:
            low = mid
        else:
            high = mid - 1
    return measure(text[:low].rstrip() + "...")


def generate_agenda_pdf(agenda: MeetingAgenda) -> bytes:
    with _font_lock:
        ensure_pdf_fonts()
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setTitle("Повестка встречи")
    canvas.setAuthor("CRM ИТ Школы РТК")
    width, height = A4
    margin, content_width = 36, width - 72

    def draw(text, x, top, w, h, **kwargs):
        paragraph, measured = _paragraph(text, w, h, **kwargs)
        paragraph.drawOn(canvas, x, top - measured)

    canvas.setFillColor(colors.HexColor("#163c52"))
    canvas.rect(0, height - 35, width, 35, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, 10)
    canvas.drawString(margin, height - 23, "ИТ ШКОЛА РТК / CRM")
    draw("Повестка встречи", margin, height - 52, content_width, 30, bold=True, size=21)
    draw(agenda.university_name, margin, height - 88, content_width, 40, bold=True, size=12)
    draw(
        f"Этап {agenda.stage_order}: {agenda.stage_name} | {agenda.city or 'Город не указан'}",
        margin,
        height - 135,
        content_width,
        27,
        size=9,
    )
    draw(
        f"Сформировано: {agenda.generated_at:%d.%m.%Y %H:%M} UTC. Данные на {agenda.as_of:%d.%m.%Y}.",
        margin,
        height - 167,
        content_width,
        18,
        size=8,
    )

    def section(top, title, rows, total, empty):
        canvas.setFillColor(colors.HexColor("#edf4f7"))
        canvas.roundRect(margin, top - 25, content_width, 25, 4, fill=1, stroke=0)
        draw(f"{title} ({total})", margin + 10, top - 5, content_width - 20, 18, bold=True, size=10)
        y = top - 34
        if not rows:
            draw(empty, margin + 10, y, content_width - 20, 30)
        for index, text in enumerate(rows[:PDF_ROWS], 1):
            draw(f"{index}. {text}", margin + 10, y, content_width - 20, 29)
            y -= 34
        omitted = max(0, total - min(len(rows), PDF_ROWS))
        if omitted:
            draw(
                f"Ещё записей: {omitted}. Полный текст и список доступны в CRM.",
                margin + 10,
                top - 174,
                content_width - 20,
                16,
                size=8,
            )

    section(
        height - 202,
        "Действующие ИТ-программы",
        [
            f"{p.name} / {p.direction}"
            + (f". Запуск {p.launch_date:%d.%m.%Y}" if p.launch_date else "")
            for p in agenda.programs.items[:PDF_ROWS]
        ],
        agenda.programs.total,
        "Действующие программы не указаны.",
    )
    section(
        height - 399,
        f"Лицензии: истекают за {agenda.warning_days} дней",
        [
            f"До {lic.expires_at:%d.%m.%Y} ({lic.days_left} дн.), № {lic.license_number}: {lic.product}"
            for lic in agenda.expiring_licenses.items[:PDF_ROWS]
        ],
        agenda.expiring_licenses.total,
        f"С {agenda.as_of:%d.%m.%Y} по {agenda.expires_through:%d.%m.%Y} истекающих лицензий нет.",
    )
    section(
        height - 596,
        "Открытые вопросы из комментариев",
        [f"{q.created_at:%d.%m.%Y}: {q.content}" for q in agenda.open_questions.items[:PDF_ROWS]],
        agenda.open_questions.total,
        "Нет комментариев, отмеченных как открытые вопросы.",
    )
    canvas.setStrokeColor(colors.HexColor("#b8c8d1"))
    canvas.line(margin, 39, width - margin, 39)
    draw(
        "Внутренний документ. Длинные записи сокращены многоточием. Подробности в CRM.",
        margin,
        32,
        content_width - 20,
        15,
        size=7,
    )
    canvas.setFont(FONT_REGULAR, 8)
    canvas.setFillColor(colors.HexColor("#647887"))
    canvas.drawRightString(width - margin, 22, "1 / 1")
    canvas.showPage()
    canvas.save()
    return output.getvalue()
