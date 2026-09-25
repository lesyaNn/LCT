"""P1-04 passport SQL loading (one batched SELECT per block, no N+1).

Moved verbatim from ``passport_service`` (M1 god-file split): block loaders
fill :class:`PassportLoadContext`; DTO assembly lives in
``passport_blocks``. No behavior change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import Date, Integer, Text, func, literal, select, union_all

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
