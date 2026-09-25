"""Render the checked-in ArchiMate context as a presentation PNG."""

from __future__ import annotations

import math
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "architecture.archimate"
OUTPUT = ROOT / "architecture.png"
NS = {"a": "http://www.opengroup.org/xsd/archimate/3.1/"}

BOXES = {
    "user": (75, 120, 320, 250),
    "fe": (420, 120, 665, 250),
    "be": (765, 120, 1010, 250),
    "db": (1160, 120, 1455, 250),
    "kc": (420, 405, 665, 535),
    "redis": (765, 405, 1010, 535),
    "worker": (1160, 405, 1455, 535),
    "storage": (765, 690, 1010, 820),
}
LABELS = {
    "user": "Users / Managers\n/ Admins",
    "fe": "Frontend\nReact SPA + nginx",
    "be": "Backend API\nFastAPI",
    "db": "PostgreSQL 16\napplication +\nKeycloak DBs",
    "kc": "Keycloak 26\nOIDC / JWT",
    "redis": "Redis 7\ncache",
    "worker": "Worker\nreports / imports\n/ audit relay",
    "storage": "Storage\nlocal volumes\n/ S3 seam",
}
COLORS = {
    "user": "#e0e7ff",
    "fe": "#dbeafe",
    "be": "#c7d2fe",
    "db": "#dcfce7",
    "kc": "#fef3c7",
    "redis": "#fee2e2",
    "worker": "#d1fae5",
    "storage": "#f3e8ff",
}
EDGES = [
    ("user", "fe"),
    ("fe", "be"),
    ("be", "db"),
    ("be", "kc"),
    ("be", "redis"),
    ("be", "worker"),
    ("worker", "db"),
    ("be", "storage"),
]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def boundary(box: tuple[int, int, int, int], toward: tuple[float, float]) -> tuple[float, float]:
    cx, cy = center(box)
    dx, dy = toward[0] - cx, toward[1] - cy
    half_width = (box[2] - box[0]) / 2
    half_height = (box[3] - box[1]) / 2
    scale = min(half_width / abs(dx) if dx else float("inf"), half_height / abs(dy) if dy else float("inf"))
    return (cx + dx * scale, cy + dy * scale)


def main() -> None:
    root = ElementTree.parse(MODEL).getroot()
    ids = {element.attrib["identifier"] for element in root.findall("a:elements/a:element", NS)}
    assert ids == set(BOXES) == set(LABELS)

    image = Image.new("RGB", (1530, 890), "#f8fafc")
    draw = ImageDraw.Draw(image)
    draw.text((75, 35), "RTK EdTech CRM — architecture context", fill="#0f172a", font=font(32))
    draw.text((77, 78), "ArchiMate model: architecture.archimate", fill="#475569", font=font(19))

    for source, target in EDGES:
        start = boundary(BOXES[source], center(BOXES[target]))
        end = boundary(BOXES[target], center(BOXES[source]))
        draw.line((start, end), fill="#475569", width=4)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        size = 15
        left = (end[0] - size * math.cos(angle - 0.55), end[1] - size * math.sin(angle - 0.55))
        right = (end[0] - size * math.cos(angle + 0.55), end[1] - size * math.sin(angle + 0.55))
        draw.polygon((end, left, right), fill="#475569")

    for identifier, box in BOXES.items():
        draw.rounded_rectangle(box, radius=18, fill=COLORS[identifier], outline="#334155", width=3)
        draw.multiline_text(center(box), LABELS[identifier], anchor="mm", align="center", spacing=8,
                            fill="#0f172a", font=font(21))

    image.save(OUTPUT, optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
