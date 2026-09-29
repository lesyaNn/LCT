"""P1-04 passport DTO assembly + public block getters + get_passport.

Moved verbatim from ``passport_service`` (M1 god-file split): assemblers map
loaded rows to response DTOs; SQL stays in ``passport_loading``.
No behavior change.
"""

from __future__ import annotations

import enum
import logging
import uuid
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.core.errors import BusinessException
from app.config import settings
from app.core.exceptions import NotFound
from app.schemas.errors import ErrorCode
from app.models.catalog import Contract, ITDirection, ITProgram, License, Responsible
from app.models.enums import EXPIRY_WARNING_DAYS, UniversityProductStatus, UniversityProgramStatus
from app.models.interactions import Document, InteractionNote, Meeting, UniversityProgram
from app.modules.audit.service import AuditService
from app.modules.universities.passport_loading import (
    AUDIT_LIMIT,
    DOCUMENTS_LIMIT,
    MEETINGS_LIMIT,
    TIMELINE_LIMIT,
    TIMELINE_PER_SOURCE_LIMIT,
    PassportLoadContext,
    _load_interaction_rows,
    _load_license_contract_rows,
    _load_product_rows,
    _load_program_rows,
    _load_responsible_rows,
    _load_university_row,
)
from app.modules.universities.passport_schemas import (
    AuditEventShort,
    ContractShort,
    DocumentShort,
    LicenseShort,
    MeetingShort,
    ProductShort,
    ProgramShort,
    ResponsibleShort,
    TimelineItem,
    UniversityBrief,
    UniversityPassport,
    WorkflowSummary,
)

logger = logging.getLogger(__name__)

class PassportInclude(str, enum.Enum):
    """Allowed ``?include=`` blocks for the passport endpoint."""

    AUDIT = "audit"


def parse_include(raw: str | None) -> frozenset[PassportInclude]:
    """Centralized ``?include=`` parsing (single place, no string matching).

    Normalizes surrounding whitespace, accepts any order
    (``audit`` alone), tolerates empty
    segments (``include=`` / trailing commas). Unknown tokens raise 422
    (project validation-error style) instead of being silently ignored.
    """
    if raw is None or not raw.strip():
        return frozenset()
    blocks: set[PassportInclude] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            blocks.add(PassportInclude(token))
        except ValueError:
            raise BusinessException(ErrorCode.VALIDATION_ERROR)
    return frozenset(blocks)


def _ensure_tz(dt: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime (project UTC/ISO-8601 convention).

    Never blindly ``replace(tzinfo=...)`` on ambiguous data: naive values
    coming from SQLite (which cannot store tzinfo) are interpreted as UTC —
    the only timezone the seed and the app ever write
    (``datetime.now(timezone.utc)``). PostgreSQL ``timestamptz`` already
    returns aware values and passes through untouched.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _participants_to_strs(raw: object) -> list[str]:
    """Coerce Meeting.participants JSONB to list[str] without assumptions.

    Real format (seed/model): list of ``{"name": ..., "role": ...}`` objects.
    Tolerates plain strings, missing keys and NULL.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, (list, tuple)):
        return [str(raw)]
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            if item:
                out.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("full_name") or item.get("email")
            if name:
                out.append(str(name))
            else:
                out.append(str(item))
        elif item is not None:
            out.append(str(item))
    return out



# ---------------------------------------------------------- assemblers ---


def _assemble_programs(
    program_rows: list[tuple],
) -> list[ProgramShort]:
    out: list[ProgramShort] = []
    for link, program, direction, responsible in program_rows:
        try:
            status = UniversityProgramStatus(link.status)
        except ValueError:
            status = UniversityProgramStatus.PLANNED
        out.append(
            ProgramShort(
                id=program.id,
                name=program.name,
                direction_name=direction.name if direction is not None else "",
                status=status,
                launch_date=link.launch_date,
                responsible_name=responsible.full_name if responsible else None,
            )
        )
    return out


def _license_short_from_row(row: dict) -> LicenseShort:
    """LicenseShort from a block-6 UNION row (derived status via the model)."""
    transient = License(
        product_id=row["product_id"],
        signed_at=row["signed_at"],
        expires_at=row["expires_at"],
        transfer_status_raw=row["transfer_status"] or "",
    )
    return LicenseShort(
        id=row["id"],
        license_number=row["num"] or "",
        product_name=row["product_name"] or "",
        vendor_name=row["vendor_name"] or "",
        signed_at=row["signed_at"],
        expires_at=row["expires_at"],
        status=transient.derived_status,
        transfer_status=row["transfer_status"] or "",
        days_to_expiry=transient.days_to_expiry,
        contract_number=row["contract_number"],
    )


def _assemble_products_licenses_contracts(
    product_rows: list[tuple], license_contract_rows: list[dict]
):
    """Assemble products/licenses/contracts from blocks 5+6.

    License choice rule (unchanged, documented): ProductShort.license is
    the ``university_products.license_id`` link when set, otherwise the
    active non-expired license of the same product with the nearest
    ``expires_at``; ``None`` when the university holds no license at all.
    Ordering: licenses ``expires_at`` ASC, contracts ``signed_at`` DESC,
    products by product name.
    """
    lic_rows = [r for r in license_contract_rows if r["kind"] == "license"]
    con_rows = [r for r in license_contract_rows if r["kind"] == "contract"]

    licenses = [_license_short_from_row(r) for r in lic_rows]
    licenses.sort(key=lambda lic: lic.expires_at)
    license_by_id = {lic.id: lic for lic in licenses}

    licenses_by_contract: dict[uuid.UUID, list[dict]] = defaultdict(list)
    vendor_by_product: dict[uuid.UUID, str] = {}
    for r in lic_rows:
        vendor_by_product.setdefault(r["product_id"], r["vendor_name"] or "")
        if r["contract_id"] is not None:
            licenses_by_contract[r["contract_id"]].append(r)
    for r in con_rows:
        if r["product_id"] is not None:
            vendor_by_product.setdefault(r["product_id"], r["vendor_name"] or "")

    today = date.today()
    # NOTE: fallback follows licenses ASC order (nearest expiry first).
    fallback_by_product: dict[uuid.UUID, LicenseShort] = {}
    for r in sorted(lic_rows, key=lambda r: r["expires_at"]):
        if r["expires_at"] >= today and r["product_id"] not in fallback_by_product:
            lic = license_by_id.get(r["id"])
            if lic is not None:
                fallback_by_product[r["product_id"]] = lic

    products_out: list[ProductShort] = []
    for up, product, vendor in sorted(product_rows, key=lambda t: t[1].name):
        try:
            status = UniversityProductStatus(up.status)
        except ValueError:
            status = UniversityProductStatus.PLANNED
        chosen: LicenseShort | None = None
        if up.license_id is not None:
            chosen = license_by_id.get(up.license_id)
        if chosen is None:
            chosen = fallback_by_product.get(up.product_id)
        products_out.append(
            ProductShort(
                id=up.product_id,
                name=product.name,
                version=product.version or "",
                vendor_name=vendor.name if vendor is not None else "",
                status=status,
                license=chosen,
            )
        )

    contracts: list[ContractShort] = []
    for r in sorted(con_rows, key=lambda r: r["signed_at"], reverse=True):
        transient = Contract(
            signed_at=r["signed_at"],
            expires_at=r["expires_at"],
            status_raw=r["status_raw"] or "",
            transfer_status_raw=r["transfer_status"] or "",
        )
        vendor_name = ""
        if r["product_id"] is not None:
            vendor_name = vendor_by_product.get(r["product_id"], "") or r["vendor_name"] or ""
        if not vendor_name:
            for linked in licenses_by_contract.get(r["id"], []):
                vendor_name = vendor_by_product.get(linked["product_id"], "")
                if vendor_name:
                    break
        contracts.append(
            ContractShort(
                id=r["id"],
                contract_number=r["num"] or "",
                signed_at=r["signed_at"],
                expires_at=r["expires_at"],
                status=transient.derived_status,
                vendor_name=vendor_name,
            )
        )
    return products_out, licenses, contracts


def _document_short_from_row(row: dict) -> DocumentShort:
    return DocumentShort(
        id=row["id"],
        document_type=row["ctype"] or "",
        title=row["title"] or "",
        file_name=row["file_name"] or "",
        file_size=int(row["file_size"] or 0),
        mime_type=row["mime"] or "",
        signed_at=row["signed_at"],
        expires_at=row["expires_at"],
        status=row["status_raw"] or "",
        uploaded_by=row["author"] or "",
        created_at=_ensure_tz(row["ts"]),
    )


def _meeting_short_from_row(row: dict) -> MeetingShort:
    return MeetingShort(
        id=row["id"],
        meeting_type=row["ctype"] or "",
        subject=row["title"] or "",
        participants=_participants_to_strs(row["participants"]),
        outcome=row["extra1"],
        next_action=row["extra2"],
        next_action_due=row["due"],
        meeting_at=_ensure_tz(row["ts"]),
        created_by=row["author"] or "",
    )


def _assemble_documents_meetings(
    interaction_rows: list[dict],
) -> tuple[list[DocumentShort], list[MeetingShort], list[dict]]:
    """Split block 7 into documents, meetings and raw note rows."""
    documents = [_document_short_from_row(r) for r in interaction_rows if r["kind"] == "document"]
    meetings = [_meeting_short_from_row(r) for r in interaction_rows if r["kind"] == "meeting"]
    notes = [r for r in interaction_rows if r["kind"] == "note"]
    return documents, meetings, notes


def _compose_timeline(
    documents: list[DocumentShort],
    meetings: list[MeetingShort],
    note_rows: list[dict],
) -> list[TimelineItem]:
    """Pure timeline merge over already-loaded rows (zero SQL)."""
    items: list[TimelineItem] = []
    for d in documents[:TIMELINE_PER_SOURCE_LIMIT]:
        items.append(
            TimelineItem(
                id=str(d.id),
                type="document",
                title=d.title,
                description=f"{d.document_type}: {d.file_name}",
                author=d.uploaded_by,
                created_at=d.created_at,
            )
        )
    for m in meetings[:TIMELINE_PER_SOURCE_LIMIT]:
        items.append(
            TimelineItem(
                id=str(m.id),
                type="meeting",
                title=m.subject,
                description=m.outcome,
                author=m.created_by,
                created_at=m.meeting_at,
            )
        )
    for n in note_rows:
        content = n["title"] or ""
        items.append(
            TimelineItem(
                id=str(n["id"]),
                type="note",
                title=(content[:80] if content else "Заметка"),
                description=content,
                author=n["author"] or "",
                created_at=_ensure_tz(n["ts"]),
            )
        )
    items.extend(get_workflow_transitions_raw())
    items.sort(key=lambda i: i.created_at, reverse=True)
    return items[:TIMELINE_LIMIT]


def get_workflow_transitions_raw() -> list[TimelineItem]:
    """P2 integration point — returns [] until P2 tables are available."""
    return []


# ------------------------------------------------------------- P1-04-02 ---


def get_programs(db, university_id) -> list[ProgramShort]:
    """Batch-load university programs (no N+1)."""
    program_rows = _load_program_rows(db, university_id)
    if not program_rows:
        return []
    return _assemble_programs(program_rows)


# ------------------------------------------------------------- P1-04-03 ---


def get_products_licenses_contracts(db, university_id: uuid.UUID):
    """Batch-load university_products/products/vendors/licenses/contracts.

    Returns ``(products, licenses, contracts)`` DTO lists (2 statements:
    blocks 5+6). License choice rule (documented, no arbitrary pick):
    ProductShort.license is the ``university_products.license_id`` link
    when set, otherwise the active non-expired license of the same
    product with the nearest ``expires_at``; ``None`` when the university
    holds no license at all.
    """
    product_rows = _load_product_rows(db, university_id)
    license_contract_rows = _load_license_contract_rows(db, university_id)
    return _assemble_products_licenses_contracts(product_rows, license_contract_rows)


# ------------------------------------------------------------- P1-04-04 ---


def get_documents(db, university_id: uuid.UUID) -> list[DocumentShort]:
    rows = (
        db.execute(
            select(Document)
            .where(Document.university_id == university_id, Document.contract_id.is_(None), Document.license_id.is_(None))
            .order_by(Document.created_at.desc())
            .limit(DOCUMENTS_LIMIT)
        )
        .scalars()
        .all()
    )
    return [
        DocumentShort(
            id=d.id,
            document_type=d.document_type,
            title=d.title,
            file_name=d.file_name,
            file_size=d.file_size or 0,
            mime_type=d.mime_type or "",
            signed_at=d.signed_at,
            expires_at=d.expires_at,
            status=d.status_raw,
            uploaded_by=d.uploaded_by_keycloak_sub,
            created_at=_ensure_tz(d.created_at),
        )
        for d in rows
    ]


def get_documents_page(
    db, university_id: uuid.UUID, page: int, page_size: int,
    *, search: str | None = None, document_type: str | None = None,
    status: str | None = None,
) -> tuple[list[DocumentShort], int, list[str]]:
    conditions = [Document.university_id == university_id, Document.contract_id.is_(None), Document.license_id.is_(None)]
    types = db.scalars(select(Document.document_type).where(*conditions).distinct().order_by(Document.document_type)).all()
    if search:
        from app.modules.catalog.repository import like_pattern
        pattern = like_pattern(search.strip())
        conditions.append(Document.title.ilike(pattern, escape="\\") | Document.file_name.ilike(pattern, escape="\\"))
    if document_type:
        conditions.append(Document.document_type == document_type)
    if status:
        if status == "expired":
            conditions.extend((Document.expires_at < date.today(), Document.status_raw != "archived"))
        elif status == "signed":
            conditions.extend((Document.status_raw == "signed", (Document.expires_at.is_(None) | (Document.expires_at >= date.today()))))
        elif status == "pending":
            conditions.extend((Document.status_raw.in_(("draft", "pending")), (Document.expires_at.is_(None) | (Document.expires_at >= date.today()))))
        else:
            conditions.append(Document.status_raw == status)
    total = db.scalar(select(func.count(Document.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Document).where(*conditions)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [document_to_short(row) for row in rows], total, list(types)


def document_to_short(row: Document) -> DocumentShort:
    return DocumentShort(
        id=row.id, document_type=row.document_type, title=row.title,
        file_name=row.file_name, file_size=row.file_size,
        file_available=bool(document_storage_path(row.file_path)),
        mime_type=row.mime_type, signed_at=row.signed_at,
        expires_at=row.expires_at, status=row.status_raw,
        uploaded_by=row.uploaded_by_keycloak_sub,
        created_at=_ensure_tz(row.created_at),
    )


def document_storage_path(file_path: str) -> Path | None:
    root = Path(settings.storage_root).resolve()
    stored = Path(file_path)
    path = (stored if stored.is_absolute() else root / stored).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def get_meetings(db, university_id: uuid.UUID) -> list[MeetingShort]:
    rows = (
        db.execute(
            select(Meeting)
            .where(Meeting.university_id == university_id)
            .order_by(Meeting.meeting_at.desc())
            .limit(MEETINGS_LIMIT)
        )
        .scalars()
        .all()
    )
    return [
        MeetingShort(
            id=m.id,
            meeting_type=m.meeting_type,
            subject=m.subject,
            participants=_participants_to_strs(m.participants),
            outcome=m.outcome,
            next_action=m.next_action,
            next_action_due=m.next_action_due,
            meeting_at=_ensure_tz(m.meeting_at),
            created_by=m.created_by_keycloak_sub,
        )
        for m in rows
    ]


def get_responsibles(db, university_id: uuid.UUID) -> list[ResponsibleShort]:
    rows = _load_responsible_rows(db, university_id)
    return [
        ResponsibleShort(
            id=resp.id,
            full_name=resp.full_name,
            email=resp.email,
            phone=resp.phone,
            role=link.role_in_university or resp.role or "",
            is_primary=link.is_primary,
        )
        for resp, link in rows
    ]


def get_workflow_transitions(db, university_id: uuid.UUID) -> list[TimelineItem]:
    """P2 integration point — returns [] until P2 tables are available.

    The legacy ``workflow_transitions`` tables use integer FKs incompatible
    with UUID universities, so no copy is created here (P1-04-04 constraint).
    When P2 ships a UUID-compatible query/helper, plug it in here without
    touching the rest of the aggregator.
    """
    return get_workflow_transitions_raw()


def get_timeline(
    db,
    university_id: uuid.UUID,
    documents: list[DocumentShort] | None = None,
    meetings: list[MeetingShort] | None = None,
    notes: list[dict] | None = None,
) -> list[TimelineItem]:
    if documents is None:
        documents = get_documents(db, university_id)
    if meetings is None:
        meetings = get_meetings(db, university_id)
    if notes is None:
        note_rows = (
            db.execute(
                select(InteractionNote)
                .where(InteractionNote.university_id == university_id)
                .order_by(InteractionNote.created_at.desc())
                .limit(TIMELINE_PER_SOURCE_LIMIT)
            )
            .scalars()
            .all()
        )
        notes = [
            {
                "id": n.id,
                "title": n.content,
                "author": n.author_keycloak_sub,
                "ts": n.created_at,
            }
            for n in note_rows
        ]
    return _compose_timeline(documents, meetings, notes)


def get_workflow_summary(db, university_id: uuid.UUID) -> WorkflowSummary:
    """Safe fallback until P2 exposes a UUID-compatible workflow instance."""
    return WorkflowSummary()


# ------------------------------------------------------------- P1-04-05 ---


def get_recent_audit(db, university_id: uuid.UUID) -> list[AuditEventShort]:
    """Last 5 audit events of one university via the existing P5 service.

    Exactly one SQL query (filter + ORDER BY + LIMIT in the DB). Datetimes
    are coerced to tz-aware UTC on output (project convention).
    """
    rows = AuditService(db).recent_for_university(university_id, limit=AUDIT_LIMIT)
    return [
        AuditEventShort(
            id=ev.id,
            user_id=ev.user_id,
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            action=ev.action,
            created_at=_ensure_tz(ev.created_at),
        )
        for ev in rows
    ]


def _optional_block_failed(university_id: uuid.UUID, integration: str, exc: Exception) -> None:
    """Log an optional-integration failure (never tokens, never to the API)."""
    logger.warning(
        "passport optional integration failed",
        extra={
            "university_id": str(university_id),
            "integration": integration,
            "error_type": type(exc).__name__,
        },
        exc_info=True,
    )


# ------------------------------------------------------------- P1-04-01 ---


def get_passport(
    db, university_id: uuid.UUID, include: frozenset[PassportInclude] = frozenset()
) -> UniversityPassport:
    """Compose the full passport in at most 8 SELECTs (no N+1).

    ``include`` selects optional P1-04-05 blocks; each is resolved lazily
    (no queries when not requested) and degrades gracefully — an optional
    integration failure never breaks the base passport (health -> None,
    audit -> []), while base errors still propagate as before.
    """
    # Block 1 (columns-only lookup): 404 before any other work, so the
    # loading pipeline never runs for unknown universities.
    row = _load_university_row(db, university_id)
    if row is None:
        raise NotFound("University not found")

    ctx = PassportLoadContext(university_id=university_id, university_row=row)
    ctx.program_rows = _load_program_rows(db, university_id)  # block 2
    ctx.product_rows = _load_product_rows(db, university_id)  # block 5
    ctx.license_contract_rows = _load_license_contract_rows(db, university_id)  # block 6
    ctx.interaction_rows = _load_interaction_rows(db, university_id)  # block 7
    ctx.responsible_rows = _load_responsible_rows(db, university_id)  # block 8

    programs = _assemble_programs(ctx.program_rows)
    products, licenses, contracts = _assemble_products_licenses_contracts(
        ctx.product_rows, ctx.license_contract_rows
    )
    documents, meetings, note_rows = _assemble_documents_meetings(ctx.interaction_rows)
    responsibles = [
        ResponsibleShort(
            id=resp.id,
            full_name=resp.full_name,
            email=resp.email,
            phone=resp.phone,
            role=link.role_in_university or resp.role or "",
            is_primary=link.is_primary,
        )
        for resp, link in ctx.responsible_rows
    ]
    timeline = _compose_timeline(documents, meetings, note_rows)
    workflow_summary = get_workflow_summary(db, university_id)

    recent_audit = None
    if PassportInclude.AUDIT in include:
        try:
            recent_audit = get_recent_audit(db, university_id)
        except Exception as exc:
            _optional_block_failed(university_id, "audit", exc)
            recent_audit = []

    return UniversityPassport(
        university=UniversityBrief(id=row[0], name=row[1], city=row[2]),
        programs=programs,
        products=products,
        licenses=licenses,
        contracts=contracts,
        documents=documents,
        meetings=meetings,
        responsibles=responsibles,
        workflow_summary=workflow_summary,
        last_interactions=timeline,
        recent_audit=recent_audit,
    )


# ------------------------------------------------- paginated subresources ---


def get_programs_page(
    db, university_id, page: int, page_size: int, status: str | None = None
) -> tuple[list[ProgramShort], int]:
    """Paginated university programs (SQL LIMIT/OFFSET + COUNT, no N+1)."""
    row = _load_university_row(db, university_id)
    if row is None:
        raise NotFound("University not found")
    conditions = [UniversityProgram.university_id == university_id]
    if status is not None:
        conditions.append(UniversityProgram.status == status)
    total = (
        db.execute(
            select(func.count())
            .select_from(UniversityProgram)
            .where(*conditions)
        ).scalar()
        or 0
    )
    stmt = (
        select(
            UniversityProgram,
            ITProgram,
            ITDirection,
            Responsible,
        )
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .join(ITDirection, ITDirection.id == ITProgram.direction_id)
        .outerjoin(Responsible, Responsible.id == UniversityProgram.responsible_id)
        .where(*conditions)
        .order_by(UniversityProgram.created_at)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    program_rows = list(db.execute(stmt).all())
    return _assemble_programs(program_rows), int(total)
