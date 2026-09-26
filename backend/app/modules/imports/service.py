"""Import v2: whole-file staging, single-sheet preview/execute (fixed structures).

Each workbook sheet has a fixed column contract and a dedicated handler
below; the client never sends a column mapping. Natural keys make every
handler idempotent (re-runs only fill gaps, ``update_existing`` refreshes
changed fields). Bad rows are collected into per-row errors and never
abort the whole sheet; structural problems (unknown sheet, missing
required header) fail the job loudly with a clear message.

Conventions (match the SQL-migration universe):
* UUID PKs are client-generated (``uuid4``); the DB never defaults them.
* ``license_number`` reuses ``contract_number`` (the file has no separate
  license number); one contract number may span several products, so
  ``contracts.product_id`` stays ``NULL`` (framework contract) and each
  (university, product) pair gets its own license row.
* ``contracts.expires_at`` stays ``NULL`` (the file carries no contract
  expiry); license ``signed_at``/``expires_at`` come from the
  Подписание/Окончание columns (there is no license start column).
* Transfer statuses are normalized from RU labels to the canonical set
  {pending, transferred, accepted, rejected}; unknown labels are row errors.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    ProductDirection,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
PREVIEW_ROWS = 10
MAX_ROW_ERRORS = 100
STAGING_DIR = os.getenv("IMPORT_STAGING_DIR", "/tmp/rtk-imports")
ALLOWED_EXTS = frozenset({".xlsx", ".xls"})

_FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")

#: RU transfer labels -> canonical transfer_status_raw.
TRANSFER_STATUS_MAP = {
    "действует": "accepted",
    "действующий": "accepted",
    "передан": "accepted",
    "передано": "accepted",
    "принят": "accepted",
    "принято": "accepted",
    "в работе": "pending",
    "ожидает": "pending",
    "передан в работу": "pending",
    "отклонен": "rejected",
    "отклонено": "rejected",
}


class ImportValidationError(ValueError):
    """Job-level import failure (bad file structure, unknown sheet)."""

    def __init__(self, message: str, *, code: str = "IMPORT_VALIDATION_FAILED"):
        super().__init__(message)
        self.code = code


class RowError(ValueError):
    """Single-row failure (message is user-facing)."""

    def __init__(self, message: str, *, field: str = "row"):
        super().__init__(message)
        self.field = field


def normalize_header(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(
        text.lstrip("\ufeff").casefold().replace("ё", "е").replace("_", " ").replace("-", " ").strip().split()
    )


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _to_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise RowError(f"Неверная дата в поле '{field}': {_cell_text(value) or '—'}", field=field)


def _transfer_status(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "pending"
    if isinstance(value, str):
        mapped = TRANSFER_STATUS_MAP.get(value.strip().casefold().replace("ё", "е"))
        if mapped:
            return mapped
    raise RowError(
        f"Неизвестный статус '{_cell_text(value)}' (ожидается: Действует / Передан / В работе)",
        field="Статус",
    )


# ------------------------------------------------------------------ staging


def _staging_dir() -> Path:
    path = Path(STAGING_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _staged_path(file_id: str) -> Path:
    if not _FILE_ID_RE.match(file_id or ""):
        raise ImportValidationError("Некорректный file_id", code="INVALID_FORMAT")
    matches = sorted(_staging_dir().glob(f"{file_id}.*"))
    if not matches:
        raise ImportValidationError("Файл не найден. Загрузите его заново.", code="FILE_NOT_FOUND")
    return matches[0]


def stage_upload(filename: str, content: bytes) -> str:
    """Validate + persist an uploaded workbook, return its ``file_id``."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ImportValidationError(
            "Поддерживаются только файлы .xlsx и .xls", code="FILE_TYPE_NOT_ALLOWED"
        )
    if len(content) > MAX_FILE_BYTES:
        raise ImportValidationError("Файл больше лимита 10 МБ", code="FILE_TOO_LARGE")
    if not content:
        raise ImportValidationError("Файл пустой", code="INVALID_FORMAT")
    file_id = uuid.uuid4().hex
    dest = _staging_dir() / f"{file_id}{ext}"
    dest.write_bytes(content)
    # Fail fast on unreadable workbooks (wrong magic, password, garbage).
    _open_sheet(dest, None)
    return file_id


def _open_workbook(path: Path):  # type: ignore[no-untyped-def]
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        return openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        import xlrd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportValidationError(
            "Файлы .xls не поддерживаются этим стендом. Сохраните как .xlsx",
            code="FILE_TYPE_NOT_ALLOWED",
        ) from exc
    raise ImportValidationError("Не удалось прочитать .xls", code="INVALID_FORMAT")


def _open_sheet(path: Path, title: str | None) -> tuple[list[str], list[tuple[int, list[Any]]]]:
    """Return (headers, [(excel_row, values)]) for a sheet; skips empty rows."""
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except Exception as exc:
            raise ImportValidationError(
                "Не удалось прочитать XLSX (файл повреждён?)", code="INVALID_FORMAT"
            ) from exc
        try:
            names = wb.sheetnames
            if title is None:
                if not names:
                    raise ImportValidationError("В файле нет листов", code="INVALID_FORMAT")
                return names, []
            if title not in names:
                raise ImportValidationError(
                    f"Лист '{title}' не найден в файле", code="INVALID_FORMAT"
                )
            ws = wb[title]
            rows: list[tuple[int, list[Any]]] = []
            for r, raw in enumerate(ws.iter_rows(values_only=True), start=1):
                vals = list(raw or [])
                if any(v is not None and str(v).strip() != "" for v in vals):
                    rows.append((r, vals))
            if not rows:
                return [], []
            width = max(len(v) for _, v in rows)
            headers = [_cell_text(v) for v in (rows[0][1] + [None] * width)[:width]]
            return headers, [(r, (v + [None] * width)[:width]) for r, v in rows[1:]]
        finally:
            wb.close()
    raise ImportValidationError("Не удалось прочитать .xls", code="INVALID_FORMAT")


def list_sheets(file_id: str) -> list[dict[str, Any]]:
    path = _staged_path(file_id)
    names, _ = _open_sheet(path, None)
    out = []
    for name in names:  # type: ignore[union-attr]
        headers, rows = _open_sheet(path, name)
        out.append({"id": name, "label": name, "row_count": len(rows)})
    return out


def preview_sheet(file_id: str, sheet: str) -> dict[str, Any]:
    path = _staged_path(file_id)
    headers, rows = _open_sheet(path, sheet)
    preview = [
        {h or f"Колонка {i + 1}": _preview_value(v) for i, (h, v) in enumerate(zip(headers, vals))}
        for _, vals in rows[:PREVIEW_ROWS]
    ]
    return {"file_id": file_id, "sheet": sheet, "headers": headers, "preview": preview, "row_count": len(rows)}


def _preview_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value).strip()


# ------------------------------------------------------------------ handlers


def _require(headers: list[str], *names: str) -> dict[str, int]:
    normed = [normalize_header(h) for h in headers]
    missing = [n for n in names if n not in normed]
    if missing:
        raise ImportValidationError(
            f"В листе нет обязательных колонок: {', '.join(missing)}", code="INVALID_FORMAT"
        )
    return {n: normed.index(n) for n in names}


def _get(session: Session, model: Any, **key: Any) -> Any | None:
    return session.execute(select(model).filter_by(**key)).scalar_one_or_none()


class _SheetRun:
    """Per-sheet accumulator: inserted/updated/skipped + capped row errors."""

    def __init__(self, session: Session, *, update_existing: bool):
        self.session = session
        self.update_existing = update_existing
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.errors: list[dict[str, Any]] = []
        self.errors_total = 0

    def fail(self, excel_row: int, field: str, message: str) -> None:
        self.errors_total += 1
        if len(self.errors) < MAX_ROW_ERRORS:
            self.errors.append({"row": excel_row, "field": field, "error": message})

    def unchanged(self) -> None:
        self.skipped += 1


def _save(run: _SheetRun, obj: Any, changed: bool, created: bool) -> None:
    if created:
        run.session.add(obj)
        run.session.flush()
        run.inserted += 1
    elif changed and run.update_existing:
        run.session.flush()
        run.updated += 1
    else:
        run.unchanged()


def _touch(obj: Any, **fields: Any) -> bool:
    changed = False
    for key, value in fields.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed


def _handle_universities(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(headers, "название вуза", "город")
    for excel_row, vals in rows:
        try:
            name = _cell_text(vals[col["название вуза"]])
            if not name:
                raise RowError("Пустое название ВУЗа", field="Название ВУЗа")
            city = _cell_text(vals[col["город"]]) or None
            obj = _get(run.session, University, name=name)
            if obj is None:
                obj = University(name=name, city=city)
                _save(run, obj, True, True)
            else:
                _save(run, obj, _touch(obj, city=city), False)
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _vendor(run: _SheetRun, name: str, excel_row: int) -> Vendor:
    if not name:
        raise RowError("Пустой вендор", field="Вендор")
    obj = _get(run.session, Vendor, name=name)
    if obj is None:
        obj = Vendor(name=name)
        _save(run, obj, True, True)
    else:
        run.unchanged()
    return obj


def _handle_products(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(headers, "вендор", "ит продукт")
    for excel_row, vals in rows:
        try:
            vendor = _vendor(run, _cell_text(vals[col["вендор"]]), excel_row)
            name = _cell_text(vals[col["ит продукт"]])
            if not name:
                raise RowError("Пустое название продукта", field="ИТ-продукт")
            obj = _get(run.session, ITProduct, vendor_id=vendor.id, name=name, version="")
            if obj is None:
                obj = ITProduct(vendor_id=vendor.id, name=name, version="")
                _save(run, obj, True, True)
            else:
                run.unchanged()
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _handle_responsibles(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(headers, "вуз", "фио", "должность", "email", "телефон")
    for excel_row, vals in rows:
        try:
            uni_name = _cell_text(vals[col["вуз"]])
            uni = _get(run.session, University, name=uni_name)
            if uni is None:
                raise RowError(f"ВУЗ '{uni_name or '—'}' не найден", field="ВУЗ")
            full_name = _cell_text(vals[col["фио"]])
            email = _cell_text(vals[col["email"]])
            if not full_name:
                raise RowError("Пустое ФИО", field="ФИО")
            if not email:
                raise RowError("Пустой email (обязателен и уникален)", field="Email")
            phone = _cell_text(vals[col["телефон"]]) or None
            role = _cell_text(vals[col["должность"]])
            obj = _get(run.session, Responsible, email=email)
            if obj is None:
                obj = Responsible(full_name=full_name, email=email, phone=phone, role=role)
                _save(run, obj, True, True)
            else:
                _save(run, obj, _touch(obj, full_name=full_name, phone=phone, role=role), False)
            link = _get(run.session, UniversityResponsible, university_id=uni.id, responsible_id=obj.id)
            if link is None:
                has_primary = (
                    run.session.execute(
                        select(UniversityResponsible).filter_by(university_id=uni.id, is_primary=True)
                    ).scalar_one_or_none()
                    is not None
                )
                link = UniversityResponsible(
                    university_id=uni.id,
                    responsible_id=obj.id,
                    role_in_university="university_contact",
                    is_primary=not has_primary,
                )
                _save(run, link, True, True)
            else:
                run.unchanged()
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _resolve_product(run: _SheetRun, vendor_name: str, product_name: str) -> ITProduct:
    vendor = _get(run.session, Vendor, name=vendor_name)
    if vendor is None:
        raise RowError(f"Вендор '{vendor_name or '—'}' не найден", field="Вендор")
    if not product_name:
        raise RowError("Пустое название продукта", field="ИТ-продукт")
    obj = _get(run.session, ITProduct, vendor_id=vendor.id, name=product_name, version="")
    if obj is None:
        raise RowError(
            f"Продукт '{product_name}' вендора '{vendor_name}' не найден", field="ИТ-продукт"
        )
    return obj


def _handle_licenses(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(
        headers,
        "вуз",
        "вендор",
        "ит продукт",
        "номер договора",
        "дата договора",
        "подписание лицензии",
        "окончание действия лицензии",
        "статус",
    )
    for excel_row, vals in rows:
        try:
            uni_name = _cell_text(vals[col["вуз"]])
            uni = _get(run.session, University, name=uni_name)
            if uni is None:
                raise RowError(f"ВУЗ '{uni_name or '—'}' не найден", field="ВУЗ")
            product = _resolve_product(
                run, _cell_text(vals[col["вендор"]]), _cell_text(vals[col["ит продукт"]])
            )
            number = _cell_text(vals[col["номер договора"]])
            if not number:
                raise RowError("Пустой номер договора", field="Номер договора")
            signed_raw = vals[col["дата договора"]]
            lic_signed_raw = vals[col["подписание лицензии"]]
            lic_expires_raw = vals[col["окончание действия лицензии"]]
            if signed_raw is None or (isinstance(signed_raw, str) and not signed_raw.strip()):
                raise RowError("Пустая дата договора", field="Дата договора")
            contract = _get(run.session, Contract, contract_number=number)
            if contract is None:
                contract = Contract(
                    university_id=uni.id,
                    contract_number=number,
                    product_id=None,
                    signed_at=_to_date(signed_raw, "Дата договора"),
                    expires_at=None,
                    status_raw="signed",
                    transfer_status_raw=_transfer_status(vals[col["статус"]]),
                )
                _save(run, contract, True, True)
            else:
                run.unchanged()
            lic = _get(
                run.session,
                License,
                university_id=uni.id,
                product_id=product.id,
                license_number=number,
            )
            if lic is None:
                lic = License(
                    university_id=uni.id,
                    product_id=product.id,
                    contract_id=contract.id,
                    license_number=number,
                    signed_at=_to_date(lic_signed_raw, "Подписание лицензии"),
                    expires_at=_to_date(lic_expires_raw, "Окончание действия лицензии"),
                    transfer_status_raw=_transfer_status(vals[col["статус"]]),
                )
                _save(run, lic, True, True)
            else:
                _save(
                    run,
                    lic,
                    _touch(
                        lic,
                        contract_id=contract.id,
                        transfer_status_raw=_transfer_status(vals[col["статус"]]),
                    ),
                    False,
                )
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _handle_directions(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(headers, "код направления", "название направления")
    for excel_row, vals in rows:
        try:
            code = _cell_text(vals[col["код направления"]])
            name = _cell_text(vals[col["название направления"]])
            if not code:
                raise RowError("Пустой код направления", field="Код направления")
            if not name:
                raise RowError("Пустое название направления", field="Название направления")
            obj = _get(run.session, ITDirection, code=code)
            if obj is None:
                obj = ITDirection(code=code, name=name)
                _save(run, obj, True, True)
            else:
                _save(run, obj, _touch(obj, name=name), False)
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _resolve_direction(run: _SheetRun, name: str) -> ITDirection:
    if not name:
        raise RowError("Пустое направление", field="Направление")
    found = run.session.execute(select(ITDirection).filter_by(name=name)).scalars().all()
    if not found:
        raise RowError(f"Направление '{name}' не найдено", field="Направление")
    if len(found) > 1:
        raise RowError(
            f"Направление '{name}' неоднозначно — укажите код", field="Направление"
        )
    return found[0]


def _handle_programs(run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]) -> None:
    col = _require(headers, "название программы", "направление", "описание")
    for excel_row, vals in rows:
        try:
            name = _cell_text(vals[col["название программы"]])
            if not name:
                raise RowError("Пустое название программы", field="Название программы")
            direction = _resolve_direction(run, _cell_text(vals[col["направление"]]))
            description = _cell_text(vals[col["описание"]])
            obj = _get(run.session, ITProgram, direction_id=direction.id, name=name)
            if obj is None:
                obj = ITProgram(direction_id=direction.id, name=name, description=description)
                _save(run, obj, True, True)
            else:
                _save(run, obj, _touch(obj, description=description), False)
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


def _handle_product_directions(
    run: _SheetRun, headers: list[str], rows: list[tuple[int, list[Any]]]
) -> None:
    col = _require(headers, "id продукта", "id направления")
    for excel_row, vals in rows:
        try:
            product_name = _cell_text(vals[col["id продукта"]])
            code = _cell_text(vals[col["id направления"]])
            if not product_name:
                raise RowError("Пустой продукт", field="ID продукта")
            candidates = (
                run.session.execute(select(ITProduct).filter_by(name=product_name)).scalars().all()
            )
            if not candidates:
                raise RowError(f"Продукт '{product_name}' не найден", field="ID продукта")
            if len(candidates) > 1:
                raise RowError(
                    f"Продукт '{product_name}' неоднозначен — есть у нескольких вендоров",
                    field="ID продукта",
                )
            direction = _get(run.session, ITDirection, code=code)
            if direction is None:
                raise RowError(f"Направление '{code or '—'}' не найдено", field="ID направления")
            link = _get(
                run.session,
                ProductDirection,
                product_id=candidates[0].id,
                direction_id=direction.id,
            )
            if link is None:
                link = ProductDirection(product_id=candidates[0].id, direction_id=direction.id)
                _save(run, link, True, True)
            else:
                run.unchanged()
        except RowError as exc:
            run.fail(excel_row, exc.field, str(exc))


#: Normalized sheet title -> handler.
SHEET_HANDLERS = {
    "вузы": _handle_universities,
    "ит продукты": _handle_products,
    "ответственные вуза": _handle_responsibles,
    "договоры и лицензии": _handle_licenses,
    "направления": _handle_directions,
    "программы": _handle_programs,
    "продукт направление": _handle_product_directions,
}

#: Canonical import order (dependencies first); unknown sheets go last.
SHEET_ORDER = [
    "направления",
    "программы",
    "вузы",
    "ит продукты",
    "ответственные вуза",
    "договоры и лицензии",
    "продукт направление",
]


def resolve_sheet_kind(sheet: str) -> str:
    key = normalize_header(sheet)
    if key not in SHEET_HANDLERS:
        raise ImportValidationError(
            f"Неизвестный лист '{sheet}'. Ожидаются: ВУЗы, ИТ-продукты, "
            "Ответственные ВУЗа, Договоры и лицензии, Направления, "
            "Программы, Продукт_Направление",
            code="INVALID_FORMAT",
        )
    return key


def _run_one_sheet(
    db: Session, path: Path, sheet: str, kind: str, *, update_existing: bool
) -> dict[str, Any]:
    headers, rows = _open_sheet(path, sheet)
    if len(rows) > MAX_ROWS:
        raise ImportValidationError(f"В листе больше {MAX_ROWS} строк", code="FILE_TOO_LARGE")
    run = _SheetRun(db, update_existing=update_existing)
    SHEET_HANDLERS[kind](run, headers, rows)
    return {
        "total_rows": len(rows),
        "inserted": run.inserted,
        "updated": run.updated,
        "skipped": run.skipped,
        "errors": run.errors,
        "dry_run": False,
        "errors_total": run.errors_total,
        "truncated": run.errors_total > len(run.errors),
    }


def execute_sheet(
    db: Session, file_id: str, sheet: str, *, dry_run: bool, update_existing: bool
) -> dict[str, Any]:
    """Run one sheet import in a single transaction (rollback on dry-run)."""
    kind = resolve_sheet_kind(sheet)
    path = _staged_path(file_id)
    try:
        summary = _run_one_sheet(db, path, sheet, kind, update_existing=update_existing)
        summary["dry_run"] = dry_run
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return summary
    except Exception:
        db.rollback()
        raise


def execute_sheets(
    db: Session, file_id: str, sheets: list[str], *, dry_run: bool, update_existing: bool
) -> dict[str, Any]:
    """Run several sheets in canonical order inside ONE transaction.

    This is the only way a dry-run sees cross-sheet dependencies (every
    per-sheet dry-run rolls back, so chaining them would fake missing
    parents). Rollback once at the end on dry-run, commit once otherwise.
    """
    if not sheets:
        raise ImportValidationError("Не выбрано ни одного листа", code="INVALID_FORMAT")
    kinds = [(sheet, resolve_sheet_kind(sheet)) for sheet in sheets]
    kinds.sort(key=lambda item: SHEET_ORDER.index(item[1]) if item[1] in SHEET_ORDER else len(SHEET_ORDER))
    path = _staged_path(file_id)
    breakdown: list[dict[str, Any]] = []
    try:
        for sheet, kind in kinds:
            summary = _run_one_sheet(db, path, sheet, kind, update_existing=update_existing)
            breakdown.append({"sheet": sheet, "summary": summary})
        combined = {
            "total_rows": sum(item["summary"]["total_rows"] for item in breakdown),
            "inserted": sum(item["summary"]["inserted"] for item in breakdown),
            "updated": sum(item["summary"]["updated"] for item in breakdown),
            "skipped": sum(item["summary"]["skipped"] for item in breakdown),
            "errors": [
                {**err, "sheet": item["sheet"]}
                for item in breakdown
                for err in item["summary"]["errors"]
            ][:MAX_ROW_ERRORS],
            "dry_run": dry_run,
            "errors_total": sum(item["summary"]["errors_total"] for item in breakdown),
            "truncated": any(item["summary"]["truncated"] for item in breakdown),
            "sheets": [
                {"sheet": item["sheet"], "summary": {**item["summary"], "dry_run": dry_run}}
                for item in breakdown
            ],
        }
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return combined
    except Exception:
        db.rollback()
        raise


def write_error_report(summary: dict[str, Any], path: Path) -> int:
    """Write an errors-only XLSX artifact for the journal download."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ошибки"
    ws.append(["Строка", "Колонка", "Ошибка"])
    for item in summary.get("errors", []):
        ws.append([item.get("row"), item.get("field"), item.get("error")])
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 80
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path.stat().st_size


__all__ = [
    "ImportValidationError",
    "SHEET_HANDLERS",
    "SHEET_ORDER",
    "execute_sheet",
    "execute_sheets",
    "list_sheets",
    "preview_sheet",
    "resolve_sheet_kind",
    "stage_upload",
    "write_error_report",
]
