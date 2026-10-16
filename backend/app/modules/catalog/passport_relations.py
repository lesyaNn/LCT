"""Atomic university relations used by Passport mutations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.models.catalog import ITProduct, ITProgram, Responsible, University, UniversityResponsible
from app.models.interactions import UniversityProduct, UniversityProgram
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.catalog.schemas import (
    PrimaryResponsibleChange,
    UniversityProgramAttach,
    UniversityProgramRead,
    UniversityProductAttach,
    UniversityProductRead,
    UniversityResponsibleRead,
)


def _lock_university(db: Session, university_id: uuid.UUID) -> None:
    university = db.scalar(
        select(University).where(University.id == university_id).with_for_update()
    )
    if university is None:
        raise NotFound("University not found")


def _display_or_none(db: Session, model, pk, attr: str = "name"):
    try:
        row = db.get(model, pk)
        value = getattr(row, attr, None) if row is not None else None
        return value if isinstance(value, str) and value.strip() else None
    except Exception:
        return None


def attach_program(
    db: Session, university_id: uuid.UUID, data: UniversityProgramAttach
) -> UniversityProgramRead:
    _lock_university(db, university_id)
    if db.get(ITProgram, data.program_id) is None:
        raise NotFound("Program not found")
    existing = db.scalar(
        select(UniversityProgram.id).where(
            UniversityProgram.university_id == university_id,
            UniversityProgram.program_id == data.program_id,
        )
    )
    if existing is not None:
        raise Conflict("Программа уже закреплена за этим ВУЗом.")
    link = UniversityProgram(
        university_id=university_id, program_id=data.program_id, status=data.status
    )
    db.add(link)
    db.flush()
    if "audit_context" in db.info:
        new_value: dict = {
            "audit_object_type": "university_program",
            "program_id": str(data.program_id), "status": data.status,
        }
        program_name = _display_or_none(db, ITProgram, data.program_id)
        if program_name:
            new_value["program_name"] = program_name
        university_name = _display_or_none(db, University, university_id)
        if university_name:
            new_value["university_name"] = university_name
        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.CREATE,
            entity_type="program", entity_id=link.id, university_id=university_id,
            new_value=new_value,
        )
    db.commit()
    db.refresh(link)
    return UniversityProgramRead.model_validate(link)


def attach_product(
    db: Session, university_id: uuid.UUID, data: UniversityProductAttach
) -> UniversityProductRead:
    _lock_university(db, university_id)
    if db.get(ITProduct, data.product_id) is None:
        raise NotFound("Product not found")
    existing = db.scalar(
        select(UniversityProduct.id).where(
            UniversityProduct.university_id == university_id,
            UniversityProduct.product_id == data.product_id,
        )
    )
    if existing is not None:
        raise Conflict("Продукт уже закреплён за этим ВУЗом.")
    link = UniversityProduct(
        university_id=university_id, product_id=data.product_id, status=data.status
    )
    db.add(link)
    db.flush()
    if "audit_context" in db.info:
        new_value = {
            "audit_object_type": "university_product",
            "product_id": str(data.product_id), "status": data.status,
        }
        product_name = _display_or_none(db, ITProduct, data.product_id)
        if product_name:
            new_value["product_name"] = product_name
        university_name = _display_or_none(db, University, university_id)
        if university_name:
            new_value["university_name"] = university_name
        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.CREATE,
            entity_type="product", entity_id=link.id, university_id=university_id,
            new_value=new_value,
        )
    db.commit()
    db.refresh(link)
    return UniversityProductRead.model_validate(link)


def change_primary_responsible(
    db: Session, university_id: uuid.UUID, data: PrimaryResponsibleChange
) -> UniversityResponsibleRead:
    _lock_university(db, university_id)
    if db.get(Responsible, data.responsible_id) is None:
        raise NotFound("Responsible not found")
    links = list(
        db.scalars(
            select(UniversityResponsible)
            .where(UniversityResponsible.university_id == university_id)
            .order_by(UniversityResponsible.id)
        ).all()
    )
    previous = [link for link in links if link.is_primary]
    if len(previous) > 1:
        raise Conflict("У ВУЗа уже несколько основных ответственных; требуется исправить данные.")
    old_id = previous[0].responsible_id if previous else None
    selected = next(
        (link for link in links if link.responsible_id == data.responsible_id), None
    )
    if old_id == data.responsible_id and selected is not None:
        return UniversityResponsibleRead.model_validate(selected)
    if previous:
        previous[0].is_primary = False
        db.flush()
    if selected is None:
        selected = UniversityResponsible(
            university_id=university_id,
            responsible_id=data.responsible_id,
            is_primary=True,
        )
        db.add(selected)
    else:
        selected.is_primary = True
    db.flush()
    if "audit_context" in db.info:
        old_value: dict = {
            "audit_object_type": "responsible_assignment",
            "responsible_id": str(old_id) if old_id else None,
        }
        if old_id:
            old_name = _display_or_none(db, Responsible, old_id, "full_name")
            if old_name:
                old_value["responsible_name"] = old_name
        new_value = {
            "audit_object_type": "responsible_assignment",
            "responsible_id": str(data.responsible_id), "reason": data.reason,
        }
        new_name = _display_or_none(db, Responsible, data.responsible_id, "full_name")
        if new_name:
            new_value["responsible_name"] = new_name
        university_name = _display_or_none(db, University, university_id)
        if university_name:
            new_value["university_name"] = university_name
        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.ASSIGN_RESPONSIBLE,
            entity_type="responsible", entity_id=selected.id,
            university_id=university_id,
            old_value=old_value,
            new_value=new_value,
        )
    from app.modules.notifications.service import notify_assignment

    notify_assignment(db, data.responsible_id, university_id,
                      event_key=f"primary-assigned:{university_id}:{data.responsible_id}:{uuid.uuid4()}")
    db.commit()
    db.refresh(selected)
    return UniversityResponsibleRead.model_validate(selected)
