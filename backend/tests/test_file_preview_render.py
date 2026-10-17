"""Exercise the isolated renderer, including first-page selection and invalid PDFs.

Run with: python -m unittest discover -s tests -p test_file_preview_render.py
"""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pdfencrypt import StandardEncryption

from app.modules.workflow_attachments import preview_worker


class PdfPreviewTests(unittest.TestCase):
    def render(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'document.pdf'
            path.write_bytes(content)
            result = subprocess.run(
                [sys.executable, preview_worker.__file__, str(path), path.name, '0'],
                check=True, timeout=6, capture_output=True,
            )
            return json.loads(result.stdout)

    def document(self, *, encrypted=False, size=(600, 800)):
        stream = io.BytesIO()
        canvas = Canvas(stream, pagesize=size,
                        encrypt=StandardEncryption('secret') if encrypted else None)
        for color in ('red', 'blue'):
            canvas.setFillColor(color)
            canvas.rect(0, 0, *size, fill=1, stroke=0)
            canvas.showPage()
        canvas.save()
        return stream.getvalue()

    def test_only_first_page_is_rendered_as_safe_png(self):
        result = self.render(self.document())
        self.assertEqual(result['kind'], 'image')
        self.assertEqual(result['format'], 'pdf')
        self.assertEqual(result['message'], 'Страница 1 из 2')
        self.assertLessEqual(result['width'], 1200)
        self.assertLessEqual(result['height'], 1600)
        self.assertTrue(result['src'].startswith('data:image/png;base64,'))
        with Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))) as image:
            self.assertEqual(image.convert('RGB').getpixel((image.width // 2, image.height // 2)), (255, 0, 0))

    def test_corrupted_pdf_has_controlled_error(self):
        self.assertEqual(self.render(b'%PDF-1.4\ncorrupted')['kind'], 'error')

    def test_encrypted_pdf_has_controlled_error(self):
        self.assertEqual(self.render(self.document(encrypted=True))['kind'], 'error')

    def test_large_page_has_bounded_bitmap(self):
        result = self.render(self.document(size=(10000, 20000)))
        self.assertEqual(result['kind'], 'image')
        self.assertLessEqual(result['width'], 1200)
        self.assertLessEqual(result['height'], 1600)


if __name__ == '__main__':
    unittest.main()
