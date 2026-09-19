"""XLSX/XLS catalog import: staging, parsing, validation, execution (P4-10-01).

Scope: ``.xlsx`` + ``.xls`` (legacy Excel 97-2003), basic mapping, simple
validation. Bad rows are skipped with per-row errors — they never abort
the whole import. Idempotency via natural keys (``contract_number`` is
UNIQUE; licenses match on ``(university, product, license_number)``;
directions on ``code``; programs on ``(direction_id, name)``).

``execute_import`` runs synchronously in the MVP; the router wraps it into
the ``task_queue`` stub so the API shape (``job_id`` + job status) already
matches the background-worker design from P4-06-01.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.models.interactions import UniversityProgram

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
PREVIEW_ROWS = 10
STAGING_DIR = os.getenv("IMPORT_STAGING_DIR", "/tmp/rtk-imports")

ALLOWED_EXTS = frozenset({".xlsx", ".xls"})

#: file column -> model field paths accepted in ``mapping`` (P4-10-01 §2).
TARGET_FIELDS = frozenset({
    "university.name",
    "vendor.name",
    "product.name",
    "product.version",
    "direction.code",
    "direction.name",
    "program.name",
    "program.description",
    "contract.contract_number",
    "license.signed_at",
    "license.expires_at",
    "license.transfer_status",
    "license.comment",
    "responsible.full_name",
    "university_responsibles",
})

TRANSFER_STATUSES = frozenset({"pending", "transferred", "accepted", "rejected"})

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")


class ImportValidationError(ValueError):
    """Single-row validation failure (message is user-facing)."""


def parse_date(value: Any, field: str) -> date | None:
    """Coerce an openpyxl/xlrd cell value to ``date`` (``None`` for empty).

    Accepts datetime/date, full date strings (several formats) and a plain
    year (``"2027"`` / ``2027`` / ``2027.0``) — year maps to Dec 31 of that
    year, as the spec column is "Срок действия лицензии (год)".
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # xlrd may give years as float (2027.0); Excel dates as float are
        # already converted by the .xls reader, so here float == year.
        if float(value).is_integer() and 1900 <= int(value) <= 2100:
            return date(int(value), 12, 31)
        raise ImportValidationError(f"Неверный формат даты в поле '{field}': {value!r}")
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"(19|20)\d{2}", text):
            return date(int(text), 12, 31)
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ImportValidationError(f"Неверный формат даты в поле '{field}': {value!r}")


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


# ------------------------------------------------------------------ staging


def stage_upload(filename: str, content: bytes) -> str:
    """Validate + persist an uploaded workbook, return its ``file_id``."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ImportValidationError(
            f"Поддерживается только .xlsx/.xls, получено: {filename!r}"
        )
    if len(content) > MAX_FILE_BYTES:
        raise ImportValidationError(
            f"Файл больше лимита {MAX_FILE_BYTES // 1024 // 1024} МБ"
        )
    if not content:
        raise ImportValidationError("Пустой файл")
    os.makedirs(STAGING_DIR, exist_ok=True)
    file_id = uuid.uuid4().hex
    with open(os.path.join(STAGING_DIR, f"{file_id}{ext}"), "wb") as fh:
        fh.write(content)
    return file_id


def _staged_path(file_id: str) -> str:
    # New layout: <STAGING_DIR>/<file_id>.<ext>. Legacy (MVP) layout stored
    # everything as <file_id>.xlsx — keep reading it for backward compat.
    candidates = [
        os.path.join(STAGING_DIR, f"{file_id}{ext}") for ext in (".xlsx", ".xls")
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # file_id may already include extension (defensive, not part of API).
    direct = os.path.join(STAGING_DIR, file_id)
    if os.path.exists(direct):
        return direct
    raise ImportValidationError(f"Файл {file_id} не найден (загрузите заново)")


def _read_xlsx(path: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ImportValidationError("В книге нет листов")
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ImportValidationError("Пустой лист")
    headers = [_cell_text(c) or f"col_{i}" for i, c in enumerate(rows[0])]
    data = [dict(zip(headers, r)) for r in rows[1:]]
    if len(data) > MAX_ROWS:
        raise ImportValidationError(f"Больше лимита {MAX_ROWS} строк")
    return ws.title or "Sheet1", headers, data


def _read_xls(path: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Read legacy Excel 97-2003 (.xls) via xlrd. Same shape as _read_xlsx."""
    import xlrd

    try:
        book = xlrd.open_workbook(path, logfile=open(os.devnull, "w"))
    except Exception as exc:
        raise ImportValidationError(f"Не удалось прочитать .xls: {exc}") from exc
    if book.nsheets == 0:
        raise ImportValidationError("В книге нет листов")
    sh = book.sheet_by_index(0)
    if sh.nrows == 0:
        raise ImportValidationError("Пустой лист")
    headers = [_cell_text(sh.cell_value(0, c)) or f"col_{c}" for c in range(sh.ncols)]
    data: list[dict[str, Any]] = []
    for r in range(1, sh.nrows):
        row: dict[str, Any] = {}
        for c in range(sh.ncols):
            ctype = sh.cell_type(r, c)
            cval = sh.cell_value(r, c)
            if ctype == xlrd.XL_CELL_DATE:
                try:
                    cval = xlrd.xldate_as_datetime(cval, book.datemode).date()
                except Exception:
                    pass
            elif ctype == xlrd.XL_CELL_EMPTY or ctype == xlrd.XL_CELL_BLANK:
                cval = None
            row[headers[c]] = cval
        data.append(row)
    if len(data) > MAX_ROWS:
        raise ImportValidationError(f"Больше лимита {MAX_ROWS} строк")
    return sh.name or "Sheet1", headers, data


def read_sheet(file_id: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Return ``(sheet_name, headers, data_rows)`` for a staged workbook."""
    path = _staged_path(file_id)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        return _read_xls(path)
    return _read_xlsx(path)


def parse_preview(file_id: str) -> dict[str, Any]:
    sheet, headers, data = read_sheet(file_id)
    return {
        "headers": headers,
        "preview": [{k: _cell_text(v) or None for k, v in row.items()}
                    for row in data[:PREVIEW_ROWS]],
        "row_count": len(data),
        "detected_sheet": sheet,
    }


# ------------------------------------------------------------------ lookups


def _get_or_create(session: Session, model, defaults: dict, **key):
    obj = session.execute(select(model).filter_by(**key)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**{**key, **defaults})
    session.add(obj)
    session.flush()
    return obj, True


def find_university(session: Session, name: str) -> University | None:
    """Exact match first, then case-insensitive fuzzy (spec: exact/fuzzy)."""
    uni = session.execute(select(University).filter_by(name=name)).scalar_one_or_none()
    if uni is not None:
        return uni
    return session.execute(
        select(University).filter(University.name.ilike(f"%{name}%"))
    ).scalar_one_or_none()


def find_or_create_responsible(
    session: Session, full_name: str, role: str
) -> Responsible:
    existing = session.execute(
        select(Responsible).filter_by(full_name=full_name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    # email is UNIQUE NOT NULL — stable synthetic value for import-created rows.
    email = f"import-{uuid.uuid4().hex[:8]}@example.local"
    resp = Responsible(full_name=full_name, email=email, role=role)
    session.add(resp)
    session.flush()
    return resp


def link_responsible(
    session: Session, university_id, responsible_id, role_in_university: str,
    is_primary: bool = False,
) -> None:
    exists = session.execute(
        select(UniversityResponsible).filter_by(
            university_id=university_id, responsible_id=responsible_id
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(UniversityResponsible(
            university_id=university_id, responsible_id=responsible_id,
            role_in_university=role_in_university, is_primary=is_primary,
        ))
        session.flush()


def _slug_code(name: str) -> str:
    """Fallback code for a direction when only ``direction.name`` is mapped."""
    slug = re.sub(r"\s+", "_", name.strip().lower())
    slug = re.sub(r"[^\w\-]", "", slug, flags=re.UNICODE)[:64]
    return slug or f"dir-{uuid.uuid4().hex[:8]}"


def find_or_create_direction(
    session: Session, code: str, name: str | None
) -> ITDirection:
    existing = session.execute(
        select(ITDirection).filter_by(code=code)
    ).scalar_one_or_none()
    if existing is not None:
        if name and existing.name != name:
            existing.name = name
            session.flush()
        return existing
    direction = ITDirection(code=code, name=name or code)
    session.add(direction)
    session.flush()
    return direction


def find_or_create_program(
    session: Session, direction: ITDirection, name: str, description: str | None
) -> ITProgram:
    existing = session.execute(
        select(ITProgram).filter_by(direction_id=direction.id, name=name)
    ).scalar_one_or_none()
    if existing is not None:
        if description is not None and existing.description != description:
            existing.description = description
            session.flush()
        return existing
    program = ITProgram(
        direction_id=direction.id, name=name, description=description or ""
    )
    session.add(program)
    session.flush()
    return program


def link_university_program(
    session: Session, university_id, program_id
) -> None:
    """Bind university <-> program (uq pair, idempotent, never deleted)."""
    exists = session.execute(
        select(UniversityProgram).filter_by(
            university_id=university_id, program_id=program_id
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(UniversityProgram(
            university_id=university_id, program_id=program_id, status="active",
        ))
        session.flush()


# ------------------------------------------------------------------ row apply


def _mapped(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Project a file row onto target fields via the mapping."""
    return {target: row.get(col) for col, target in mapping.items() if col in row}


def apply_row(
    session: Session, mapped: dict[str, Any], update_existing: bool
) -> str:
    """Apply one mapped row. Returns ``inserted`` / ``updated`` / ``skipped``.

    Raises :class:`ImportValidationError` for bad rows (caller records it
    and continues with the next row).
    """
    uni_name = _cell_text(mapped.get("university.name"))
    if not uni_name:
        raise ImportValidationError("Поле 'university.name' обязательно")
    uni = find_university(session, uni_name)
    if uni is None:
        uni = University(name=uni_name, city=None)
        session.add(uni)
        session.flush()

    contract_no = _cell_text(mapped.get("contract.contract_number"))
    if not contract_no:
        raise ImportValidationError("Поле 'contract.contract_number' обязательно")

    product_name = _cell_text(mapped.get("product.name"))
    product = None
    if product_name:
        vendor_name = _cell_text(mapped.get("vendor.name"))
        if not vendor_name:
            raise ImportValidationError(
                "Поле 'vendor.name' обязательно, если указан продукт"
            )
        vendor, _ = _get_or_create(session, Vendor, {}, name=vendor_name)
        version = _cell_text(mapped.get("product.version"))
        product, _ = _get_or_create(
            session, ITProduct, {"vendor_id": vendor.id},
            vendor_id=vendor.id, name=product_name, version=version,
        )

    # ИТ-направление — отдельное поле файла (опционально).
    # Направление строки хранится прямо в лицензии (direction_id).
    # it_programs — зона workflow: программа и связь вуз↔программа
    # создаются только если в файле есть колонка программы.
    direction_code = _cell_text(mapped.get("direction.code"))
    direction_name = _cell_text(mapped.get("direction.name"))
    program_name = _cell_text(mapped.get("program.name"))
    program_desc_raw = mapped.get("program.description")
    program_desc = _cell_text(program_desc_raw) or None
    row_program = None
    row_direction = None
    if direction_code or direction_name or program_name:
        if not direction_code and direction_name:
            direction_code = _slug_code(direction_name)
        if not direction_code:
            raise ImportValidationError(
                "Поле 'direction.code' обязательно, если указаны направление/программа"
                " (или замаппьте 'direction.name' для автогенерации кода)"
            )
        row_direction = find_or_create_direction(
            session, direction_code, direction_name or None
        )
        if program_name:
            row_program = find_or_create_program(
                session, row_direction, program_name, program_desc
            )
            link_university_program(session, uni.id, row_program.id)

    signed_at = parse_date(mapped.get("license.signed_at"), "license.signed_at")
    expires_at = parse_date(mapped.get("license.expires_at"), "license.expires_at")
    if expires_at is None:
        raise ImportValidationError("Поле 'license.expires_at' обязательно")
    transfer = _cell_text(mapped.get("license.transfer_status")) or "pending"
    if transfer not in TRANSFER_STATUSES:
        raise ImportValidationError(
            f"Недопустимый transfer_status {transfer!r} "
            f"(pending/transferred/accepted/rejected)"
        )
    comment_raw = mapped.get("license.comment")
    comment = _cell_text(comment_raw) or None

    contract = session.execute(
        select(Contract).filter_by(contract_number=contract_no)
    ).scalar_one_or_none()
    if contract is None:
        contract = Contract(
            university_id=uni.id, contract_number=contract_no,
            product_id=product.id if product else None,
            signed_at=signed_at or date.today(), expires_at=expires_at,
            status_raw="signed", transfer_status_raw="accepted", comment=comment,
        )
        session.add(contract)
        session.flush()
        contract_created = True
    elif update_existing:
        contract.signed_at = signed_at or contract.signed_at
        contract.expires_at = expires_at
        if product is not None:
            contract.product_id = product.id
        contract.comment = comment
        session.flush()
        contract_created = False
    else:
        return "skipped"

    license_number = contract_no
    lic = None
    if product is not None:
        lic = session.execute(
            select(License).filter_by(
                university_id=uni.id, product_id=product.id,
                license_number=license_number,
            )
        ).scalar_one_or_none()
    if lic is None:
        if product is None:
            raise ImportValidationError(
                "Строка без продукта: не к чему привязать лицензию"
            )
        session.add(License(
            university_id=uni.id, product_id=product.id, contract_id=contract.id,
            program_id=row_program.id if row_program else None,
            direction_id=row_direction.id if row_direction else None,
            license_number=license_number, signed_at=signed_at or date.today(),
            expires_at=expires_at, transfer_status_raw=transfer, comment=comment,
        ))
        session.flush()
        lic_created = True
    elif update_existing:
        lic.expires_at = expires_at
        lic.signed_at = signed_at or lic.signed_at
        lic.transfer_status_raw = transfer
        lic.contract_id = contract.id
        if row_program is not None:
            lic.program_id = row_program.id
        if row_direction is not None:
            lic.direction_id = row_direction.id
        lic.comment = comment
        session.flush()
        lic_created = False
    else:
        return "skipped"

    manager_name = _cell_text(mapped.get("responsible.full_name"))
    if manager_name:
        manager = find_or_create_responsible(session, manager_name, "our_manager")
        link_responsible(session, uni.id, manager.id, "our_manager")

    contacts_raw = _cell_text(mapped.get("university_responsibles"))
    if contacts_raw:
        for part in contacts_raw.replace(",", ";").split(";"):
            name = part.strip()
            if not name:
                continue
            contact = find_or_create_responsible(session, name, "university_contact")
            link_responsible(session, uni.id, contact.id, "university_contact")

    if contract_created or lic_created:
        return "inserted"
    return "updated"


def execute_import(
    session: Session,
    file_id: str,
    mapping: dict[str, str],
    update_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the import over all staged rows. Bad rows are collected, never fatal."""
    unknown = sorted(set(mapping.values()) - TARGET_FIELDS)
    if unknown:
        raise ImportValidationError(
            f"Неизвестные поля маппинга: {', '.join(unknown)}"
        )
    if "university.name" not in mapping.values():
        raise ImportValidationError("Маппинг должен содержать university.name")
    if "contract.contract_number" not in mapping.values():
        raise ImportValidationError(
            "Маппинг должен содержать contract.contract_number"
        )

    _, _, data = read_sheet(file_id)
    summary: dict[str, Any] = {
        "total_rows": len(data), "inserted": 0, "updated": 0,
        "skipped": 0, "errors": [], "dry_run": dry_run,
    }
    try:
        for idx, row in enumerate(data, start=2):  # 1-based incl. header
            if all(v is None or _cell_text(v) == "" for v in row.values()):
                summary["skipped"] += 1
                continue
            try:
                outcome = apply_row(session, _mapped(row, mapping), update_existing)
                summary[outcome] += 1
            except ImportValidationError as exc:
                field = "row"
                msg = str(exc)
                if "Поле '" in msg:
                    field = msg.split("Поле '")[1].split("'")[0]
                summary["errors"].append(
                    {"row": idx, "field": field, "error": msg}
                )
                if len(summary["errors"]) >= 100:
                    break
        if dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    return summary


__all__ = [
    "ALLOWED_EXTS",
    "ImportValidationError",
    "TARGET_FIELDS",
    "apply_row",
    "execute_import",
    "find_or_create_direction",
    "find_or_create_program",
    "find_university",
    "parse_date",
    "parse_preview",
    "read_sheet",
    "stage_upload",
]
