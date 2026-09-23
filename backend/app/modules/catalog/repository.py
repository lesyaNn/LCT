"""P1-03 query layer: filtered/paginated/sorted SELECTs + writes.

All list queries are exactly 2 SELECTs (COUNT with the same WHERE, then the
page); many-to-one display names (direction_name, vendor_name) come from a
JOIN inside the page statement — never a query per item. Detail loaders use
1-2 constant statements. No business logic here, only query construction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)

# ------------------------------------------------------------- like escape


def like_pattern(raw: str) -> str:
    """Wrap a user search term for ILIKE, escaping %, _ and backslash."""
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _order(model, sort_map: dict, sort_by: str, sort_order: str):
    """Whitelisted ORDER BY + deterministic id tie-break (total order)."""
    column = sort_map[sort_by]  # KeyError is impossible: router validates via Literal
    primary = column.asc() if sort_order == "asc" else column.desc()
    return [primary, model.id.asc()]


# -------------------------------------------------------------- universities


UNIVERSITY_SORT = {
    "name": University.name,
    "city": University.city,
    "created_at": University.created_at,
}


def university_conditions(
    *,
    search: str | None,
    city: str | None,
    responsible_id: uuid.UUID | None,
    unified_filter=None,
    today=None,
):
    conds = []
    if search:
        pattern = like_pattern(search)
        conds.append(
            or_(
                University.name.ilike(pattern, escape="\\"),
                University.city.ilike(pattern, escape="\\"),
            )
        )
    if city is not None:
        conds.append(University.city == city)
    if responsible_id is not None:
        conds.append(
            exists(
                select(1)
                .select_from(UniversityResponsible)
                .where(
                    UniversityResponsible.university_id == University.id,
                    UniversityResponsible.responsible_id == responsible_id,
                )
            )
        )
    if unified_filter is not None:
        # P4-01-02: additive AND with legacy filters; EXISTS strategy keeps
        # one row per university (no JOIN fan-out). Import is local so the
        # catalog layer never hard-depends on the analytics package at
        # module load time.
        from app.modules.analytics.filter_service import UnifiedFilterService

        conds.extend(
            UnifiedFilterService.build_university_conditions(unified_filter, today=today)
        )
    return conds


def list_universities(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    city: str | None,
    responsible_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
    unified_filter=None,
    unified_today=None,
    user=None,
) -> tuple[list[University], int]:
    conds = university_conditions(
        search=search,
        city=city,
        responsible_id=responsible_id,
        unified_filter=unified_filter,
        today=unified_today,
    )
    count_stmt = select(func.count()).select_from(University).where(*conds)
    page_stmt = (
        select(University)
        .where(*conds)
        .order_by(*_order(University, UNIVERSITY_SORT, sort_by, sort_order))
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    if user is not None:
        # Same security intersection as the report dataset: scoped users are
        # confined to their universities for BOTH total and page.
        from app.modules.analytics.filter_service import UnifiedFilterService

        count_stmt = UnifiedFilterService.apply_security_scope(count_stmt, user)
        page_stmt = UnifiedFilterService.apply_security_scope(page_stmt, user)
    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(page_stmt).scalars().all()
    return list(rows), int(total)


def get_university(db: Session, university_id: uuid.UUID) -> University | None:
    return db.get(University, university_id)


def university_responsibles(db: Session, university_id: uuid.UUID) -> list[tuple]:
    """(Responsible, UniversityResponsible) pairs for one university, ONE query."""
    return list(
        db.execute(
            select(Responsible, UniversityResponsible)
            .join(
                UniversityResponsible,
                UniversityResponsible.responsible_id == Responsible.id,
            )
            .where(UniversityResponsible.university_id == university_id)
            .order_by(Responsible.full_name.asc(), Responsible.id.asc())
        ).all()
    )


# -------------------------------------------------------------- directions


DIRECTION_SORT = {
    "code": ITDirection.code,
    "name": ITDirection.name,
    "created_at": ITDirection.created_at,
}


def list_directions(
    db: Session, *, page: int, page_size: int, search: str | None, sort_by: str, sort_order: str
) -> tuple[list[ITDirection], int]:
    conds = []
    if search:
        pattern = like_pattern(search)
        conds.append(
            or_(
                ITDirection.code.ilike(pattern, escape="\\"),
                ITDirection.name.ilike(pattern, escape="\\"),
            )
        )
    total = db.execute(select(func.count()).select_from(ITDirection).where(*conds)).scalar() or 0
    rows = (
        db.execute(
            select(ITDirection)
            .where(*conds)
            .order_by(*_order(ITDirection, DIRECTION_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_direction(db: Session, direction_id: uuid.UUID) -> ITDirection | None:
    return db.get(ITDirection, direction_id)


def direction_programs(db: Session, direction_id: uuid.UUID) -> list[tuple]:
    """(ITProgram, direction_name) for one direction, ONE query."""
    return list(
        db.execute(
            select(ITProgram, ITDirection.name)
            .join(ITDirection, ITDirection.id == ITProgram.direction_id)
            .where(ITProgram.direction_id == direction_id)
            .order_by(ITProgram.name.asc(), ITProgram.id.asc())
        ).all()
    )


# ---------------------------------------------------------------- programs


PROGRAM_SORT = {
    "name": ITProgram.name,
    "created_at": ITProgram.created_at,
}


def list_programs(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    direction_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple], int]:
    """Page rows are (ITProgram, direction_name) tuples — JOIN, no N+1."""
    conds = []
    if search:
        conds.append(ITProgram.name.ilike(like_pattern(search), escape="\\"))
    if direction_id is not None:
        conds.append(ITProgram.direction_id == direction_id)
    total = db.execute(select(func.count()).select_from(ITProgram).where(*conds)).scalar() or 0
    rows = list(
        db.execute(
            select(ITProgram, ITDirection.name)
            .join(ITDirection, ITDirection.id == ITProgram.direction_id)
            .where(*conds)
            .order_by(*_order(ITProgram, PROGRAM_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
    )
    return rows, int(total)


def get_program(db: Session, program_id: uuid.UUID) -> tuple | None:
    """(ITProgram, ITDirection|None), ONE statement."""
    return db.execute(
        select(ITProgram, ITDirection)
        .outerjoin(ITDirection, ITDirection.id == ITProgram.direction_id)
        .where(ITProgram.id == program_id)
    ).first()


# ---------------------------------------------------------------- products


PRODUCT_SORT = {
    "name": ITProduct.name,
    "version": ITProduct.version,
    "created_at": ITProduct.created_at,
}


def list_products(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    vendor_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple], int]:
    """Page rows are (ITProduct, vendor_name) tuples — JOIN, no N+1."""
    conds = []
    if search:
        conds.append(ITProduct.name.ilike(like_pattern(search), escape="\\"))
    if vendor_id is not None:
        conds.append(ITProduct.vendor_id == vendor_id)
    total = db.execute(select(func.count()).select_from(ITProduct).where(*conds)).scalar() or 0
    rows = list(
        db.execute(
            select(ITProduct, Vendor.name)
            .join(Vendor, Vendor.id == ITProduct.vendor_id)
            .where(*conds)
            .order_by(*_order(ITProduct, PRODUCT_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
    )
    return rows, int(total)


def get_product(db: Session, product_id: uuid.UUID) -> tuple | None:
    """(ITProduct, Vendor|None), ONE statement."""
    return db.execute(
        select(ITProduct, Vendor)
        .outerjoin(Vendor, Vendor.id == ITProduct.vendor_id)
        .where(ITProduct.id == product_id)
    ).first()


# ----------------------------------------------------------------- vendors


VENDOR_SORT = {
    "name": Vendor.name,
    "created_at": Vendor.created_at,
}


def list_vendors(
    db: Session, *, page: int, page_size: int, search: str | None, sort_by: str, sort_order: str
) -> tuple[list[Vendor], int]:
    conds = []
    if search:
        conds.append(Vendor.name.ilike(like_pattern(search), escape="\\"))
    total = db.execute(select(func.count()).select_from(Vendor).where(*conds)).scalar() or 0
    rows = (
        db.execute(
            select(Vendor)
            .where(*conds)
            .order_by(*_order(Vendor, VENDOR_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_vendor(db: Session, vendor_id: uuid.UUID) -> Vendor | None:
    return db.get(Vendor, vendor_id)


def vendor_products(db: Session, vendor_id: uuid.UUID) -> list[ITProduct]:
    """Products of one vendor, ONE query."""
    return list(
        db.execute(
            select(ITProduct)
            .where(ITProduct.vendor_id == vendor_id)
            .order_by(ITProduct.name.asc(), ITProduct.id.asc())
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------- responsibles


RESPONSIBLE_SORT = {
    "full_name": Responsible.full_name,
    "email": Responsible.email,
    "created_at": Responsible.created_at,
}


def list_responsibles(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    role: str | None,
    university_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[Responsible], int]:
    conds = []
    if search:
        pattern = like_pattern(search)
        conds.append(
            or_(
                Responsible.full_name.ilike(pattern, escape="\\"),
                Responsible.email.ilike(pattern, escape="\\"),
            )
        )
    if role is not None:
        conds.append(Responsible.role == role)
    if university_id is not None:
        conds.append(
            exists(
                select(1)
                .select_from(UniversityResponsible)
                .where(
                    UniversityResponsible.responsible_id == Responsible.id,
                    UniversityResponsible.university_id == university_id,
                )
            )
        )
    total = db.execute(select(func.count()).select_from(Responsible).where(*conds)).scalar() or 0
    rows = (
        db.execute(
            select(Responsible)
            .where(*conds)
            .order_by(*_order(Responsible, RESPONSIBLE_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_responsible(db: Session, responsible_id: uuid.UUID) -> Responsible | None:
    return db.get(Responsible, responsible_id)


def responsible_universities(db: Session, responsible_id: uuid.UUID) -> list[University]:
    """Universities linked to one responsible, ONE query."""
    return list(
        db.execute(
            select(University)
            .join(
                UniversityResponsible,
                UniversityResponsible.university_id == University.id,
            )
            .where(UniversityResponsible.responsible_id == responsible_id)
            .order_by(University.name.asc(), University.id.asc())
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------- links


def get_link(
    db: Session, university_id: uuid.UUID, responsible_id: uuid.UUID
) -> UniversityResponsible | None:
    return db.execute(
        select(UniversityResponsible).where(
            UniversityResponsible.university_id == university_id,
            UniversityResponsible.responsible_id == responsible_id,
        )
    ).scalar_one_or_none()


# ------------------------------------------------------------------ writes


def add_and_flush(db: Session, obj):
    """Persist a new row. IntegrityError bubbles to the central 409 handler."""
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def save(db: Session, obj):
    """Persist in-place mutations. IntegrityError bubbles to the 409 handler."""
    db.commit()
    db.refresh(obj)
    return obj


def delete_by_id(db: Session, model, pk: uuid.UUID) -> None:
    """Hard DELETE through Core so the real DB ON DELETE policy applies.

    ORM ``db.delete()`` would first NULL loaded children's FKs (masking
    RESTRICT as a NOT NULL violation); Core DELETE probes the true
    RESTRICT/CASCADE/SET NULL contract. IntegrityError -> central 409.
    """
    db.expunge_all()
    db.execute(sa_delete(model).where(model.id == pk))
    db.commit()


def delete_link(db: Session, link: UniversityResponsible) -> None:
    db.delete(link)
    db.commit()


__all__ = [
    "RESPONSIBLE_SORT",
    "DIRECTION_SORT",
    "PRODUCT_SORT",
    "PROGRAM_SORT",
    "UNIVERSITY_SORT",
    "VENDOR_SORT",
    "add_and_flush",
    "delete_by_id",
    "delete_link",
    "direction_programs",
    "get_direction",
    "get_link",
    "get_product",
    "get_program",
    "get_responsible",
    "get_university",
    "get_vendor",
    "like_pattern",
    "list_directions",
    "list_products",
    "list_programs",
    "list_responsibles",
    "list_universities",
    "list_vendors",
    "responsible_universities",
    "save",
    "university_responsibles",
    "vendor_products",
]
