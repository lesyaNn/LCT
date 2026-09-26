"""P1-03 query layer: filtered/paginated/sorted SELECTs + writes.

All list queries are exactly 2 SELECTs (COUNT with the same WHERE, then the
page); many-to-one display names (direction_name, vendor_name) come from a
JOIN inside the page statement — never a query per item. Detail loaders use
1-2 constant statements. No business logic here, only query construction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import exists, func, inspect, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.policies import apply_university_scope
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
    VendorContact,
)
from app.models.health_score import HealthScoreCurrent
from app.modules.audit.service import AuditAction, AuditService, context_for

_AUDIT_FIELDS = {
    University: ("name", "city"),
    ITDirection: ("code", "name"),
    ITProgram: ("direction_id", "name", "description"),
    Vendor: ("name",),
    ITProduct: ("vendor_id", "name", "version"),
    Responsible: ("full_name", "email", "phone", "role", "keycloak_sub"),
    UniversityResponsible: ("university_id", "responsible_id", "role_in_university", "is_primary"),
}

_AUDIT_ENTITY_TYPES = {
    University: "university",
    ITDirection: "direction",
    ITProgram: "program",
    Vendor: "vendor",
    ITProduct: "product",
    Responsible: "responsible",
    UniversityResponsible: "responsible",
}


def _audit_snapshot(obj):
    return {name: getattr(obj, name) for name in _AUDIT_FIELDS[type(obj)]}


def _audit_write(db: Session, obj, action: AuditAction, *, old=None, new=None):
    if "audit_context" not in db.info or type(obj) not in _AUDIT_FIELDS:
        return
    entity_type = _AUDIT_ENTITY_TYPES[type(obj)]
    university_id = obj.university_id if isinstance(obj, UniversityResponsible) else (
        obj.id if isinstance(obj, University) else None
    )
    AuditService(db).log_event(
        context=context_for(db), action=action, entity_type=entity_type,
        entity_id=obj.id, university_id=university_id,
        old_value=old, new_value=new,
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


def list_universities_health(
    db: Session, *, page: int, page_size: int, search: str | None,
    city: str | None, responsible_id: uuid.UUID | None, sort_order: str,
    health_status: str | None = None, unified_filter=None, unified_today=None,
    user=None, external_source: str | None = None,
) -> tuple[list[tuple[University, int | None, str | None]], int]:
    """SQL scoped health filter/order/page over the materialized projection."""
    conds = university_conditions(search=search, city=city,
        responsible_id=responsible_id, unified_filter=unified_filter,
        today=unified_today, external_source=external_source)
    base = select(University).outerjoin(
        HealthScoreCurrent, HealthScoreCurrent.university_id == University.id
    ).where(*conds)
    if health_status is not None:
        base = base.where(HealthScoreCurrent.status == health_status)
    count = select(func.count()).select_from(University).outerjoin(
        HealthScoreCurrent, HealthScoreCurrent.university_id == University.id
    ).where(*conds)
    if health_status is not None:
        count = count.where(HealthScoreCurrent.status == health_status)
    page_stmt = select(University, HealthScoreCurrent.score, HealthScoreCurrent.status).select_from(
        University
    ).outerjoin(HealthScoreCurrent, HealthScoreCurrent.university_id == University.id).where(*conds)
    if health_status is not None:
        page_stmt = page_stmt.where(HealthScoreCurrent.status == health_status)
    score = HealthScoreCurrent.score.asc() if sort_order == "asc" else HealthScoreCurrent.score.desc()
    page_stmt = page_stmt.order_by(score.nulls_last(), University.id.asc()).limit(page_size).offset((page - 1) * page_size)
    if user is not None:
        from app.modules.analytics.filter_service import UnifiedFilterService
        count = UnifiedFilterService.apply_security_scope(count, user)
        page_stmt = UnifiedFilterService.apply_security_scope(page_stmt, user)
    total = int(db.execute(count).scalar() or 0)
    rows = list(db.execute(page_stmt).all())
    return rows, total


def university_conditions(
    *,
    search: str | None,
    city: str | None,
    responsible_id: uuid.UUID | None,
    unified_filter=None,
    today=None,
    external_source: str | None = None,
):
    conds = []
    if external_source == "lms":
        from app.models.interactions import Student

        conds.append(exists(select(1).select_from(Student).where(
            Student.university_id == University.id, Student.source == "lms",
        )))
    elif external_source == "website":
        from app.models.external import ExternalApplication

        conds.append(exists(select(1).select_from(ExternalApplication).where(
            ExternalApplication.university_id == University.id,
            ExternalApplication.source == "website",
        )))
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
    user=None, external_source: str | None = None,
) -> tuple[list[University], int]:
    conds = university_conditions(
        search=search,
        city=city,
        responsible_id=responsible_id,
        unified_filter=unified_filter,
        today=unified_today,
        external_source=external_source,
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


def list_university_candidates(
    db: Session,
    *,
    search: str | None,
    city: str | None,
    responsible_id: uuid.UUID | None,
    unified_filter=None,
    unified_today=None,
    user=None,
) -> list[University]:
    """All universities matching the non-health filters (name asc, id asc).

    Used by the health_status/health_score path (P1-03-01): scores are
    computed in Python, so SQL pagination cannot apply — the caller
    filters/sorts/paginates in memory. Shares ``university_conditions``
    and the security scope with ``list_universities``.
    """
    conds = university_conditions(
        search=search,
        city=city,
        responsible_id=responsible_id,
        unified_filter=unified_filter,
        today=unified_today,
    )
    stmt = (
        select(University)
        .where(*conds)
        .order_by(University.name.asc(), University.id.asc())
    )
    if user is not None:
        from app.modules.analytics.filter_service import UnifiedFilterService

        stmt = UnifiedFilterService.apply_security_scope(stmt, user)
    return list(db.execute(stmt).scalars().all())


def get_university(db: Session, university_id: uuid.UUID) -> University | None:
    return db.get(University, university_id)


def get_university_scoped(db: Session, university_id: uuid.UUID, user) -> University | None:
    """H5: single scoped SELECT — missing and out-of-scope both yield None,
    so the router returns 404 without a second check query (no timing oracle
    between existing/foreign ids and no unscoped row load)."""
    return db.execute(
        apply_university_scope(
            select(University).where(University.id == university_id),
            University.id,
            user,
        )
    ).scalar_one_or_none()


# M4: unified university delete policy. DB-level ON DELETE is mixed
# (RESTRICT for licenses/contracts/teachers/students, CASCADE for workflow
# instances/meetings/documents/notes/links/snapshots), so a bare Core DELETE
# would silently wipe history while refusing on catalog rows. The service
# therefore pre-checks EVERYTHING and refuses with 409 while any business
# data references the university; the DB constraints stay as backstop.
_DELETE_REFERENCE_CHECKS: tuple[tuple[str, object, object], ...] = ()


def _delete_checks():
    """(label, model, university_fk) pairs, resolved lazily (import cycle)."""
    from app.models.interactions import (
        Document,
        InteractionNote,
        Meeting,
        Student,
        UniversityProduct,
        UniversityProgram,
    )
    from app.models.teachers import Teacher
    from app.models.workflow_instances import WorkflowInstance

    return (
        ("licenses", License, License.university_id),
        ("contracts", Contract, Contract.university_id),
        ("teachers", Teacher, Teacher.university_id),
        ("students", Student, Student.university_id),
        ("workflow instances", WorkflowInstance, WorkflowInstance.university_id),
        ("meetings", Meeting, Meeting.university_id),
        ("documents", Document, Document.university_id),
        ("interaction notes", InteractionNote, InteractionNote.university_id),
        ("university programs", UniversityProgram, UniversityProgram.university_id),
        ("university products", UniversityProduct, UniversityProduct.university_id),
        (
            "responsible links",
            UniversityResponsible,
            UniversityResponsible.university_id,
        ),
    )


def university_delete_blockers(db: Session, university_id: uuid.UUID) -> list[str]:
    """Labels of referencing data blocking a university hard-delete (M4)."""
    global _DELETE_REFERENCE_CHECKS
    if not _DELETE_REFERENCE_CHECKS:
        _DELETE_REFERENCE_CHECKS = _delete_checks()
    blockers = []
    for label, model, column in _DELETE_REFERENCE_CHECKS:
        present = db.execute(
            select(exists().where(column == university_id))
        ).scalar()
        if present:
            blockers.append(label)
    return blockers


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


def product_contacts(db: Session, product_id: uuid.UUID) -> list[VendorContact]:
    return list(db.scalars(
        select(VendorContact)
        .where(VendorContact.product_id == product_id)
        .order_by(VendorContact.full_name, VendorContact.id)
    ).all())


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


def vendor_contacts(db: Session, vendor_id: uuid.UUID) -> list[VendorContact]:
    return list(db.scalars(
        select(VendorContact)
        .where(VendorContact.vendor_id == vendor_id)
        .order_by(VendorContact.full_name, VendorContact.id)
    ).all())


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
    if "audit_context" in db.info and type(obj) in _AUDIT_FIELDS:
        db.flush()
        action = (AuditAction.ASSIGN_RESPONSIBLE if isinstance(obj, UniversityResponsible)
                  else AuditAction.CREATE)
        _audit_write(db, obj, action, new=_audit_snapshot(obj))
    db.commit()
    db.refresh(obj)
    return obj


def save(db: Session, obj):
    """Persist in-place mutations. IntegrityError bubbles to the 409 handler."""
    if "audit_context" in db.info and type(obj) in _AUDIT_FIELDS:
        current = _audit_snapshot(obj)
        old = dict(current)
        state = inspect(obj)
        for name in current:
            history = state.attrs[name].history
            if history.deleted:
                old[name] = history.deleted[0]
        if old != current:
            _audit_write(db, obj, AuditAction.UPDATE, old=old, new=current)
    db.commit()
    db.refresh(obj)
    return obj


def delete_by_id(db: Session, model, pk: uuid.UUID) -> None:
    """Hard DELETE through Core so the real DB ON DELETE policy applies.

    ORM ``db.delete()`` would first NULL loaded children's FKs (masking
    RESTRICT as a NOT NULL violation); Core DELETE probes the true
    RESTRICT/CASCADE/SET NULL contract. IntegrityError -> central 409.
    """
    obj = db.get(model, pk) if "audit_context" in db.info and model in _AUDIT_FIELDS else None
    old = _audit_snapshot(obj) if obj is not None else None
    db.expunge_all()
    db.execute(sa_delete(model).where(model.id == pk))
    if obj is not None:
        _audit_write(db, obj, AuditAction.DELETE, old=old)
    db.commit()


def delete_link(db: Session, link: UniversityResponsible) -> None:
    old = _audit_snapshot(link) if "audit_context" in db.info else None
    db.delete(link)
    if old is not None:
        _audit_write(db, link, AuditAction.ASSIGN_RESPONSIBLE, old=old)
    db.commit()


# ------------------------------------------------------- catalog overview


def count_overview(db: Session, user) -> tuple[int, int]:
    """Scoped totals for the overview header (H4: both counts respect scope)."""
    total_universities = db.execute(apply_university_scope(
        select(func.count()).select_from(University), University.id, user
    )).scalar() or 0
    total_licenses = db.execute(apply_university_scope(
        select(func.count()).select_from(License), License.university_id, user
    )).scalar() or 0
    return total_universities, total_licenses


def page_overview_licenses(db: Session, user, *, limit: int, offset: int):
    """Scoped license page with all display relations eager (H4).

    Nested ``product.vendor`` and ``link.responsible`` are eager too — the
    previous router-inline version lazy-loaded them per row (N+1).
    """
    from app.models.interactions import UniversityProgram

    return (
        db.execute(
            apply_university_scope(select(License), License.university_id, user)
            .options(
                selectinload(License.university).selectinload(
                    University.university_responsibles
                ).selectinload(UniversityResponsible.responsible),
                selectinload(License.university).selectinload(
                    University.university_programs
                ).selectinload(UniversityProgram.program).selectinload(
                    ITProgram.direction
                ),
                selectinload(License.product).selectinload(ITProduct.vendor),
                selectinload(License.contract),
                selectinload(License.program).selectinload(ITProgram.direction),
                selectinload(License.direction),
            )
            .order_by(License.expires_at)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )


def direction_program_counts(db: Session, user) -> tuple[list, dict[str, int]]:
    """Reference direction list + per-direction program counts (H4).

    The direction list itself is global reference data (filter dropdowns need
    it whole); the COUNTS are scoped to in-scope universities via a single
    GROUP BY instead of loading every program row into Python.
    """
    from app.models.interactions import UniversityProgram

    directions = (
        db.execute(select(ITDirection).order_by(ITDirection.code)).scalars().all()
    )
    counts = dict(
        db.execute(
            apply_university_scope(
                select(ITProgram.direction_id, func.count(ITProgram.id))
                .select_from(ITProgram)
                .join(
                    UniversityProgram,
                    UniversityProgram.program_id == ITProgram.id,
                ),
                UniversityProgram.university_id,
                user,
            ).group_by(ITProgram.direction_id)
        ).all()
    )
    return list(directions), {str(k): v for k, v in counts.items()}


__all__ = [
    "RESPONSIBLE_SORT",
    "DIRECTION_SORT",
    "PRODUCT_SORT",
    "PROGRAM_SORT",
    "UNIVERSITY_SORT",
    "VENDOR_SORT",
    "add_and_flush",
    "count_overview",
    "delete_by_id",
    "delete_link",
    "direction_program_counts",
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
    "page_overview_licenses",
    "responsible_universities",
    "save",
    "university_delete_blockers",
    "university_responsibles",
    "vendor_products",
]
