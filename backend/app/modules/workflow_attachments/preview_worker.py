"""Bounded, isolated extraction. Never extracts archive members onto disk."""
from __future__ import annotations

import base64
import json
import io
import math
from pathlib import Path, PurePosixPath
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

MAX_XML = 2 * 1024 * 1024
MAX_ENTRIES = 10000


def xml_member(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_XML or info.file_size > max(info.compress_size, 1) * 200:
        raise ValueError("Документ слишком сложный для предпросмотра")
    raw = archive.read(info)
    if b'<!DOCTYPE' in raw.replace(b'\x00', b'').upper() or b'<!ENTITY' in raw.replace(b'\x00', b'').upper():
        raise ValueError("Небезопасная структура документа")
    return ET.fromstring(raw)


def entry(name, size, directory=False):
    name = name.replace('\\', '/')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name:
        raise ValueError("Архив содержит небезопасные пути")
    return {"name": name[:1024], "size": size, "directory": directory,
            "extension": path.suffix.lower().lstrip('.')}


def extract(path, filename, offset):
    with open(path, 'rb') as source:
        head = source.read(16)
    suffix = Path(filename).suffix.lower()
    if head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8\xff'):
        if Path(path).stat().st_size > 8 * 1024 * 1024:
            return {"kind": "unsupported", "message": "Изображение больше 8 МиБ. Используйте скачивание."}
        mime = 'image/png' if head.startswith(b'\x89PNG') else 'image/jpeg'
        # Bound decoded image dimensions before passing bytes to the browser.
        if mime == 'image/png':
            with open(path, 'rb') as source:
                source.seek(16)
                width, height = struct.unpack('>II', source.read(8))
        else:
            width = height = 0
            with open(path, 'rb') as source:
                source.read(2)
                for _ in range(4096):
                    marker = source.read(1)
                    if marker != b'\xff':
                        break
                    while marker == b'\xff':
                        marker = source.read(1)
                    if not marker or marker in (b'\xda', b'\xd9'):
                        break
                    length = int.from_bytes(source.read(2), 'big')
                    if length < 2:
                        break
                    if marker[0] in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                        _, height, width = struct.unpack('>BHH', source.read(5))
                        break
                    source.seek(length - 2, 1)
        if not width or not height or width * height > 25_000_000:
            raise ValueError("Изображение повреждено или слишком велико")
        return {"kind": "image", "src": f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode(), "width": width, "height": height}
    if head.startswith(b'%PDF-'):
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as document:
            if not len(document):
                raise ValueError("В PDF нет страниц")
            page = document[0]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(value) and value > 0 for value in (width, height)):
                    raise ValueError("Некорректный размер страницы")
                scale = min(1200 / width, 1600 / height, 2)
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil()
                    try:
                        output = io.BytesIO()
                        image.save(output, format="PNG")
                        return {"kind": "image", "src": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
                                "width": image.width, "height": image.height,
                                "message": f"Страница 1 из {len(document)}", "format": "pdf"}
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
    if head.startswith(b'PK'):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError("В архиве больше 10 000 записей")
            names = set(archive.namelist())
            if suffix == '.docx' and 'word/document.xml' in names:
                root = xml_member(archive, 'word/document.xml')
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                blocks = []
                for paragraph in root.findall('.//w:body/w:p', ns):
                    text = ''.join(t.text or '' for t in paragraph.findall('.//w:t', ns))[:2000]
                    style = paragraph.find('w:pPr/w:pStyle', ns)
                    heading = style is not None and 'heading' in style.get('{%s}val' % ns['w'], '').lower()
                    listed = paragraph.find('w:pPr/w:numPr', ns) is not None
                    if text:
                        blocks.append({'text': text, 'style': 'heading' if heading else 'list' if listed else 'paragraph'})
                    if len(blocks) >= 60:
                        break
                return {"kind": "document", "blocks": blocks, "message": "Первые 60 абзацев; сложное форматирование опущено."}
            if suffix == '.xlsx' and 'xl/workbook.xml' in names:
                for info in infos:
                    if info.file_size > 16 * 1024 * 1024 or info.file_size > max(info.compress_size, 1) * 200:
                        raise ValueError("Таблица слишком сложная для предпросмотра")
                if sum(info.file_size for info in infos) > 64 * 1024 * 1024:
                    raise ValueError("Таблица слишком большая для предпросмотра")
                from openpyxl import load_workbook
                book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
                try:
                    sheet = book.worksheets[0]
                    rows = [[str(value)[:500] if value is not None else '' for value in row]
                            for row in sheet.iter_rows(min_row=1, max_row=20, max_col=10, values_only=True)]
                    return {"kind": "table", "rows": rows, "sheet": sheet.title, "message": "Первые 20 строк и 10 столбцов. Формулы не вычисляются."}
                finally:
                    book.close()
            return {"kind": "archive", "entries": [entry(i.filename, i.file_size, i.is_dir()) for i in infos[offset:offset + 100]], "total": len(infos), "offset": offset}
    if head.startswith(b'Rar!\x1a\x07'):
        import rarfile
        with rarfile.RarFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError("В архиве больше 10 000 записей")
            return {"kind": "archive", "entries": [entry(i.filename, i.file_size, i.isdir()) for i in infos[offset:offset + 100]], "total": len(infos), "offset": offset}
    if head.startswith(b'\x1f\x8b\x08'):
        # GZIP is a stream, not a directory. Never inflate it just for a listing.
        with open(path, 'rb') as source:
            header = source.read(10)
            flags = header[3]
            if flags & 0xe0:
                raise ValueError("Повреждённый заголовок GZIP")
            if flags & 4:
                extra = int.from_bytes(source.read(2), 'little')
                source.seek(extra, 1)
            name = bytearray()
            if flags & 8:
                for _ in range(1024):
                    char = source.read(1)
                    if not char:
                        raise ValueError("Повреждённый заголовок GZIP")
                    if char == b'\0':
                        break
                    name.extend(char)
                else:
                    raise ValueError("Слишком длинное имя GZIP")
        return {"kind": "archive", "entries": [entry(name.decode('latin-1') if name else Path(filename).stem, None)], "total": 1, "offset": 0, "message": "GZIP содержит сжатый поток. Размер и вложенный TAR без распаковки не определяются."}
    if head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') and suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(path, on_demand=True)
        try:
            sheet = book.sheet_by_index(0)
            return {"kind": "table", "rows": [[str(sheet.cell_value(r, c))[:500] for c in range(min(sheet.ncols, 10))] for r in range(min(sheet.nrows, 20))], "sheet": sheet.name, "message": "Первые 20 строк и 10 столбцов."}
        finally:
            book.release_resources()
    return {"kind": "unsupported", "message": "Предпросмотр этого формата (включая DOC) недоступен. Файл можно скачать."}


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    # Linux supports an address-space ceiling; macOS does not reliably do so.
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    try:
        print(json.dumps(extract(sys.argv[1], sys.argv[2], int(sys.argv[3]))))
    except Exception:
        print(json.dumps({"kind": "error", "message": "Файл повреждён, защищён паролем или превышает ограничения предпросмотра."}))
