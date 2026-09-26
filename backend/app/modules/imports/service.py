"""XLSX/XLS catalog import: staging, parsing, validation, execution (P4-10-01).

Scope: ``.xlsx`` + ``.xls`` (legacy Excel 97-2003), basic mapping, simple
validation. Bad rows are skipped with per-row errors — they never abort
the whole import. Idempotency via natural keys (``contract_number`` is
UNIQUE; licenses match on ``(university, product, license_number)``;
directions on ``code``; programs on ``(direction_id, name)``).

``execute_import`` is the worker-owned business operation.  The HTTP route
persists a queued ledger row; ``report_worker`` calls this function after an
atomic claim and commits the terminal summary.
"""

from __future__ import annotations

import io
import os
import re
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
from app.modules.imports.normalize import normalized_name

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
PREVIEW_ROWS = 10
#: Cap на число сохраняемых построчных ошибок в summary (H1): хвост не
#: отбрасывается молча — выставляется truncated=true + errors_total.
MAX_ROW_ERRORS = 100
#: Периодический commit батчами (H1): не держим одну транзакцию на 5000 строк.
#: Прогрессивная фиксация — при крэше воркера уже закоммиченные батчи остаются.
IMPORT_COMMIT_BATCH = 500
STAGING_DIR = os.getenv("IMPORT_STAGING_DIR", "/tmp/rtk-imports")

ALLOWED_EXTS = frozenset({".xlsx", ".xls"})

#: Канонический file_id из stage_upload(): uuid4().hex (32 hex-символа).
#: Строгая валидация закрывает path traversal через file_id (C1).
_FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: file column -> model field paths accepted in ``mapping`` (P4-10-01 §2).
TARGET_FIELDS = frozenset({
    "university.name",
    "university.city",
    "vendor.name",
    "product.name",
    "product.version",
    "vendor_contact.full_name",
    "vendor_contact.phone",
    "vendor_contact.email",
    "vendor_contact.communication_method",
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
    "responsible.email",
    "responsible.phone",
    "responsible.role",
    "university_responsibles",
    "application.external_id",
    "application.student_external_id",
    "application.status",
    "application.flow_name",
    "application.person_name",
    "application.created_at",
})

# One server-owned mapping contract. The UI receives these definitions with
# preview; labels and aliases are never used as persistence identifiers.
FIELD_DEFINITIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "university.name": ("Название ВУЗа", ("вуз", "название вуз", "название вуза", "университет", "наименование вуза", "university")),
    "university.city": ("Город ВУЗа", ("город", "город вуза", "город университета")),
    "vendor.name": ("Вендор", ("вендор", "поставщик", "компания", "vendor")),
    "product.name": ("Название продукта", ("продукт", "по", "название продукта", "программное обеспечение", "product")),
    "product.version": ("Версия продукта", ("версия", "версия продукта")),
    "vendor_contact.full_name": ("ФИО контакта вендора", ("фио контакта", "контактное лицо")),
    "vendor_contact.phone": ("Телефон контакта вендора", ("телефон контакта",)),
    "vendor_contact.email": ("Почта контакта вендора", ("почта контакта",)),
    "vendor_contact.communication_method": ("Способ связи", ("способ связи", "канал связи")),
    "direction.code": ("Код направления", ("код", "код направления", "код ит направления")),
    "direction.name": ("Название направления", ("направление", "ит направление", "it направление", "название направления")),
    "program.name": ("Название программы", ("программа", "ит программа", "название программы")),
    "program.description": ("Описание программы", ("описание программы",)),
    "contract.contract_number": ("Номер договора", ("номер договора", "договор")),
    "license.signed_at": ("Дата подписания лицензии", ("подписание лицензии", "дата подписания", "дата лицензии")),
    "license.expires_at": ("Срок действия лицензии", ("срок лицензии", "срок действия лицензии", "срок действия лицензии (год)", "срок действия", "год окончания")),
    "license.transfer_status": ("Статус передачи", ("статус передачи", "статус по передаче", "статус по передачи")),
    "license.comment": ("Комментарий к лицензии", ("комментарий", "примечание")),
    "responsible.full_name": ("ФИО ответственного", ("фио", "фио менеджера", "ответственный")),
    "responsible.email": ("Почта ответственного", ("почта", "email", "почта ответственного")),
    "responsible.phone": ("Телефон ответственного", ("телефон ответственного",)),
    "responsible.role": ("Роль ответственного", ("роль", "должность")),
    "university_responsibles": ("Ответственные от ВУЗа", ("ответственные от вуза", "представители вуза")),
    "application.external_id": ("ID внешней заявки", ("id заявки", "application id", "external application id", "external id")),
    "application.student_external_id": ("Внешний ID обучающегося", ("id обучающегося", "student external id")),
    "application.status": ("Статус заявки", ("статус заявки", "application status")),
    "application.flow_name": ("Поток заявки", ("поток заявки", "поток", "cohort")),
    "application.person_name": ("ФИО заявителя", ("фио заявителя", "заявитель", "person")),
    "application.created_at": ("Дата создания заявки", ("дата заявки", "создана", "created at")),
}
assert set(FIELD_DEFINITIONS) == TARGET_FIELDS

IMPORT_REQUIRED_FIELDS = {
    "licenses": frozenset({"university.name", "vendor.name", "product.name", "contract.contract_number", "license.signed_at", "license.expires_at"}),
    "universities": frozenset({"university.name"}),
    "directions": frozenset({"direction.code"}),
    "products": frozenset({"vendor.name", "product.name"}),
    "responsibles": frozenset({"responsible.full_name", "responsible.email"}),
    "vendor_contacts": frozenset({
        "vendor.name", "product.name", "vendor_contact.full_name", "vendor_contact.email"
    }),
    "applications": frozenset({"application.external_id", "university.name", "program.name"}),
}

IMPORT_FIELDS_BY_TYPE = {
    "universities": tuple(k for k in TARGET_FIELDS if k.startswith("university.")),
    "directions": tuple(k for k in TARGET_FIELDS if k.startswith("direction.")),
    "products": tuple(k for k in TARGET_FIELDS if k.startswith(("vendor.", "product."))),
    "responsibles": tuple(k for k in TARGET_FIELDS if k.startswith("responsible.")),
    "vendor_contacts": tuple(k for k in TARGET_FIELDS if k.startswith(("vendor.", "product.", "vendor_contact."))),
    "licenses": tuple(k for k in TARGET_FIELDS if not k.startswith(("vendor_contact.", "application."))),
    "applications": tuple(k for k in TARGET_FIELDS if k.startswith("application.") or k in {"university.name", "program.name"}),
}


def normalize_header(value: str) -> str:
    return " ".join(value.lstrip("\ufeff").casefold().replace("ё", "е").replace("_", " ").replace("-", " ").strip().split())


def mapping_contract(headers: list[str], catalog_type: str) -> dict[str, Any]:
    allowed = set(IMPORT_FIELDS_BY_TYPE[catalog_type])
    fields = [
        {"id": key, "label": FIELD_DEFINITIONS[key][0], "required": key in IMPORT_REQUIRED_FIELDS[catalog_type]}
        for key in FIELD_DEFINITIONS if key in allowed
    ]
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for header in headers:
        normalized = normalize_header(header)
        for key in FIELD_DEFINITIONS:
            if key not in allowed or key in used:
                continue
            aliases = (key, key.replace(".", " "), *FIELD_DEFINITIONS[key][1])
            if normalized and normalized in {normalize_header(alias) for alias in aliases}:
                mapping[header] = key
                used.add(key)
                break
    return {"target_fields": fields, "required_fields": sorted(IMPORT_REQUIRED_FIELDS[catalog_type]), "suggested_mapping": mapping}


def validate_mapping(headers: list[str], mapping: dict[str, str], catalog_type: str) -> None:
    if catalog_type not in IMPORT_REQUIRED_FIELDS:
        raise ImportValidationError("Неизвестный тип импорта", code="INVALID_FORMAT", field="catalog_type")
    unknown_sources = set(mapping) - set(headers)
    unknown_targets = set(mapping.values()) - set(IMPORT_FIELDS_BY_TYPE[catalog_type])
    if unknown_sources or unknown_targets:
        raise ImportValidationError("Маппинг содержит неизвестную колонку или поле", code="INVALID_FORMAT", field="mapping")
    if len(mapping.values()) != len(set(mapping.values())):
        raise ImportValidationError("Одно поле системы сопоставлено нескольким колонкам", code="DUPLICATE", field="mapping")
    if IMPORT_REQUIRED_FIELDS[catalog_type] - set(mapping.values()):
        raise ImportValidationError("Не сопоставлены обязательные поля", code="REQUIRED", field="mapping")

TRANSFER_STATUSES = frozenset({"pending", "transferred", "accepted", "rejected"})

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")


class ImportValidationError(ValueError):
    """Single-row validation failure (message is user-facing).

    P4-10-02: machine-readable ``code`` + ``field`` travel with the message
    so the summary and the downloadable XLSX error report can expose them::

        REQUIRED | INVALID_FORMAT | NOT_FOUND | DUPLICATE | FK_VIOLATION
    """

    def __init__(self, message: str, *, code: str = "ROW_ERROR", field: str = "row"):
        super().__init__(message)
        self.code = code
        self.field = field


def parse_date(value: Any, field: str) -> date | None:
    """Coerce an openpyxl/xlrd cell value to ``date`` (``None`` for empty).

    Accepts datetime/date and full date strings. A year alone cannot be
    stored in the existing DATE column without inventing a day and month.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        if float(value).is_integer() and 1900 <= int(value) <= 2100:
            raise ImportValidationError(
                f"Для поля '{field}' укажите полную дату: год без дня и месяца неоднозначен",
                code="INVALID_FORMAT", field=field,
            )
        raise ImportValidationError(
            f"Неверный формат даты в поле '{field}'",
            code="INVALID_FORMAT", field=field,
        )
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"(19|20)\d{2}", text):
            raise ImportValidationError(
                f"Для поля '{field}' укажите полную дату: год без дня и месяца неоднозначен",
                code="INVALID_FORMAT", field=field,
            )
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ImportValidationError(
        f"Неверный формат даты в поле '{field}'",
        code="INVALID_FORMAT", field=field,
    )


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
            "Поддерживаются только .xlsx и .xls"
        )
    if len(content) > MAX_FILE_BYTES:
        raise ImportValidationError(
            f"Файл больше лимита {MAX_FILE_BYTES // 1024 // 1024} МБ"
        )
    if not content:
        raise ImportValidationError("Пустой файл")
    if ext == ".xlsx":
        if not content.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(io.BytesIO(content)):
            raise ImportValidationError("Содержимое файла не соответствует XLSX")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 5000 or sum(item.file_size for item in members) > 64 * 1024 * 1024:
                raise ImportValidationError("XLSX превышает безопасный размер распаковки")
            if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(archive.namelist()):
                raise ImportValidationError("Некорректная структура XLSX")
    elif not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ImportValidationError("Содержимое файла не соответствует XLS")
    os.makedirs(STAGING_DIR, exist_ok=True)
    file_id = uuid.uuid4().hex
    with open(os.path.join(STAGING_DIR, f"{file_id}{ext}"), "wb") as fh:
        fh.write(content)
    return file_id


def _staged_path(file_id: str) -> str:
    # Строгая валидация: только канонический <hex32>, иначе 400.
    # Закрывает path traversal (C1): '../../' и 'a.xlsx' отклоняются до join.
    if not _FILE_ID_RE.fullmatch(file_id or ""):
        raise ImportValidationError("Некорректный file_id (загрузите файл заново)")
    base = Path(STAGING_DIR).resolve()
    for ext in (".xlsx", ".xls"):
        candidate = (base / f"{file_id}{ext}").resolve()
        # Пояс от судьбы: даже при корректном file_id проверяем containment.
        try:
            candidate.relative_to(base)
        except ValueError:
            raise ImportValidationError("Некорректный file_id (загрузите файл заново)")
        if candidate.is_file():
            return str(candidate)
    raise ImportValidationError("Файл не найден (загрузите заново)")


def _read_xlsx(path: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ImportValidationError("В книге нет листов")
    row_iter = ws.iter_rows(values_only=True)
    first = next(row_iter, None)
    if first is None:
        raise ImportValidationError("Пустой лист")
    headers = [_cell_text(c).lstrip("\ufeff") or f"col_{i}" for i, c in enumerate(first)]
    _validate_headers(headers)
    data = []
    for row in row_iter:
        if len(data) >= MAX_ROWS:
            raise ImportValidationError(f"Больше лимита {MAX_ROWS} строк")
        data.append(dict(zip(headers, row)))
    wb.close()
    return ws.title or "Sheet1", headers, data


def _read_xls(path: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Read legacy Excel 97-2003 (.xls) via xlrd. Same shape as _read_xlsx."""
    import xlrd

    try:
        book = xlrd.open_workbook(path, logfile=None)
    except Exception as exc:
        raise ImportValidationError(f"Не удалось прочитать .xls: {exc}") from exc
    if book.nsheets == 0:
        raise ImportValidationError("В книге нет листов")
    sh = book.sheet_by_index(0)
    if sh.nrows == 0:
        raise ImportValidationError("Пустой лист")
    headers = [_cell_text(sh.cell_value(0, c)) or f"col_{c}" for c in range(sh.ncols)]
    _validate_headers(headers)
    data: list[dict[str, Any]] = []
    if sh.nrows - 1 > MAX_ROWS:
        raise ImportValidationError(f"Больше лимита {MAX_ROWS} строк")
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


def _validate_headers(headers: list[str]) -> None:
    normalized = [normalize_header(header) for header in headers]
    if len(normalized) != len(set(normalized)):
        raise ImportValidationError("В файле повторяются названия колонок", code="DUPLICATE", field="headers")


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


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards in user-supplied fuzzy-search text."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def find_university(session: Session, name: str) -> University | None:
    """Exact normalized identity only; substring matches can merge different VУЗы."""
    matches = list(session.scalars(
        select(University).where(func.lower(University.name) == name.lower()).limit(2)
    ))
    if len(matches) > 1:
        raise ImportValidationError("Неоднозначное совпадение ВУЗа", code="DUPLICATE", field="university.name")
    return matches[0] if matches else None


def resolve_responsible(session: Session, full_name: str, field: str) -> Responsible:
    """Resolve an existing catalog identity; never invent a synthetic email."""
    matches = list(session.scalars(
        select(Responsible).where(func.lower(Responsible.full_name) == full_name.lower()).limit(2)
    ))
    if not matches:
        raise ImportValidationError(
            "Ответственный отсутствует в каталоге", code="NOT_FOUND", field=field,
        )
    if len(matches) > 1:
        raise ImportValidationError(
            "Неоднозначный ответственный", code="DUPLICATE", field=field,
        )
    return matches[0]


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
    uni_name = normalized_name(mapped.get("university.name"))
    if not uni_name:
        raise ImportValidationError(
            "Поле 'university.name' обязательно",
            code="REQUIRED", field="university.name",
        )
    uni = find_university(session, uni_name)
    if uni is None:
        uni = University(name=uni_name, city=None)
        session.add(uni)
        session.flush()

    contract_no = _cell_text(mapped.get("contract.contract_number"))
    if not contract_no:
        raise ImportValidationError(
            "Поле 'contract.contract_number' обязательно",
            code="REQUIRED", field="contract.contract_number",
        )

    product_name = normalized_name(mapped.get("product.name"))
    product = None
    if product_name:
        vendor_name = normalized_name(mapped.get("vendor.name"))
        if not vendor_name:
            raise ImportValidationError(
                "Поле 'vendor.name' обязательно, если указан продукт",
                code="REQUIRED", field="vendor.name",
            )
        vendors = list(session.scalars(select(Vendor).where(func.lower(Vendor.name) == vendor_name.lower()).limit(2)))
        if len(vendors) > 1:
            raise ImportValidationError("Неоднозначный вендор", code="DUPLICATE", field="vendor.name")
        vendor = vendors[0] if vendors else Vendor(name=vendor_name)
        if not vendors:
            session.add(vendor)
            session.flush()
        # P4-10-03: если колонки "Версия ПО" нет — дефолт "1.0" (ключ продукта
        # включает версию, поэтому "" плодил бы дубли на каждый импорт).
        version = normalized_name(mapped.get("product.version")) or "1.0"
        products = list(session.scalars(select(ITProduct).where(
            ITProduct.vendor_id == vendor.id,
            func.lower(ITProduct.name) == product_name.lower(),
            ITProduct.version == version,
        ).limit(2)))
        if len(products) > 1:
            raise ImportValidationError("Неоднозначный продукт", code="DUPLICATE", field="product.name")
        product = products[0] if products else ITProduct(vendor_id=vendor.id, name=product_name, version=version)
        if not products:
            session.add(product)
            session.flush()

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
                " (или замаппьте 'direction.name' для автогенерации кода)",
                code="REQUIRED", field="direction.code",
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
        raise ImportValidationError(
            "Поле 'license.expires_at' обязательно",
            code="REQUIRED", field="license.expires_at",
        )
    transfer_raw = _cell_text(mapped.get("license.transfer_status"))
    transfer = transfer_raw or "pending"
    if transfer not in TRANSFER_STATUSES:
        raise ImportValidationError(
            "Недопустимый статус передачи (pending/transferred/accepted/rejected)",
            code="INVALID_FORMAT", field="license.transfer_status",
        )
    comment_raw = mapped.get("license.comment")
    comment = _cell_text(comment_raw) or None

    contract = session.execute(
        select(Contract).filter_by(contract_number=contract_no)
    ).scalar_one_or_none()
    if contract is not None and contract.university_id != uni.id:
        raise ImportValidationError(
            "Номер договора уже принадлежит другому ВУЗу",
            code="DUPLICATE", field="contract.contract_number",
        )
    if contract is not None and product is not None and contract.product_id not in (None, product.id):
        raise ImportValidationError(
            "Договор уже привязан к другому продукту",
            code="DUPLICATE", field="contract.contract_number",
        )
    if contract is None:
        if signed_at is None:
            raise ImportValidationError("Укажите дату подписания лицензии", code="REQUIRED", field="license.signed_at")
        contract = Contract(
            university_id=uni.id, contract_number=contract_no,
            product_id=product.id if product else None,
            signed_at=signed_at, expires_at=expires_at,
            status_raw="signed", transfer_status_raw=transfer, comment=comment,
        )
        session.add(contract)
        session.flush()
        contract_created = True
    elif update_existing:
        contract.signed_at = signed_at or contract.signed_at
        contract.expires_at = expires_at
        if product is not None:
            contract.product_id = product.id
        if transfer_raw:
            contract.transfer_status_raw = transfer
        if comment is not None:
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
                "Строка без продукта: не к чему привязать лицензию",
                code="REQUIRED", field="product.name",
            )
        if signed_at is None:
            raise ImportValidationError("Укажите дату подписания лицензии", code="REQUIRED", field="license.signed_at")
        session.add(License(
            university_id=uni.id, product_id=product.id, contract_id=contract.id,
            program_id=row_program.id if row_program else None,
            direction_id=row_direction.id if row_direction else None,
            license_number=license_number, signed_at=signed_at,
            expires_at=expires_at, transfer_status_raw=transfer, comment=comment,
        ))
        session.flush()
        lic_created = True
    elif update_existing:
        lic.expires_at = expires_at
        lic.signed_at = signed_at or lic.signed_at
        if transfer_raw:
            lic.transfer_status_raw = transfer
        lic.contract_id = contract.id
        if row_program is not None:
            lic.program_id = row_program.id
        if row_direction is not None:
            lic.direction_id = row_direction.id
        if comment is not None:
            lic.comment = comment
        session.flush()
        lic_created = False
    else:
        return "skipped"

    manager_name = _cell_text(mapped.get("responsible.full_name"))
    if manager_name:
        manager = resolve_responsible(session, manager_name, "responsible.full_name")
        link_responsible(session, uni.id, manager.id, "our_manager")

    contacts_raw = _cell_text(mapped.get("university_responsibles"))
    if contacts_raw:
        for part in contacts_raw.replace(",", ";").split(";"):
            name = part.strip()
            if not name:
                continue
            contact = resolve_responsible(session, name, "university_responsibles")
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
    catalog_type: str = "licenses",
) -> dict[str, Any]:
    """Run the import over all staged rows. Bad rows are collected, never fatal.

    P4-10-02: каждая строка выполняется в собственном savepoint
    (``session.begin_nested()``) — откат плохой строки не трогает хорошие.

    H1: успешные строки фиксируются батчами (IMPORT_COMMIT_BATCH), а не одним
    commit в конце — не держим открытую транзакцию/снапшот на весь файл.
    При dry_run коммитов нет — в конце общий rollback.
    Ошибки сверх MAX_ROW_ERRORS не отбрасываются молча: truncated=true,
    errors_total считает все ошибки.
    """
    _, headers, data = read_sheet(file_id)
    validate_mapping(headers, mapping, catalog_type)
    summary: dict[str, Any] = {
        "total_rows": len(data), "inserted": 0, "updated": 0,
        "skipped": 0, "errors": [], "dry_run": dry_run,
        "truncated": False, "errors_total": 0,
    }
    errors_total = 0
    truncated = False
    processed_since_commit = 0
    try:
        for idx, row in enumerate(data, start=2):  # 1-based incl. header
            if truncated:
                summary["skipped"] += 1
                continue
            if all(v is None or _cell_text(v) == "" for v in row.values()):
                summary["skipped"] += 1
                continue
            try:
                with session.begin_nested():
                    mapped = _mapped(row, mapping)
                    if catalog_type == "licenses":
                        outcome = apply_row(session, mapped, update_existing)
                    else:
                        from app.modules.imports.catalog_rows import apply_catalog_row

                        outcome = apply_catalog_row(session, mapped, catalog_type, update_existing)
                summary[outcome] += 1
                processed_since_commit += 1
            except ImportValidationError as exc:
                errors_total += 1
                if len(summary["errors"]) < MAX_ROW_ERRORS:
                    summary["errors"].append(
                        {"row": idx, "source_field": next((source for source, target in mapping.items() if target == exc.field), None),
                         "field": exc.field, "code": exc.code,
                         "message": str(exc)}
                    )
                else:
                    truncated = True
                continue
            except IntegrityError:
                errors_total += 1
                if len(summary["errors"]) < MAX_ROW_ERRORS:
                    summary["errors"].append({"row": idx, "source_field": None, "field": "row", "code": "DUPLICATE", "message": "Конфликт уникальности или связей; строка не сохранена"})
                else:
                    truncated = True
                continue
            if not dry_run and processed_since_commit >= IMPORT_COMMIT_BATCH:
                session.commit()
                processed_since_commit = 0
        summary["truncated"] = truncated
        summary["errors_total"] = errors_total
        if dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    return summary


def write_error_report(summary: dict[str, Any], dest: str) -> int:
    """P4-10-02: скачиваемый XLSX-отчёт (лист «Итог» + лист «Ошибки»).

    Возвращает размер файла в байтах. Пишется всегда (даже без ошибок —
    тогда лист «Ошибки» содержит только шапку), чтобы у job был файловый
    артефакт для ``GET /import/jobs/{id}/report``.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws_total = wb.active
    ws_total.title = "Итог"
    bold = Font(bold=True)
    ws_total.append(["Метрика", "Значение"])
    for cell in ws_total[1]:
        cell.font = bold
    for key in ("total_rows", "inserted", "updated", "skipped", "dry_run"):
        ws_total.append([key, summary.get(key)])
    ws_total.append(["errors", len(summary.get("errors", []))])
    ws_total.append(["errors_total", summary.get("errors_total", len(summary.get("errors", [])))])
    ws_total.append(["truncated", summary.get("truncated", False)])
    for col in ("A", "B"):
        ws_total.column_dimensions[col].width = 18

    ws_err = wb.create_sheet("Ошибки")
    ws_err.append(["Строка", "Колонка файла", "Поле системы", "Код", "Сообщение"])
    for cell in ws_err[1]:
        cell.font = bold
    for err in summary.get("errors", []):
        ws_err.append([
            err.get("row"), err.get("source_field"), err.get("field"),
            err.get("code"), err.get("message"),
        ])
    for col, width in (("A", 10), ("B", 28), ("C", 28), ("D", 16), ("E", 70)):
        ws_err.column_dimensions[col].width = width

    wb.save(dest)
    wb.close()
    return os.path.getsize(dest)


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
    "write_error_report",
]
