"""P1-03 query layer: filtered/paginated/sorted SELECTs + writes.

All list queries are exactly 2 SELECTs (COUNT with the same WHERE, then the
page); many-to-one display names (direction_name, vendor_name) come from a
JOIN inside the page statement — never a query per item. Detail loaders use
1-2 constant statements. No business logic here, only query construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import and_, delete as sa_delete
from sqlalchemy import exists, func, inspect, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.policies import apply_university_scope
from app.models.enums import EXPIRY_WARNING_DAYS
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
    VendorContact,
)
from app.modules.audit.service import AuditAction, AuditService, context_for

_AUDIT_FIELDS = {
    University: ("name", "city"),
    ITDirection: ("code", "name"),
    ITProgram: ("direction_id", "name", "description"),
    Vendor: ("name",),
    ITProduct: ("vendor_id", "name", "version"),
    Responsible: ("full_name", "email", "phone", "role", "keycloak_sub"),
    UniversityResponsible: ("university_id", "responsible_id", "role_in_university", "is_primary"),
    Contract: (
        "university_id", "contract_number", "product_id", "signed_at",
        "expires_at", "status_raw", "transfer_status_raw", "comment",
    ),
    License: (
        "university_id", "product_id", "contract_id", "program_id", "direction_id",
        "license_number", "signed_at", "expires_at", "transfer_status_raw", "comment",
    ),
}

_AUDIT_ENTITY_TYPES = {
    University: "university",
    ITDirection: "direction",
    ITProgram: "program",
    Vendor: "vendor",
    ITProduct: "product",
    Responsible: "responsible",
    UniversityResponsible: "responsible",
    Contract: "contract",
    License: "license",
}


def _audit_snapshot(obj):
    return {name: getattr(obj, name) for name in _AUDIT_FIELDS[type(obj)]}


def _snapshot_display_names(db: Session, snapshot: dict | None) -> dict | None:
    """Add human-readable ``*_name`` siblings next to raw FK ids.

    Best-effort: any lookup failure leaves the snapshot untouched so the
    business write never breaks because of audit enrichment.
    """
    if not snapshot:
        return snapshot
    enriched = dict(snapshot)
    try:
        direction_id = snapshot.get("direction_id")
        if direction_id is not None and "direction_name" not in enriched:
            direction = db.get(ITDirection, direction_id)
            if direction is not None:
                enriched["direction_name"] = direction.name
        vendor_id = snapshot.get("vendor_id")
        if vendor_id is not None and "vendor_name" not in enriched:
            vendor = db.get(Vendor, vendor_id)
            if vendor is not None:
                enriched["vendor_name"] = vendor.name
        responsible_id = snapshot.get("responsible_id")
        if responsible_id is not None and "responsible_name" not in enriched:
            responsible = db.get(Responsible, responsible_id)
            if responsible is not None:
                enriched["responsible_name"] = responsible.full_name
        university_id = snapshot.get("university_id")
        if university_id is not None and "university_name" not in enriched:
            university = db.get(University, university_id)
            if university is not None:
                enriched["university_name"] = university.name
    except Exception:
        return snapshot
    return enriched


def _audit_write(db: Session, obj, action: AuditAction, *, old=None, new=None):
    if "audit_context" not in db.info or type(obj) not in _AUDIT_FIELDS:
        return
    entity_type = _AUDIT_ENTITY_TYPES[type(obj)]
    # Contracts and licenses are university-scoped too, so the audit row keeps
    # the university for scope-filtered audit views.
    university_id = obj.university_id if isinstance(
        obj, (UniversityResponsible, Contract, License)
    ) else (obj.id if isinstance(obj, University) else None)
    AuditService(db).log_event(
        context=context_for(db), action=action, entity_type=entity_type,
        entity_id=obj.id, university_id=university_id,
        old_value=_snapshot_display_names(db, old),
        new_value=_snapshot_display_names(db, new),
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
    db, *, page: int, page_size: int, search: str | None,
    city: str | None, responsible_id=None, sort_order: str = "asc",
    health_status: str | None = None, unified_filter=None, unified_today=None,
    user=None, external_source: str | None = None,
) -> tuple[list[tuple], int]:
    """Plain university list (health score removed)."""
    conds = university_conditions(search=search, city=city,
        responsible_id=responsible_id, unified_filter=unified_filter,
        today=unified_today, external_source=external_source)
    count = select(func.count()).select_from(University).where(*conds)
    page_stmt = select(University).where(*conds).order_by(University.name.asc(), University.id.asc()).limit(page_size).offset((page - 1) * page_size)
    if user is not None:
        from app.modules.analytics.filter_service import UnifiedFilterService
        count = UnifiedFilterService.apply_security_scope(count, user)
        page_stmt = UnifiedFilterService.apply_security_scope(page_stmt, user)
    total = int(db.execute(count).scalar() or 0)
    unis = list(db.execute(page_stmt).scalars().all())
    rows = [(u, None, None) for u in unis]
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
    if external_source == "website":
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


def university_list_presentation(
    db: Session,
    university_ids: Sequence[uuid.UUID],
    *,
    today: date | None = None,
) -> dict[uuid.UUID, dict]:
    """Batched presentation aggregates for one universities page (no N+1).

    Returns ``{university_id: {responsible, programs_count,
    program_status_counts, current_stage, last_interaction_at, attention}}``.
    Every relation is loaded with one GROUP BY / filtered SELECT over the
    whole page (constant ~8 SELECTs, never per-row). Missing relations yield
    None/0/False. Reuses the frozen business rules: primary responsible from
    ``university_responsibles.is_primary``; last interaction as
    GREATEST(max meetings, max notes) (P4-02-02 FULL); attention as the
    existing P2 overdue signal (overdue open stage or overdue open task on
    an ACTIVE instance, ``due < today`` canonical rule).
    """
    from app.models.interactions import InteractionNote, Meeting, UniversityProgram
    from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask

    result: dict[uuid.UUID, dict] = {
        uid: {
            "responsible": None,
            "programs_count": 0,
            "program_status_counts": {},
            "current_stage": None,
            "last_interaction_at": None,
            "attention": False,
        }
        for uid in university_ids
    }
    if not university_ids:
        return result
    day = today if today is not None else date.today()

    # 1. Primary responsible: is_primary first, then alphabetical (ONE query).
    resp_rows = db.execute(
        select(
            UniversityResponsible.university_id,
            Responsible,
            UniversityResponsible.is_primary,
        )
        .join(Responsible, Responsible.id == UniversityResponsible.responsible_id)
        .where(UniversityResponsible.university_id.in_(list(university_ids)))
        .order_by(
            UniversityResponsible.university_id,
            UniversityResponsible.is_primary.desc(),
            Responsible.full_name.asc(),
        )
    ).all()
    seen_resp: set[uuid.UUID] = set()
    for uni_id, resp, primary in resp_rows:
        if uni_id not in seen_resp and uni_id in result:
            result[uni_id]["responsible"] = (resp, bool(primary))
            seen_resp.add(uni_id)

    # 2. Programs GROUP BY status (ONE query).
    for uni_id, status, count in db.execute(
        select(
            UniversityProgram.university_id,
            UniversityProgram.status,
            func.count(UniversityProgram.id),
        )
        .where(UniversityProgram.university_id.in_(list(university_ids)))
        .group_by(UniversityProgram.university_id, UniversityProgram.status)
    ).all():
        if uni_id in result:
            result[uni_id]["program_status_counts"][status] = int(count)
            result[uni_id]["programs_count"] += int(count)

    # 3-4. Latest workflow instance per university + its current stage name.
    inst_rows = db.execute(
        select(
            WorkflowInstance.university_id,
            WorkflowInstance.id,
            WorkflowInstance.current_instance_stage_id,
        )
        .where(WorkflowInstance.university_id.in_(list(university_ids)))
        .order_by(WorkflowInstance.updated_at.desc(), WorkflowInstance.id.asc())
    ).all()
    latest: dict[uuid.UUID, tuple] = {}
    for uni_id, inst_id, stage_id in inst_rows:
        if uni_id not in latest:
            latest[uni_id] = (inst_id, stage_id)
    stage_ids = [sid for _, sid in latest.values() if sid is not None]
    stage_names: dict = {}
    if stage_ids:
        stage_names = {
            sid: name
            for sid, name in db.execute(
                select(InstanceStage.id, InstanceStage.name).where(
                    InstanceStage.id.in_(stage_ids)
                )
            ).all()
        }
    for uni_id, (inst_id, stage_id) in latest.items():
        name = stage_names.get(stage_id)
        if uni_id in result and name:
            result[uni_id]["current_stage"] = {"code": str(stage_id), "name": name}

    # 5-6. Last interaction = GREATEST(max meetings, max notes) (TWO queries).
    last: dict[uuid.UUID, object] = {}
    for uni_id, moment in db.execute(
        select(Meeting.university_id, func.max(Meeting.meeting_at))
        .where(Meeting.university_id.in_(list(university_ids)))
        .group_by(Meeting.university_id)
    ).all():
        if moment is not None:
            last[uni_id] = moment
    for uni_id, moment in db.execute(
        select(InteractionNote.university_id, func.max(InteractionNote.created_at))
        .where(InteractionNote.university_id.in_(list(university_ids)))
        .group_by(InteractionNote.university_id)
    ).all():
        if moment is not None and (uni_id not in last or moment > last[uni_id]):
            last[uni_id] = moment
    for uni_id, moment in last.items():
        if uni_id in result:
            result[uni_id]["last_interaction_at"] = moment

    # 7-8. Attention = overdue open stage OR overdue open task (P2 rule).
    overdue_unis: set[uuid.UUID] = set()
    for (uni_id,) in db.execute(
        select(WorkflowInstance.university_id)
        .join(
            InstanceStage,
            InstanceStage.instance_id == WorkflowInstance.id,
        )
        .where(
            WorkflowInstance.university_id.in_(list(university_ids)),
            WorkflowInstance.status == "active",
            InstanceStage.completed_at.is_(None),
            InstanceStage.status.notin_(["completed", "skipped"]),
            InstanceStage.due_date.is_not(None),
            InstanceStage.due_date < day,
        )
        .group_by(WorkflowInstance.university_id)
    ).all():
        overdue_unis.add(uni_id)
    for (uni_id,) in db.execute(
        select(WorkflowInstance.university_id)
        .join(WorkflowTask, WorkflowTask.instance_id == WorkflowInstance.id)
        .where(
            WorkflowInstance.university_id.in_(list(university_ids)),
            WorkflowInstance.status == "active",
            WorkflowTask.status == "open",
            WorkflowTask.deadline.is_not(None),
            WorkflowTask.deadline < day,
        )
        .group_by(WorkflowInstance.university_id)
    ).all():
        overdue_unis.add(uni_id)
    for uni_id in overdue_unis:
        if uni_id in result:
            result[uni_id]["attention"] = True

    return result


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
# (RESTRICT for licenses/contracts, CASCADE for workflow
# instances/meetings/documents/notes/links), so a bare Core DELETE
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
        UniversityProduct,
        UniversityProgram,
    )
    from app.models.workflow_instances import WorkflowInstance

    return (
        ("licenses", License, License.university_id),
        ("contracts", Contract, Contract.university_id),
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
    direction_id: uuid.UUID | None = None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[tuple], int]:
    """Page rows are (ITProduct, vendor_name, program_name) tuples — JOINs, no N+1."""
    conds = []
    if search:
        conds.append(ITProduct.name.ilike(like_pattern(search), escape="\\"))
    if vendor_id is not None:
        conds.append(ITProduct.vendor_id == vendor_id)
    from_clause = ITProduct
    if direction_id is not None:
        conds.append(
            exists().where(
                (ProductDirection.product_id == ITProduct.id)
                & (ProductDirection.direction_id == direction_id)
            )
        )
    total = db.execute(select(func.count()).select_from(from_clause).where(*conds)).scalar() or 0
    rows = list(
        db.execute(
            select(ITProduct, Vendor.name, ITProgram.name)
            .join(Vendor, Vendor.id == ITProduct.vendor_id)
            .outerjoin(ITProgram, ITProgram.id == ITProduct.program_id)
            .where(*conds)
            .order_by(*_order(ITProduct, PRODUCT_SORT, sort_by, sort_order))
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
    )
    return rows, int(total)


def get_product(db: Session, product_id: uuid.UUID) -> tuple | None:
    """(ITProduct, Vendor|None, ITProgram|None), ONE statement."""
    return db.execute(
        select(ITProduct, Vendor, ITProgram)
        .outerjoin(Vendor, Vendor.id == ITProduct.vendor_id)
        .outerjoin(ITProgram, ITProgram.id == ITProduct.program_id)
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


def responsible_universities_by_id(
    db: Session, responsible_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[University]]:
    """Universities for a whole page of responsibles, ONE query (no N+1).

    Returns a map responsible_id -> universities, keeping the per-responsible
    order of responsible_universities (name asc, id asc) so the list and the
    detail endpoint agree.
    """
    ids = list(dict.fromkeys(responsible_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(UniversityResponsible.responsible_id, University)
        .join(University, University.id == UniversityResponsible.university_id)
        .where(UniversityResponsible.responsible_id.in_(ids))
        .order_by(
            UniversityResponsible.responsible_id.asc(),
            University.name.asc(),
            University.id.asc(),
        )
    ).all()
    grouped: dict[uuid.UUID, list[University]] = {}
    for responsible_id, university in rows:
        grouped.setdefault(responsible_id, []).append(university)
    return grouped


# ------------------------------------------------------------------- links


# ------------------------------------------------------------- agreements
#
# Contracts and licenses are university-scoped business records (P1-06-01).
# ``vendor`` is resolved through ``product`` - there is deliberately no
# ``vendor_id`` column on Contract. Both lists scope by university_id so a
# manager never sees rows outside their universities.


CONTRACT_SORT = {
    "contract_number": Contract.contract_number,
    "signed_at": Contract.signed_at,
    "expires_at": Contract.expires_at,
    "created_at": Contract.created_at,
}

LICENSE_SORT = {
    "license_number": License.license_number,
    "signed_at": License.signed_at,
    "expires_at": License.expires_at,
    "created_at": License.created_at,
}


def _agreement_names(db: Session, model) -> dict[uuid.UUID, str]:
    """id -> label for every entity an agreement can point at, ONE query each.

    The agreement tables keep only FK ids; the list endpoint needs the labels
    to render, and per-row lookups would be N+1. Contracts are included so a
    license can show its contract number.
    """
    out: dict[uuid.UUID, str] = {}
    for entity, column in (
        (University, University.name),
        (ITProduct, ITProduct.name),
        (ITDirection, ITDirection.name),
        (ITProgram, ITProgram.name),
        (Vendor, Vendor.name),
        (Contract, Contract.contract_number),
    ):
        for row in db.execute(select(entity.id, column)).all():
            out[row[0]] = row[1]
    return out


def _vendor_id_by_product(db: Session) -> dict[uuid.UUID, uuid.UUID]:
    """product_id -> vendor_id, ONE query (Contract has no vendor column)."""
    return dict(db.execute(select(ITProduct.id, ITProduct.vendor_id)).all())


def contract_license_counts(db: Session, contract_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Licenses per contract for a whole page, ONE query (no N+1)."""
    ids = list(dict.fromkeys(contract_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(License.contract_id, func.count(License.id))
        .where(License.contract_id.in_(ids))
        .group_by(License.contract_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows if row[0] is not None}


def list_contracts(
    db: Session, *, page: int, page_size: int, search: str | None,
    university_id: uuid.UUID | None, product_id: uuid.UUID | None,
    status: str | None, sort_by: str, sort_order: str, user=None,
) -> tuple[list[Contract], int]:
    conds = []
    if search:
        conds.append(Contract.contract_number.ilike(like_pattern(search), escape="\\"))
    if university_id is not None:
        conds.append(Contract.university_id == university_id)
    if product_id is not None:
        conds.append(Contract.product_id == product_id)
    if status is not None:
        # Derived status lives in a @property, so the filter is expressed on
        # the raw state plus the date window the property reads.
        if status == "terminated":
            conds.append(Contract.status_raw == "terminated")
        elif status == "draft":
            conds.append(Contract.status_raw == "draft")
        elif status == "expired":
            conds.append(
                and_(
                    Contract.status_raw != "terminated",
                    Contract.status_raw != "draft",
                    Contract.expires_at.is_not(None),
                    Contract.expires_at < date.today(),
                )
            )
        else:
            conds.append(
                and_(
                    Contract.status_raw.notin_(("terminated", "draft")),
                    or_(
                        Contract.expires_at.is_(None),
                        Contract.expires_at >= date.today(),
                    ),
                )
            )
    count = apply_university_scope(
        select(func.count()).select_from(Contract).where(*conds), Contract.university_id, user
    ) if user is not None else select(func.count()).select_from(Contract).where(*conds)
    total = int(db.execute(count).scalar() or 0)
    stmt = select(Contract).where(*conds)
    if user is not None:
        stmt = apply_university_scope(stmt, Contract.university_id, user)
    rows = db.execute(
        stmt.order_by(*_order(Contract, CONTRACT_SORT, sort_by, sort_order))
        .limit(page_size).offset((page - 1) * page_size)
    ).scalars().all()
    return list(rows), total


def get_contract(db: Session, contract_id: uuid.UUID) -> Contract | None:
    return db.get(Contract, contract_id)


def contract_by_number(db: Session, contract_number: str) -> Contract | None:
    return db.execute(
        select(Contract).where(Contract.contract_number == contract_number)
    ).scalar_one_or_none()


def contract_licenses(db: Session, contract_id: uuid.UUID) -> list[License]:
    """Licenses of one contract, ONE query."""
    return list(
        db.execute(
            select(License)
            .where(License.contract_id == contract_id)
            .order_by(License.signed_at.desc(), License.id.asc())
        )
        .scalars()
        .all()
    )


def list_licenses(
    db: Session, *, page: int, page_size: int, search: str | None,
    university_id: uuid.UUID | None, product_id: uuid.UUID | None,
    status: str | None, sort_by: str, sort_order: str, user=None,
) -> tuple[list[License], int]:
    conds = []
    if search:
        conds.append(License.license_number.ilike(like_pattern(search), escape="\\"))
    if university_id is not None:
        conds.append(License.university_id == university_id)
    if product_id is not None:
        conds.append(License.product_id == product_id)
    if status is not None:
        if status == "expired":
            conds.append(License.expires_at < date.today())
        elif status == "expires_soon":
            conds.append(and_(
                License.expires_at >= date.today(),
                License.expires_at <= date.today() + timedelta(days=EXPIRY_WARNING_DAYS),
            ))
        else:
            conds.append(License.expires_at > date.today() + timedelta(days=EXPIRY_WARNING_DAYS))
    count = apply_university_scope(
        select(func.count()).select_from(License).where(*conds), License.university_id, user
    ) if user is not None else select(func.count()).select_from(License).where(*conds)
    total = int(db.execute(count).scalar() or 0)
    stmt = select(License).where(*conds)
    if user is not None:
        stmt = apply_university_scope(stmt, License.university_id, user)
    rows = db.execute(
        stmt.order_by(*_order(License, LICENSE_SORT, sort_by, sort_order))
        .limit(page_size).offset((page - 1) * page_size)
    ).scalars().all()
    return list(rows), total


def get_license(db: Session, license_id: uuid.UUID) -> License | None:
    return db.get(License, license_id)


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
