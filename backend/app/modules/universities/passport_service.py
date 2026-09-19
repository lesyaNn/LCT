"""P1-04 passport aggregations (service layer, no SQL in routers).

Covers P1-04-02 (programs/teachers/students), P1-04-03
(products/licenses/contracts), P1-04-04
(documents/meetings/responsibles/timeline) and P1-04-05 optional blocks
(health_score/audit via ``?include=``). P1-04-01 composes everything
via :func:`get_passport`. P1-04-06 optimizes the loading pipeline to at
most 8 SELECT statements for the base passport (was 17).

Query strategy (sync SQLAlchemy 2, predictable count, no N+1):

* exactly ONE batched SELECT per block below (never a query inside a
  Python loop, never ``asyncio.gather`` over one Session);
* many-to-one relations are plain JOINs inside the block query (no row
  multiplication is possible there);
* one-to-many fan-out is NEVER joined (that would multiply rows); it is
  aggregated with correlated scalar subqueries
  (``COUNT``/``MIN``/``EXISTS`` columns of the SAME statement — they add
  columns, not statements) or loaded as a separate batched query;
* heterogeneous small capped collections are batched with ``UNION ALL``
  of per-table capped subqueries (one statement, no multiplication —
  rows are simply concatenated and split by a ``kind`` discriminator);
* already-loaded rows are reused in-memory within one call via
  :class:`PassportLoadContext` ("request-level reuse" = plain local
  dataclass, no Redis, no global cache, no cross-request state).

Base passport SQL map (8 statements; verified by
``backend/tests/test_passport_performance.py``):

1. ``universities`` — brief columns (also the 404 check, runs first).
2. ``university_programs`` + program/direction/responsible JOINs +
   a correlated ``teacher_count`` scalar (``students_count`` is filled
   from block 3, so no second scan of ``students``).
3. ``students`` — one ``GROUP BY program_id, status`` aggregate; feeds
   BOTH ``StudentsSummary`` and ``ProgramShort.students_count``.
4. ``teachers`` + ``teacher_programs``/program/direction LEFT JOINs
   (bounded 1:N fan-out: one row per teacher×program) + six correlated
   readiness scalars (expired/soon counts, min expiry over mandatory
   certificates/qualifications). Readiness itself is still computed by
   :func:`compute_teacher_readiness` (single source of truth) fed
   through a provably equivalent lightweight adaptor (see
   :func:`_readiness_from_aggregates`).
5. ``university_products`` + product/vendor JOINs.
6. ``licenses`` + ``contracts`` UNION ALL (product/vendor/contract
   names inline; Python re-sorts; derived status via transient model
   instances so the ``@property`` formula stays the single source).
7. ``documents`` + ``meetings`` + ``interaction_notes`` UNION ALL of
   capped per-source subqueries (20/10/10); feeds documents, meetings
   AND the timeline — the timeline never re-queries them.
8. ``responsibles`` JOIN ``university_responsibles``.

``?include=health_score`` adds 0 statements (pure compute over loaded
DTOs); ``?include=audit`` adds exactly 1.

Derived fields reuse the single sources of truth:
* teacher readiness -> ``app.services.teacher_readiness`` (P1-05);
* license/contract ``derived_status``/``days_to_expiry`` -> model
  ``@property`` (P1-06-02) evaluated on transient instances built from
  already-loaded columns. Nothing derived is written back to the DB.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import enum
import logging

from fastapi import HTTPException
from sqlalchemy import Date, Integer, Text, Uuid, func, literal, select, union_all

from app.core.exceptions import NotFound
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
from app.models.enums import (
    EXPIRY_WARNING_DAYS,
    TeacherReadiness,
    UniversityProductStatus,
    UniversityProgramStatus,
)
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.modules.audit.service import AuditService
from app.modules.health_score.service import compute_score
from app.modules.universities.passport_schemas import (
    AuditEventShort,
    ContractShort,
    DocumentShort,
    HealthScoreResponse,
    LicenseShort,
    MeetingShort,
    ProductShort,
    ProgramShort,
    ResponsibleShort,
    StudentsByProgram,
    StudentsSummary,
    TeacherShort,
    TimelineItem,
    UniversityBrief,
    UniversityPassport,
    WorkflowSummary,
)
from app.services.teacher_readiness import compute_teacher_readiness

logger = logging.getLogger(__name__)

DOCUMENTS_LIMIT = 20
MEETINGS_LIMIT = 10
TIMELINE_LIMIT = 10
TIMELINE_PER_SOURCE_LIMIT = 10
AUDIT_LIMIT = 5

# Typed NULL padding for UNION ALL branches. PostgreSQL (unlike SQLite)
# requires every UNION position to have a resolved type, so padding NULLs
# are explicitly CAST (``::TEXT``/``::INTEGER``/``::DATE``/...). The
# participants padding reuses the exact column type (JSONB on PostgreSQL,
# generic JSON on SQLite) so the position always matches
# ``meetings.participants`` on both dialects.
_NULL_TEXT = literal(None, type_=Text())
_NULL_INT = literal(None, type_=Integer())
_NULL_DATE = literal(None, type_=Date())
_NULL_JSON = literal(None, type_=Meeting.__table__.c.participants.type)


class PassportInclude(str, enum.Enum):
    """Allowed ``?include=`` blocks for the passport endpoint (P1-04-05)."""

    HEALTH_SCORE = "health_score"
    AUDIT = "audit"


def parse_include(raw: str | None) -> frozenset[PassportInclude]:
    """Centralized ``?include=`` parsing (single place, no string matching).

    Normalizes surrounding whitespace, accepts any order
    (``health_score,audit`` == ``audit,health_score``), tolerates empty
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
            raise HTTPException(
                status_code=422,
                detail=f"Unknown passport include: {token!r}. Allowed values: health_score, audit.",
            )
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


# ------------------------------------------------- request-scoped reuse ---


@dataclass
class PassportLoadContext:
    """Request-scoped aggregation context (P1-04-06).

    Lives only inside one :func:`get_passport` call: every block is
    loaded ONCE and then shared by every DTO that needs it (programs ↔
    students counts, documents/meetings ↔ timeline, licenses ↔ products
    license choice). Plain local dataclass — no Redis, no module-level
    cache, no cross-request state.
    """

    university_id: uuid.UUID
    university_row: tuple | None = None
    # (UniversityProgram, ITProgram, ITDirection|None, Responsible|None, teachers_count)
    program_rows: list[tuple] = field(default_factory=list)
    # (program_id, program_name, status, count) aggregate rows
    student_rows: list[tuple] = field(default_factory=list)
    # (Teacher, TeacherProgram|None, ITProgram|None, ITDirection|None,
    #  expired_cnt, soon_cnt, min_expires)
    teacher_rows: list[tuple] = field(default_factory=list)
    # (UniversityProduct, ITProduct, Vendor)
    product_rows: list[tuple] = field(default_factory=list)
    # UNION rows (mappings): kind=license|contract
    license_contract_rows: list[dict] = field(default_factory=list)
    # UNION rows (mappings): kind=document|meeting|note
    interaction_rows: list[dict] = field(default_factory=list)
    # (Responsible, UniversityResponsible)
    responsible_rows: list[tuple] = field(default_factory=list)


# ------------------------------------------------------- block loaders ---


def _load_university_row(db, university_id: uuid.UUID):
    """Block 1: university brief columns (also the 404 check)."""
    return db.execute(
        select(University.id, University.name, University.city).where(
            University.id == university_id
        )
    ).first()


def _teacher_count_scalar(university_id: uuid.UUID):
    """Correlated teacher counter (a SELECT *column*, not a statement)."""
    return (
        select(func.count(func.distinct(TeacherProgram.teacher_id)))
        .select_from(
            TeacherProgram.__table__.join(
                Teacher.__table__,
                Teacher.__table__.c.id == TeacherProgram.__table__.c.teacher_id,
            )
        )
        .where(
            Teacher.__table__.c.university_id == university_id,
            TeacherProgram.__table__.c.program_id == UniversityProgram.__table__.c.program_id,
        )
        .scalar_subquery()
    )


def _load_program_rows(db, university_id: uuid.UUID) -> list[tuple]:
    """Block 2: programs + teacher counters in ONE statement.

    Many-to-one JOINs (program/direction/responsible) cannot multiply
    rows; the teacher counter is a correlated scalar subquery (a column
    of the same statement). ``students_count`` is NOT queried here — it
    is filled from the students aggregate (block 3).
    """
    stmt = (
        select(
            UniversityProgram,
            ITProgram,
            ITDirection,
            Responsible,
            _teacher_count_scalar(university_id).label("teachers_count"),
        )
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .join(ITDirection, ITDirection.id == ITProgram.direction_id)
        .outerjoin(Responsible, Responsible.id == UniversityProgram.responsible_id)
        .where(UniversityProgram.university_id == university_id)
        .order_by(UniversityProgram.created_at)
    )
    return list(db.execute(stmt).all())


def _load_student_rows(db, university_id: uuid.UUID) -> list[tuple]:
    """Block 3: single GROUP BY aggregate over the university's students."""
    return list(
        db.execute(
            select(Student.program_id, ITProgram.name, Student.status, func.count(Student.id))
            .join(ITProgram, ITProgram.id == Student.program_id)
            .where(Student.university_id == university_id)
            .group_by(Student.program_id, ITProgram.name, Student.status)
        ).all()
    )


def _readiness_scalar(column, teacher_fk, mandatory_only: bool, today: date, soon: date):
    """Correlated (expired_count, soon_count, min_expires) for one child table."""
    filters = [
        teacher_fk == Teacher.id,
        column.is_not(None),
    ]
    if mandatory_only:
        filters.append(TeacherCertificate.is_mandatory.is_(True))
    expired = (
        select(func.count())
        .select_from(TeacherCertificate if mandatory_only else TeacherQualification)
        .where(*filters, column < today)
        .scalar_subquery()
    )
    expiring = (
        select(func.count())
        .select_from(TeacherCertificate if mandatory_only else TeacherQualification)
        .where(*filters, column >= today, column <= soon)
        .scalar_subquery()
    )
    minimum = (
        select(func.min(column))
        .select_from(TeacherCertificate if mandatory_only else TeacherQualification)
        .where(*filters)
        .scalar_subquery()
    )
    return expired, expiring, minimum


def _load_teacher_rows(db, university_id: uuid.UUID) -> list[tuple]:
    """Block 4: teachers + programs + readiness inputs in ONE statement.

    The teacher_programs/program/direction LEFT JOINs fan out at most
    one row per teacher×program (bounded, never a cross-collection
    cartesian product). Readiness inputs are six correlated scalar
    subqueries (expired/soon counts + min expiry over mandatory dated
    certificates and dated qualifications) — columns, not statements.
    """
    today = date.today()
    soon = today + timedelta(days=EXPIRY_WARNING_DAYS)
    exp_c, soon_c, min_c = _readiness_scalar(
        TeacherCertificate.expires_at, TeacherCertificate.teacher_id, True, today, soon
    )
    exp_q, soon_q, min_q = _readiness_scalar(
        TeacherQualification.expires_at, TeacherQualification.teacher_id, False, today, soon
    )
    stmt = (
        select(
            Teacher,
            TeacherProgram,
            ITProgram,
            ITDirection,
            exp_c.label("expired_cert"),
            exp_q.label("expired_qual"),
            soon_c.label("soon_cert"),
            soon_q.label("soon_qual"),
            min_c.label("min_cert"),
            min_q.label("min_qual"),
        )
        .outerjoin(TeacherProgram, TeacherProgram.teacher_id == Teacher.id)
        .outerjoin(ITProgram, ITProgram.id == TeacherProgram.program_id)
        .outerjoin(ITDirection, ITDirection.id == ITProgram.direction_id)
        .where(Teacher.university_id == university_id)
        .order_by(Teacher.full_name, Teacher.id, ITProgram.name, ITProgram.id)
    )
    return list(db.execute(stmt).all())


def _readiness_from_aggregates(expired_cnt: int, soon_cnt: int, min_expires: date | None):
    """Readiness adaptor: aggregates -> :func:`compute_teacher_readiness`.

    ``compute_teacher_readiness`` stays the single source of truth (it is
    CALLED here, not reimplemented). Equivalence argument for the two
    exposed fields (``readiness``, ``next_qualification_date``; the
    human-readable ``reasons`` are not part of ``TeacherShort``):

    * the aggregates range over exactly the items the formula considers
      mandatory-and-dated (mandatory certificates + all qualifications
      with ``expires_at`` set);
    * ``expired_cnt > 0`` ⟺ ``min_expires < today`` (min over the same
      set), so a single synthetic dated entry reproduces EXPIRED;
    * otherwise ``soon_cnt > 0`` ⟺ ``today <= min_expires <= today+30``,
      reproducing ATTENTION;
    * otherwise READY, and ``next_qualification_date`` is the minimum in
      both worlds (``None`` when the set is empty).
    """
    if min_expires is None:
        entries: list[dict] = []
    else:
        entries = [
            {
                "certificate_name": "passport",
                "is_mandatory": True,
                "expires_at": min_expires,
            }
        ]
    result = compute_teacher_readiness(certificates=entries, qualifications=[])
    # Defensive cross-check of the proof above (cheap, per-teacher ints).
    if expired_cnt > 0:
        assert result.readiness == TeacherReadiness.EXPIRED
    elif soon_cnt > 0:
        assert result.readiness == TeacherReadiness.ATTENTION
    else:
        assert result.readiness == TeacherReadiness.READY
    return result


def _load_product_rows(db, university_id: uuid.UUID) -> list[tuple]:
    """Block 5: university_products + product/vendor (many-to-one JOINs)."""
    stmt = (
        select(UniversityProduct, ITProduct, Vendor)
        .join(ITProduct, ITProduct.id == UniversityProduct.product_id)
        .join(Vendor, Vendor.id == ITProduct.vendor_id)
        .where(UniversityProduct.university_id == university_id)
    )
    return list(db.execute(stmt).all())


def _load_license_contract_rows(db, university_id: uuid.UUID) -> list[dict]:
    """Block 6: licenses + contracts in ONE UNION ALL statement.

    Both collections share the same projection (number, product/vendor
    names, dates, statuses, links); ``kind`` discriminates the rows in
    Python, which also restores each collection's own ordering. No row
    multiplication (concatenation, not a JOIN).
    """
    lic_branch = (
        select(
            literal("license").label("kind"),
            License.id.label("id"),
            License.license_number.label("num"),
            License.product_id.label("product_id"),
            ITProduct.name.label("product_name"),
            Vendor.name.label("vendor_name"),
            License.signed_at.label("signed_at"),
            License.expires_at.label("expires_at"),
            License.transfer_status_raw.label("transfer_status"),
            _NULL_TEXT.label("status_raw"),
            License.contract_id.label("contract_id"),
            Contract.contract_number.label("contract_number"),
        )
        .join(ITProduct, ITProduct.id == License.product_id)
        .join(Vendor, Vendor.id == ITProduct.vendor_id)
        .outerjoin(Contract, Contract.id == License.contract_id)
        .where(License.university_id == university_id)
    )
    con_branch = (
        select(
            literal("contract").label("kind"),
            Contract.id.label("id"),
            Contract.contract_number.label("num"),
            Contract.product_id.label("product_id"),
            ITProduct.name.label("product_name"),
            Vendor.name.label("vendor_name"),
            Contract.signed_at.label("signed_at"),
            Contract.expires_at.label("expires_at"),
            Contract.transfer_status_raw.label("transfer_status"),
            Contract.status_raw.label("status_raw"),
            literal(None, type_=Uuid()).label("contract_id"),
            _NULL_TEXT.label("contract_number"),
        )
        .outerjoin(ITProduct, ITProduct.id == Contract.product_id)
        .outerjoin(Vendor, Vendor.id == ITProduct.vendor_id)
        .where(Contract.university_id == university_id)
    )
    batched = union_all(lic_branch, con_branch).subquery("plc")
    return list(db.execute(select(batched)).mappings().all())


def _load_interaction_rows(db, university_id: uuid.UUID) -> list[dict]:
    """Block 7: documents + meetings + notes in ONE UNION ALL statement.

    Each source is capped in SQL (``ORDER BY ... LIMIT`` inside a
    subquery, so PostgreSQL and SQLite both accept it); the merged rows
    feed documents, meetings AND the timeline — the timeline never
    re-queries them.
    """
    docs_branch = (
        select(
            literal("document").label("kind"),
            Document.id.label("id"),
            Document.document_type.label("ctype"),
            Document.title.label("title"),
            Document.file_name.label("file_name"),
            Document.file_size.label("file_size"),
            Document.mime_type.label("mime"),
            Document.signed_at.label("signed_at"),
            Document.expires_at.label("expires_at"),
            Document.status_raw.label("status_raw"),
            Document.uploaded_by_keycloak_sub.label("author"),
            Document.created_at.label("ts"),
            _NULL_JSON.label("participants"),
            _NULL_DATE.label("due"),
            _NULL_TEXT.label("extra1"),
            _NULL_TEXT.label("extra2"),
        )
        .where(Document.university_id == university_id)
        .order_by(Document.created_at.desc())
        .limit(DOCUMENTS_LIMIT)
        .subquery("tl_docs")
    )
    meetings_branch = (
        select(
            literal("meeting").label("kind"),
            Meeting.id.label("id"),
            Meeting.meeting_type.label("ctype"),
            Meeting.subject.label("title"),
            _NULL_TEXT.label("file_name"),
            _NULL_INT.label("file_size"),
            _NULL_TEXT.label("mime"),
            _NULL_DATE.label("signed_at"),
            _NULL_DATE.label("expires_at"),
            _NULL_TEXT.label("status_raw"),
            Meeting.created_by_keycloak_sub.label("author"),
            Meeting.meeting_at.label("ts"),
            Meeting.participants.label("participants"),
            Meeting.next_action_due.label("due"),
            Meeting.outcome.label("extra1"),
            Meeting.next_action.label("extra2"),
        )
        .where(Meeting.university_id == university_id)
        .order_by(Meeting.meeting_at.desc())
        .limit(MEETINGS_LIMIT)
        .subquery("tl_meetings")
    )
    notes_branch = (
        select(
            literal("note").label("kind"),
            InteractionNote.id.label("id"),
            literal("note").label("ctype"),
            InteractionNote.content.label("title"),
            _NULL_TEXT.label("file_name"),
            _NULL_INT.label("file_size"),
            _NULL_TEXT.label("mime"),
            _NULL_DATE.label("signed_at"),
            _NULL_DATE.label("expires_at"),
            _NULL_TEXT.label("status_raw"),
            InteractionNote.author_keycloak_sub.label("author"),
            InteractionNote.created_at.label("ts"),
            _NULL_JSON.label("participants"),
            _NULL_DATE.label("due"),
            _NULL_TEXT.label("extra1"),
            _NULL_TEXT.label("extra2"),
        )
        .where(InteractionNote.university_id == university_id)
        .order_by(InteractionNote.created_at.desc())
        .limit(TIMELINE_PER_SOURCE_LIMIT)
        .subquery("tl_notes")
    )
    batched = union_all(
        select(docs_branch), select(meetings_branch), select(notes_branch)
    ).subquery("timeline")
    return list(db.execute(select(batched)).mappings().all())


def _load_responsible_rows(db, university_id: uuid.UUID) -> list[tuple]:
    """Block 8: responsibles JOIN university_responsibles."""
    return list(
        db.execute(
            select(Responsible, UniversityResponsible)
            .join(
                UniversityResponsible,
                UniversityResponsible.responsible_id == Responsible.id,
            )
            .where(UniversityResponsible.university_id == university_id)
            .order_by(Responsible.full_name)
        ).all()
    )


# ---------------------------------------------------------- assemblers ---


def _assemble_programs(
    program_rows: list[tuple], students_count_by_program: dict[uuid.UUID, int]
) -> list[ProgramShort]:
    out: list[ProgramShort] = []
    for link, program, direction, responsible, teachers_count in program_rows:
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
                teachers_count=int(teachers_count or 0),
                students_count=int(students_count_by_program.get(link.program_id, 0)),
            )
        )
    return out


def _assemble_students_summary(student_rows: list[tuple]) -> tuple[StudentsSummary, dict]:
    """Build StudentsSummary AND the per-program totals map from one aggregate."""
    if not student_rows:
        return StudentsSummary(total=0, active=0, graduated=0, by_status={}, by_program=[]), {}
    by_status: dict[str, int] = defaultdict(int)
    per_program: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    name_by_id: dict[uuid.UUID, str] = {}
    total = 0
    for program_id, program_name, status, count in student_rows:
        count = int(count)
        total += count
        by_status[str(status)] += count
        per_program[program_id][str(status)] += count
        name_by_id[program_id] = program_name
    by_program = [
        StudentsByProgram(
            program_id=pid,
            program_name=name_by_id.get(pid, ""),
            total=sum(counts.values()),
            active=int(counts.get("active", 0)),
            graduated=int(counts.get("graduated", 0)),
        )
        for pid, counts in sorted(per_program.items(), key=lambda kv: name_by_id.get(kv[0], ""))
    ]
    by_status = dict(sorted(by_status.items()))
    totals = {pid: sum(counts.values()) for pid, counts in per_program.items()}
    return (
        StudentsSummary(
            total=total,
            active=int(by_status.get("active", 0)),
            graduated=int(by_status.get("graduated", 0)),
            by_status=by_status,
            by_program=by_program,
        ),
        totals,
    )


def _assemble_teachers(
    teacher_rows: list[tuple],
    programs_cache: list[ProgramShort] | None = None,
) -> list[TeacherShort]:
    by_program_id: dict[uuid.UUID, ProgramShort] = {p.id: p for p in (programs_cache or [])}
    grouped: dict[uuid.UUID, dict] = {}
    order: list[uuid.UUID] = []
    for row in teacher_rows:
        teacher, tp, program, direction, e_cert, e_qual, s_cert, s_qual, min_c, min_q = row
        entry = grouped.get(teacher.id)
        if entry is None:
            entry = {"teacher": teacher, "links": [], "exp": 0, "soon": 0, "mins": []}
            grouped[teacher.id] = entry
            order.append(teacher.id)
        entry["exp"] += int(e_cert or 0) + int(e_qual or 0)
        entry["soon"] += int(s_cert or 0) + int(s_qual or 0)
        if min_c is not None:
            entry["mins"].append(min_c)
        if min_q is not None:
            entry["mins"].append(min_q)
        if tp is not None and program is not None:
            if program.id not in by_program_id:
                by_program_id[program.id] = ProgramShort(
                    id=program.id,
                    name=program.name,
                    direction_name=direction.name if direction is not None else "",
                    status=UniversityProgramStatus.ACTIVE,
                    launch_date=None,
                    responsible_name=None,
                    teachers_count=0,
                    students_count=0,
                )
            entry["links"].append(program.id)

    out: list[TeacherShort] = []
    for tid in order:
        entry = grouped[tid]
        teacher = entry["teacher"]
        min_expires = min(entry["mins"]) if entry["mins"] else None
        result = _readiness_from_aggregates(entry["exp"], entry["soon"], min_expires)
        seen: set[uuid.UUID] = set()
        linked: list[ProgramShort] = []
        for pid in entry["links"]:
            if pid in by_program_id and pid not in seen:
                seen.add(pid)
                linked.append(by_program_id[pid])
        teacher_programs = sorted(linked, key=lambda p: p.name)
        out.append(
            TeacherShort(
                id=teacher.id,
                full_name=teacher.full_name,
                email=teacher.email,
                position=teacher.position or "",
                readiness=result.readiness,
                next_qualification_date=result.next_qualification_date,
                programs=list(teacher_programs),
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


def get_programs(db, university_id: uuid.UUID) -> list[ProgramShort]:
    """Batch-load university programs with aggregate counters (no N+1).

    Standalone entry point (2 statements: block 2 + one batched student
    counter). The passport pipeline instead reuses the students
    aggregate, so it issues no extra statement here.
    """
    program_rows = _load_program_rows(db, university_id)
    if not program_rows:
        return []
    program_ids = [link.program_id for link, _, _, _, _ in program_rows]
    student_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Student.program_id, func.count(Student.id))
            .where(
                Student.university_id == university_id,
                Student.program_id.in_(program_ids),
            )
            .group_by(Student.program_id)
        ).all()
    )
    return _assemble_programs(program_rows, student_counts)


def get_teachers(
    db,
    university_id: uuid.UUID,
    programs_cache: list[ProgramShort] | None = None,
) -> list[TeacherShort]:
    """Batch-load teachers with programs + readiness (no N+1, 1 statement)."""
    teacher_rows = _load_teacher_rows(db, university_id)
    if not teacher_rows:
        return []
    return _assemble_teachers(teacher_rows, programs_cache)


def get_students_summary(db, university_id: uuid.UUID) -> StudentsSummary:
    """Single GROUP BY query (program names joined in); Python-side rollup."""
    summary, _ = _assemble_students_summary(_load_student_rows(db, university_id))
    return summary


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
            .where(Document.university_id == university_id)
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


def get_health_score_for_passport(
    university_id: uuid.UUID,
    licenses: list[LicenseShort],
    teachers: list[TeacherShort],
    documents: list[DocumentShort],
) -> HealthScoreResponse:
    """Read-only Health Score from already-loaded passport data (P1-04-05).

    Direct Python reuse of the shared P2 formula — same monolith, so no HTTP
    boundary is crossed (no client, no timeout, no retry needed).

    Signals are derived transparently (zero extra queries, zero writes —
    ``HealthScoreService.calculate`` must NOT be called here because it
    persists a history row on every call):
    * ``missing_license`` — any expired license;
    * ``teacher_training`` — any teacher whose readiness is not ready;
    * ``missing_docs`` — empty file registry;
    * ``stage_delay`` / ``launch_delay`` — False (P2 workflow unavailable,
      unobservable; never fabricate a penalty);
    * ``overdue_tasks`` — 0 (legacy ``tasks`` table uses int FKs incompatible
      with UUID universities; querying it with a UUID fails on PostgreSQL).
    """
    signals = {
        "missing_license": any(lic.status == "expired" for lic in licenses),
        "teacher_training": any(t.readiness != TeacherReadiness.READY for t in teachers),
        "missing_docs": not documents,
        "stage_delay": False,
        "launch_delay": False,
    }
    score, details = compute_score(overdue_tasks=0, signals=signals)
    return HealthScoreResponse(
        university_id=university_id,
        score=score,
        details=details,
        calculated_at=datetime.now(timezone.utc),
    )


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
    ctx.student_rows = _load_student_rows(db, university_id)  # block 3
    ctx.teacher_rows = _load_teacher_rows(db, university_id)  # block 4
    ctx.product_rows = _load_product_rows(db, university_id)  # block 5
    ctx.license_contract_rows = _load_license_contract_rows(db, university_id)  # block 6
    ctx.interaction_rows = _load_interaction_rows(db, university_id)  # block 7
    ctx.responsible_rows = _load_responsible_rows(db, university_id)  # block 8

    students_summary, students_count_by_program = _assemble_students_summary(ctx.student_rows)
    programs = _assemble_programs(ctx.program_rows, students_count_by_program)
    teachers = _assemble_teachers(ctx.teacher_rows, programs)
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
        )
        for resp, link in ctx.responsible_rows
    ]
    timeline = _compose_timeline(documents, meetings, note_rows)
    workflow_summary = get_workflow_summary(db, university_id)

    health_score = None
    recent_audit = None
    if PassportInclude.HEALTH_SCORE in include:
        try:
            health_score = get_health_score_for_passport(
                university_id, licenses, teachers, documents
            )
        except Exception as exc:
            _optional_block_failed(university_id, "health_score", exc)
            health_score = None
    if PassportInclude.AUDIT in include:
        try:
            recent_audit = get_recent_audit(db, university_id)
        except Exception as exc:
            _optional_block_failed(university_id, "audit", exc)
            recent_audit = []

    return UniversityPassport(
        university=UniversityBrief(id=row[0], name=row[1], city=row[2]),
        programs=programs,
        teachers=teachers,
        students_summary=students_summary,
        products=products,
        licenses=licenses,
        contracts=contracts,
        documents=documents,
        meetings=meetings,
        responsibles=responsibles,
        workflow_summary=workflow_summary,
        last_interactions=timeline,
        health_score=health_score,
        recent_audit=recent_audit,
    )


# ------------------------------------------------- paginated subresources ---


def get_programs_page(
    db, university_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[ProgramShort], int]:
    """Paginated university programs (SQL LIMIT/OFFSET + COUNT, no N+1)."""
    row = _load_university_row(db, university_id)
    if row is None:
        raise NotFound("University not found")
    total = (
        db.execute(
            select(func.count())
            .select_from(UniversityProgram)
            .where(UniversityProgram.university_id == university_id)
        ).scalar()
        or 0
    )
    stmt = (
        select(
            UniversityProgram,
            ITProgram,
            ITDirection,
            Responsible,
            _teacher_count_scalar(university_id).label("teachers_count"),
        )
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .join(ITDirection, ITDirection.id == ITProgram.direction_id)
        .outerjoin(Responsible, Responsible.id == UniversityProgram.responsible_id)
        .where(UniversityProgram.university_id == university_id)
        .order_by(UniversityProgram.created_at)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    program_rows = list(db.execute(stmt).all())
    counts: dict[uuid.UUID, int] = {}
    if program_rows:
        program_ids = [link.program_id for link, _, _, _, _ in program_rows]
        counts = dict(
            db.execute(
                select(Student.program_id, func.count(Student.id))
                .where(
                    Student.university_id == university_id,
                    Student.program_id.in_(program_ids),
                )
                .group_by(Student.program_id)
            ).all()
        )
    return _assemble_programs(program_rows, counts), int(total)


def get_teachers_page(
    db, university_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[TeacherShort], int]:
    """Paginated university teachers (SQL LIMIT/OFFSET + COUNT, no N+1)."""
    row = _load_university_row(db, university_id)
    if row is None:
        raise NotFound("University not found")
    total = (
        db.execute(
            select(func.count()).select_from(Teacher).where(Teacher.university_id == university_id)
        ).scalar()
        or 0
    )
    page_ids = list(
        db.execute(
            select(Teacher.id)
            .where(Teacher.university_id == university_id)
            .order_by(Teacher.full_name, Teacher.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    if not page_ids:
        return [], int(total)
    today = date.today()
    soon = today + timedelta(days=EXPIRY_WARNING_DAYS)
    exp_c, soon_c, min_c = _readiness_scalar(
        TeacherCertificate.expires_at, TeacherCertificate.teacher_id, True, today, soon
    )
    exp_q, soon_q, min_q = _readiness_scalar(
        TeacherQualification.expires_at, TeacherQualification.teacher_id, False, today, soon
    )
    stmt = (
        select(
            Teacher,
            TeacherProgram,
            ITProgram,
            ITDirection,
            exp_c.label("expired_cert"),
            exp_q.label("expired_qual"),
            soon_c.label("soon_cert"),
            soon_q.label("soon_qual"),
            min_c.label("min_cert"),
            min_q.label("min_qual"),
        )
        .outerjoin(TeacherProgram, TeacherProgram.teacher_id == Teacher.id)
        .outerjoin(ITProgram, ITProgram.id == TeacherProgram.program_id)
        .outerjoin(ITDirection, ITDirection.id == ITProgram.direction_id)
        .where(Teacher.id.in_(page_ids))
        .order_by(Teacher.full_name, Teacher.id, ITProgram.name, ITProgram.id)
    )
    teacher_rows = list(db.execute(stmt).all())
    return _assemble_teachers(teacher_rows), int(total)


__all__ = [
    "AUDIT_LIMIT",
    "DOCUMENTS_LIMIT",
    "MEETINGS_LIMIT",
    "TIMELINE_LIMIT",
    "PassportInclude",
    "PassportLoadContext",
    "parse_include",
    "get_passport",
    "get_programs",
    "get_programs_page",
    "get_teachers",
    "get_teachers_page",
    "get_students_summary",
    "get_products_licenses_contracts",
    "get_documents",
    "get_meetings",
    "get_responsibles",
    "get_timeline",
    "get_workflow_summary",
    "get_workflow_transitions",
    "get_health_score_for_passport",
    "get_recent_audit",
]
