"""Shared spreadsheet cell semantics for the tabular report exporters.

XLS (BIFF8, :mod:`app.modules.analytics.xls`) and XLSX (OOXML,
:mod:`app.modules.analytics.xlsx`) render the SAME report dataset through
two very different libraries, but a cell must mean the same thing in both:

* a missing value is an EMPTY cell — never ``"N/A"``/``"null"``/``"-"``;
* ``date``/``datetime`` are real date cells with a ``DD.MM.YYYY`` display
  format, not localized strings;
* ``int``/``float`` stay numeric, so the spreadsheet can sum them;
* text is formula-injection sanitized.

Implementing those rules twice is how the exporters drift, so they live here
once and both writers consume :func:`classify_cell`. Presentation-only
styling (fonts, fills, borders, widths) stays inside each writer, because
the two formats have no shared styling API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

__all__ = [
    "DATE_NUMBER_FORMAT",
    "CellKind",
    "CellValue",
    "Cell",
    "FORMULA_PREFIXES",
    "classify_cell",
    "estimate_width",
]

#: Russian short-date display format shared by both writers.
DATE_NUMBER_FORMAT = "DD.MM.YYYY"

#: Cell text prefixes a spreadsheet app may evaluate instead of displaying.
#: A leading apostrophe keeps the value plain text; Excel hides the marker.
FORMULA_PREFIXES = ("=", "+", "-", "@")

#: Display-width estimate per cell kind, used to auto-size columns. Bounded
#: so one pathological value cannot make an unreadable 5000-wide column.
_MAX_ESTIMATE = 50

CellKind = Literal["empty", "text", "number", "date", "datetime"]


@dataclass(frozen=True)
class CellValue:
    """One normalized cell: what to write and how wide it renders."""

    kind: CellKind
    value: Any = None


def classify_cell(value: Any) -> CellValue:
    """Map a dataset value to its spreadsheet representation.

    The branch order is the contract: ``bool`` before ``int`` (a bool is an
    ``int`` subclass and must not become ``True``/``False`` text), numeric
    before ``date`` (dates are never formatted as numbers), and ``None`` is
    always ``empty`` regardless of the other branches.
    """
    if value is None:
        return CellValue("empty")
    if isinstance(value, bool):
        # Booleans render as 1/0, matching the existing XLSX behaviour.
        return CellValue("number", int(value))
    if isinstance(value, datetime):
        return CellValue("datetime", value)
    if isinstance(value, date):
        return CellValue("date", value)
    if isinstance(value, (int, float)):
        return CellValue("number", value)
    return CellValue("text", _sanitize(str(value)))


def _sanitize(text: str) -> str:
    """Escape formula-injection prefixes in user-controlled text."""
    if text[:1] in FORMULA_PREFIXES:
        return "'" + text
    return text


def estimate_width(cell: CellValue) -> int:
    """Approximate rendered width of a cell, for column auto-sizing."""
    if cell.kind == "empty":
        return 0
    if cell.kind == "datetime":
        return 16
    if cell.kind == "date":
        return 10
    if cell.kind == "number":
        return len(str(cell.value))
    return min(len(cell.value), _MAX_ESTIMATE)


# Backwards-compatible alias for call sites that predate the rename.
Cell = CellValue
