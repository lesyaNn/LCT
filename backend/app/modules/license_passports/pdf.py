"""Print-ready A4 certificate. Fonts and QR are embedded; no remote assets."""

import io
import re
import threading
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.modules.analytics.pdf import FONT_BOLD, FONT_REGULAR, ensure_pdf_fonts
from app.modules.license_passports.schemas import LicensePassport

PURPLE = colors.HexColor("#7700FF")
ORANGE = colors.HexColor("#FF4F12")
INK = colors.HexColor("#101828")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#E4E7EC")
LOGO = Path(__file__).resolve().parents[2] / "assets" / "rostelecom-horizontal.png"
_font_lock = threading.Lock()


def _paragraph(text: str, size=11, *, bold=False, color=INK, after=0):
    # Treat all DB values as text, never markup, links or image instructions.
    text = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", text).split())
    return Paragraph(escape(text), ParagraphStyle(
        "passport", fontName=FONT_BOLD if bold else FONT_REGULAR,
        fontSize=size, leading=size * 1.35, textColor=color,
        spaceAfter=after, splitLongWords=True,
    ))


def generate_passport_pdf(data: LicensePassport) -> bytes:
    with _font_lock:
        ensure_pdf_fonts()
    buffer = io.BytesIO()
    w, h = A4
    left, width = 48, w - 96
    safe_url = escape(data.verification_url, {'"': '&quot;'})
    verification_link = Paragraph(
        f'Проверка: <link href="{safe_url}" color="#7700FF">'
        f'<u>{escape(data.verification_url)}</u></link>',
        ParagraphStyle("verification-link", fontName=FONT_REGULAR, fontSize=8,
                       leading=11, textColor=MUTED, splitLongWords=True),
    )
    _, link_height = verification_link.wrap(width, h)
    # Reserve additional space above the footer for unusually long hostnames.
    verification_shift = max(0, link_height - 22)

    def decorate(canvas, document):
        def draw(text, x, top, available_width, size=11, **kwargs):
            paragraph = _paragraph(text, size, **kwargs)
            _, height = paragraph.wrap(available_width, h)
            paragraph.drawOn(canvas, x, top - height)
            return height

        # An inset frame and a restrained brand accent survive office printing.
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(.7)
        canvas.rect(24, 24, w - 48, h - 48, stroke=1, fill=0)
        canvas.setFillColor(PURPLE)
        canvas.rect(24, h - 28, w - 48, 4, fill=1, stroke=0)
        canvas.setFillColor(ORANGE)
        canvas.rect(w - 92, h - 28, 68, 4, fill=1, stroke=0)
        canvas.drawImage(str(LOGO), left, h - 114, width=190, height=190 * 1556 / 5950,
                         preserveAspectRatio=True, mask="auto")
        draw("ИТ ШКОЛА", w - 175, h - 77, 127, 10, bold=True, color=PURPLE)
        draw("Лицензионный документ", w - 175, h - 96, 127, 8, color=MUTED)
        first = canvas.getPageNumber() == 1
        if first:
            draw("ПАСПОРТ", left, h - 145, width, 28, bold=True)
            draw("ЛИЦЕНЗИИ", left, h - 179, width, 28, bold=True, color=PURPLE)
        else:
            draw("ПАСПОРТ ЛИЦЕНЗИИ · ПРОДОЛЖЕНИЕ", left, h - 145, width, 16, bold=True, color=PURPLE)
        draw(f"№ {data.passport_number}", left, h - (225 if first else 178), width, 8, color=MUTED)
        canvas.setStrokeColor(LINE)
        canvas.line(left, h - (247 if first else 200), w - left, h - (247 if first else 200))

        canvas.setStrokeColor(LINE)
        canvas.line(left, 225 + verification_shift, w - left, 225 + verification_shift)
        # Black vector QR with a four-module quiet zone, approximately 36 mm wide.
        qr = QrCodeWidget(data.verification_url, barLevel="M", barBorder=4)
        bounds = qr.getBounds()
        qr_size = 104
        scale = qr_size / (bounds[2] - bounds[0])
        drawing = Drawing(qr_size, qr_size, transform=[scale, 0, 0, scale, 0, 0])
        drawing.add(qr)
        renderPDF.draw(drawing, canvas, left - 7, 105 + verification_shift)
        canvas.linkURL(data.verification_url, (left - 7, 105 + verification_shift,
                       left - 7 + qr_size, 209 + verification_shift), relative=0)
        x = left + 120
        draw("ПРОВЕРКА ПОДЛИННОСТИ", x, 204 + verification_shift, width - 120, 9, bold=True)
        draw("Отсканируйте QR-код для проверки подлинности лицензии", x, 183 + verification_shift, width - 120, 10)
        draw("Идентификатор лицензии", x, 144 + verification_shift, width - 120, 8, color=MUTED)
        draw(str(data.license_id), x, 130 + verification_shift, width - 120, 8)
        verification_link.drawOn(canvas, left, 101 + verification_shift - link_height)
        draw("QR-код сверяет сведения с CRM. Документ не заменяет договор и электронную подпись.",
             left, 69, width, 7.5, color=MUTED)
        canvas.setStrokeColor(LINE)
        canvas.line(left, 52, w - left, 52)
        draw(data.passport_number, left, 43, width * .6, 7, color=MUTED)
        draw(f"{data.generated_at:%d.%m.%Y %H:%M} UTC · {canvas.getPageNumber()}", left + width * .62,
             43, width * .38, 7, color=MUTED)

    def label(value):
        return _paragraph(value, 8, color=MUTED, after=5)

    def date_cell(label_text, value):
        return [label(label_text), _paragraph(value.strftime("%d.%m.%Y"), 17, bold=True)]

    dates = Table([[date_cell("НАЧАЛО ДЕЙСТВИЯ", data.signed_at),
                    date_cell("ОКОНЧАНИЕ ДЕЙСТВИЯ", data.expires_at)]],
                  colWidths=[width / 2, width / 2])
    dates.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    # Full text, bounded readable sizes; unusually long fields flow onto the
    # next A4 sheet instead of being truncated or shrunk to illegible text.
    recipient_size = 14 if len(data.university_name) > 240 else 21
    product_size = 11 if len(data.product_name) > 240 else 15
    content = [KeepTogether([label("ПОЛУЧАТЕЛЬ ЛИЦЕНЗИИ"),
               _paragraph(data.university_name, recipient_size, bold=True)]), Spacer(1, 18),
               KeepTogether([label("ПРОГРАММНОЕ ОБЕСПЕЧЕНИЕ"),
               _paragraph(data.product_name, product_size, bold=True)]), Spacer(1, 6)]
    if data.vendor_name:
        content += [_paragraph(f"Вендор: {data.vendor_name}", 9, color=MUTED), Spacer(1, 6)]
    content += [Spacer(1, 6), _paragraph(f"Лицензия № {data.license_number}", 9 if len(data.license_number) > 128 else 10),
                Spacer(1, 4),
                _paragraph(f"Договор № {data.contract_number} от {data.contract_signed_at:%d.%m.%Y}", 9 if len(data.contract_number) > 128 else 10),
                Spacer(1, 18), KeepTogether([dates, Spacer(1, 18),
                _paragraph(data.status_label, 12, bold=True, color=PURPLE),
                Spacer(1, 4), _paragraph(data.status_reason, 9, color=MUTED)])]
    document = BaseDocTemplate(
        buffer, pagesize=A4, pageCompression=1,
        title=f"Паспорт лицензии {data.passport_number}", author="Ростелеком · ИТ Школа",
    )
    document.addPageTemplates([
        PageTemplate(id=name, onPage=decorate, autoNextPageTemplate="continuation", frames=[
            Frame(left, 244 + verification_shift, width, h - top - 244 - verification_shift, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0),
        ]) for name, top in (("first", 264), ("continuation", 217))
    ])
    document.build(content)
    return buffer.getvalue()
