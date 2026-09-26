"""Per-catalog row application for the shared import job pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import ITDirection, ITProduct, ITProgram, Responsible, University, Vendor, VendorContact
from app.models.external import ExternalApplication
from app.models.interactions import Student, UniversityProgram
from app.modules.imports.normalize import normalize_phone, normalized_name, split_products
from app.modules.imports.service import ImportValidationError


def _required(row: dict, field: str) -> str:
    value = normalized_name(row.get(field))
    if not value:
        raise ImportValidationError(f"Поле {field} обязательно", code="REQUIRED", field=field)
    return value


def _unique_match(db: Session, model, field, value: str, label: str):
    matches = list(db.scalars(select(model).where(func.lower(field) == value.lower()).limit(2)))
    if len(matches) > 1:
        raise ImportValidationError(
            f"Неоднозначное совпадение поля {label}", code="DUPLICATE", field=label
        )
    return matches[0] if matches else None


def _vendor(db: Session, name: str) -> tuple[Vendor, bool]:
    vendor = _unique_match(db, Vendor, Vendor.name, name, "vendor.name")
    if vendor is not None:
        return vendor, False
    vendor = Vendor(name=name)
    db.add(vendor)
    db.flush()
    return vendor, True


def _product(db: Session, vendor: Vendor, name: str, version: str) -> tuple[ITProduct, bool]:
    query = select(ITProduct).where(
        ITProduct.vendor_id == vendor.id,
        func.lower(ITProduct.name) == name.lower(),
    )
    if version:
        query = query.where(ITProduct.version == version)
    candidates = list(db.scalars(query.limit(2)))
    if len(candidates) == 1:
        return candidates[0], False
    if len(candidates) > 1:
        raise ImportValidationError(
            "У продукта несколько версий; укажите product.version",
            code="DUPLICATE", field="product.version",
        )
    product = ITProduct(vendor_id=vendor.id, name=name, version=version or "1.0")
    db.add(product)
    db.flush()
    return product, True


def apply_catalog_row(db: Session, row: dict, kind: str, update_existing: bool) -> str:
    if kind == "applications":
        from app.modules.integrations.service import upsert_application

        external_id = _required(row, "application.external_id")
        university_name = _required(row, "university.name")
        program_name = _required(row, "program.name")
        university = _unique_match(db, University, University.name, university_name, "university.name")
        if university is None:
            raise ImportValidationError("ВУЗ отсутствует в каталоге", code="NOT_FOUND", field="university.name")
        programs = list(db.scalars(select(ITProgram).join(UniversityProgram, UniversityProgram.program_id == ITProgram.id).where(
            UniversityProgram.university_id == university.id,
            func.lower(ITProgram.name) == program_name.lower(),
        ).limit(2)))
        if len(programs) != 1:
            raise ImportValidationError("Программа не найдена или связь неоднозначна", code="NOT_FOUND" if not programs else "DUPLICATE", field="program.name")
        existing = db.scalar(select(ExternalApplication).where(
            ExternalApplication.source == "website", ExternalApplication.external_id == external_id,
        ))
        if existing is not None:
            if existing.university_id not in (None, university.id) or (existing.workflow_instance_id is not None and existing.program_id not in (None, programs[0].id)):
                raise ImportValidationError("ID заявки связан с другим ВУЗом или Workflow", code="DUPLICATE", field="application.external_id")
            if not update_existing:
                return "skipped"
        payload = {"external_id": external_id, "university_id": university.id,
                   "program_id": programs[0].id}
        for key, target in (("application.person_name", "person_name"), ("application.status", "status"),
                            ("application.flow_name", "flow_name")):
            if key in row:
                payload[target] = normalized_name(row[key]) or None
        student_external_id = normalized_name(row.get("application.student_external_id"))
        if student_external_id:
            student = db.scalar(select(Student).where(Student.external_id == student_external_id))
            if student is None or student.university_id != university.id:
                raise ImportValidationError("Обучающийся с указанным ID не найден в этом ВУЗе", code="NOT_FOUND", field="application.student_external_id")
            payload["student_id"] = student.id
        raw_created = row.get("application.created_at")
        if raw_created not in (None, ""):
            try:
                created = raw_created if isinstance(raw_created, datetime) else datetime.fromisoformat(str(raw_created).strip().replace("Z", "+00:00"))
                payload["external_created_at"] = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ImportValidationError("Неверная дата заявки", code="INVALID_FORMAT", field="application.created_at") from exc
        upsert_application(db, payload, ingest_channel="file", synced_at=datetime.now(timezone.utc))
        return "updated" if existing is not None else "inserted"

    if kind == "universities":
        name = _required(row, "university.name")
        city = normalized_name(row.get("university.city")) or None
        university = _unique_match(db, University, University.name, name, "university.name")
        if university is None:
            db.add(University(name=name, city=city))
            db.flush()
            return "inserted"
        if update_existing and city is not None and university.city != city:
            university.city = city
            db.flush()
            return "updated"
        return "skipped"

    if kind == "directions":
        code = _required(row, "direction.code")
        name = normalized_name(row.get("direction.name")) or None
        direction = _unique_match(db, ITDirection, ITDirection.code, code, "direction.code")
        if direction is None:
            db.add(ITDirection(code=code, name=name or code))
            db.flush()
            return "inserted"
        if update_existing and name is not None and direction.name != name:
            direction.name = name
            db.flush()
            return "updated"
        return "skipped"

    if kind == "responsibles":
        email = _required(row, "responsible.email").lower()
        name = _required(row, "responsible.full_name")
        person = _unique_match(db, Responsible, Responsible.email, email, "responsible.email")
        try:
            phone = normalize_phone(row.get("responsible.phone"))
        except ValueError as exc:
            raise ImportValidationError(str(exc), code="INVALID_FORMAT", field="responsible.phone") from exc
        role = normalized_name(row.get("responsible.role"))
        if person is None:
            db.add(Responsible(full_name=name, email=email, phone=phone, role=role))
            db.flush()
            return "inserted"
        if not update_existing:
            return "skipped"
        next_phone = phone if phone is not None else person.phone
        next_role = role if role else person.role
        changed = (person.full_name, person.phone, person.role) != (name, next_phone, next_role)
        if changed:
            person.full_name, person.phone, person.role = name, next_phone, next_role
            db.flush()
            return "updated"
        return "skipped"

    if kind not in {"products", "vendor_contacts"}:
        raise ImportValidationError(f"Неизвестный тип импорта: {kind}", field="catalog_type")
    vendor_name = _required(row, "vendor.name")
    product_names = split_products(_required(row, "product.name"))
    version = normalized_name(row.get("product.version"))
    vendor, vendor_created = _vendor(db, vendor_name)
    created = vendor_created
    changed = False
    for product_name in product_names:
        product, product_created = _product(db, vendor, product_name, version)
        created = created or product_created
        if kind != "vendor_contacts":
            continue
        full_name = _required(row, "vendor_contact.full_name")
        email = _required(row, "vendor_contact.email").lower()
        try:
            phone = normalize_phone(row.get("vendor_contact.phone"))
        except ValueError as exc:
            raise ImportValidationError(str(exc), code="INVALID_FORMAT", field="vendor_contact.phone") from exc
        method = normalized_name(row.get("vendor_contact.communication_method")) or None
        contact = db.scalar(select(VendorContact).where(
            VendorContact.product_id == product.id,
            func.lower(VendorContact.email) == email,
        ))
        if contact is None:
            db.add(VendorContact(
                vendor_id=vendor.id, product_id=product.id, full_name=full_name,
                phone=phone, email=email, communication_method=method,
            ))
            db.flush()
            created = True
        elif update_existing and (
            contact.full_name, contact.phone, contact.communication_method
        ) != (full_name, phone if phone is not None else contact.phone,
              method if method is not None else contact.communication_method):
            contact.full_name = full_name
            if phone is not None:
                contact.phone = phone
            if method is not None:
                contact.communication_method = method
            db.flush()
            changed = True
    return "inserted" if created else "updated" if changed else "skipped"
