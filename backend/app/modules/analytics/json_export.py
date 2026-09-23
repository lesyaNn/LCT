"""P4-05-01 JSON report export (production exporter, no SQL inside).

Data comes ONLY from :class:`ReportDatasetService` (same filters, same row
grain, same selected columns, same values as the dataset). There is no
second ``JSON_COLUMN_MAPPING``: every item contains exactly the resolved
output keys in ``ReportRequest.columns`` order (``None`` = all 14
mandatory columns); internal keys (``_university_id`` / ``_license_id``)
are never emitted.

Frozen export shape::

    {
      "generated_at": "<tz-aware ISO8601>",
      "filters": {<8 UnifiedFilter fields, raw serialized>},
      "columns": ["university", ...],
      "total": 123,
      "items": [{"university": "...", "health_score": 85}, ...]
    }

Top-level key order is stable (insertion order above); items preserve the
selected-column order. Typed serialization: UUID -> string, date ->
``YYYY-MM-DD``, datetime -> ISO8601 with timezone, numbers stay numbers,
``None`` -> ``null``. Files are written UTF-8 with ``ensure_ascii=False``
so Russian text stays readable; a ``JSONResponse`` round-trip re-escapes
per the JSON standard but preserves every character.

Memory model (honest): rows stream from the database one by one via
:meth:`ReportDatasetService.iterate_rows` (bounded DB access, never
``.all()``) into a sibling temp items file; the final document is then
assembled by concatenation (header + items + footer) — the dataset is
never materialized twice. For very large exports the future P4-06-01 job
layer owns limits/retries; this exporter documents that contract instead
of silently truncating.

Output is written to ``<final>.part`` first and atomically replaced to
the final ``.json`` only after a successful write; on failure all temp
files are removed and no partial file is left behind.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.modules.analytics.columns import resolve_columns
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import GeneratedReport

__all__ = [
    "JSON_FROZEN_KEYS",
    "default_reports_dir",
    "generate_json_report",
    "serialize_json_value",
]

#: Frozen top-level key order of the export document.
JSON_FROZEN_KEYS: tuple[str, ...] = (
    "generated_at",
    "filters",
    "columns",
    "total",
    "items",
)


def default_reports_dir() -> Path:
    """Configurable reports storage root (never the public static root)."""
    return Path(os.getenv("REPORTS_DIR", "/app/reports"))


def serialize_json_value(value: Any) -> Any:
    """Typed scalar serialization for one dataset value.

    UUID -> string, date -> ``YYYY-MM-DD``, datetime -> ISO8601 (naive
    assumed UTC, never silently dropped), Enum -> its value, numbers and
    ``None`` pass through unchanged (health score stays numeric).
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        moment = value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value"):  # frozen API enums (workflow statuses, ...)
        return serialize_json_value(value.value)
    return str(value)


def _ensure_tz_aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def generate_json_report(
    db: Session,
    filters: UnifiedFilter,
    columns: list[str] | tuple[str, ...] | None,
    output_path: str | Path,
    *,
    user: Any | None = None,
    generated_at: datetime | None = None,
    batch_size: int = 1000,
) -> GeneratedReport:
    """Generate the frozen JSON export from the report dataset.

    ``columns=None`` selects the frozen 14 mandatory ``DEFAULT_COLUMNS``;
    otherwise the resolved/deduped ``ReportRequest.columns`` order is kept
    verbatim (never sorted). Raises ``UnknownReportColumnError`` /
    ``EmptyReportColumnsError`` (both ``ValueError``) for invalid
    selections — the future P4-03-01 endpoint maps them to 422.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    resolved = resolve_columns(columns)
    moment = _ensure_tz_aware(generated_at)

    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(final_path.name + ".part")
    items_path = final_path.with_name(final_path.name + ".items.part")

    row_count = 0
    try:
        # Phase 1: stream dataset rows (bounded) into the items temp file
        # as pre-serialized JSON lines — one query pass, no double
        # materialization of the dataset.
        with open(items_path, "w", encoding="utf-8") as items_file:
            for row in ReportDatasetService.iterate_rows(
                db, filters, resolved, user=user, batch_size=batch_size
            ):
                ordered = {key: serialize_json_value(row.get(key)) for key in resolved}
                if row_count:
                    items_file.write(",\n")
                items_file.write("    " + json.dumps(ordered, ensure_ascii=False))
                row_count += 1

        # Phase 2: assemble the frozen document (stable top-level order).
        header = {
            "generated_at": moment.isoformat(),
            "filters": json.loads(filters.model_dump_json()),
            "columns": list(resolved),
            "total": row_count,
        }
        with open(tmp_path, "w", encoding="utf-8") as out:
            out.write("{\n")
            out.write(f'  "generated_at": {json.dumps(header["generated_at"])}')
            out.write(f',\n  "filters": {json.dumps(header["filters"], ensure_ascii=False)}')
            out.write(f',\n  "columns": {json.dumps(header["columns"], ensure_ascii=False)}')
            out.write(f',\n  "total": {row_count},\n  "items": [')
            if row_count:
                out.write("\n")
                with open(items_path, encoding="utf-8") as items_file:
                    for chunk in iter(lambda: items_file.read(65536), ""):
                        out.write(chunk)
                out.write("\n")
            out.write("]\n}\n")
        tmp_path.replace(final_path)
    except Exception:
        for candidate in (tmp_path, items_path):
            try:
                if candidate.exists():
                    candidate.unlink()
            except OSError:
                pass
        raise
    finally:
        try:
            if items_path.exists():
                items_path.unlink()
        except OSError:
            pass

    return GeneratedReport(
        path=final_path,
        size_bytes=final_path.stat().st_size,
        row_count=row_count,
        generated_at=moment,
        columns=resolved,
    )
