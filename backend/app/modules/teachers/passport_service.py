"""P1-05 teacher passport aggregation (service layer, no SQL in routers).

Covers P1-05-01 (``GET /teachers/{id}/passport``), P1-05-02 (qualifications /
certificates / programs) and P1-05-03 (``ready`` / ``attention`` / ``expired``
via the canonical :func:`compute_teacher_readiness` formula — the single
source of truth, shared with the University Passport; NO second formula here).

Query strategy (sync SQLAlchemy 2, constant count, no N+1):

1. ``teachers`` + ``universities`` JOIN (also the 404 check).
2. ``teacher_qualifications`` (one batched SELECT, deterministic ordering).
3. ``teacher_certificates`` + linked ``it_programs`` OUTER JOIN (one batched
   SELECT — the per-certificate program is joined inline, never lazy-loaded).
4. ``teacher_programs`` + ``it_programs`` / ``it_directions`` JOINs (one
   batched SELECT).

Readiness is computed over the already-loaded ORM objects (scalar attributes
only — no relationship access, so no hidden lazy SELECTs). Small-dataset and
large-dataset SELECT counts are identical (4).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.exceptions import NotFound
from app.models.catalog import ITDirection, ITProgram, University
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.modules.teachers.passport_schemas import (
    CertificateProgramShort,
    CertificateRead,
    QualificationRead,
    TeacherBlock,
    TeacherPassport,
    TeacherProgramLink,
    TeacherProgramRead,
    UniversityBrief,
)
from app.services.teacher_readiness import compute_teacher_readiness


def _ensure_tz(dt: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime (project UTC/ISO-8601 convention).

    Naive values coming from SQLite (which cannot store tzinfo) are
    interpreted as UTC — the only timezone the seed and the app ever write.
    PostgreSQL ``timestamptz`` already returns aware values and passes
    through untouched. Mirrors the University Passport helper.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _load_teacher_row(db, teacher_id: uuid.UUID) -> tuple | None:
    """Block 1: teacher + university columns in ONE statement (404 check).

    University is loaded as bare columns (not the ORM entity) on purpose:
    ``University.university_responsibles`` is ``lazy="selectin"`` and
    instantiating the entity would fire an extra SELECT. Column access keeps
    the passport at exactly 4 statements.
    """
    return db.execute(
        select(Teacher, University.id, University.name, University.city)
        .join(University, University.id == Teacher.university_id)
        .where(Teacher.id == teacher_id)
    ).first()


def _load_qualifications(db, teacher_id: uuid.UUID) -> list[TeacherQualification]:
    """Block 2: all qualifications of one teacher (deterministic order)."""
    return list(
        db.execute(
            select(TeacherQualification)
            .where(TeacherQualification.teacher_id == teacher_id)
            .order_by(
                TeacherQualification.expires_at.asc().nulls_last(),
                TeacherQualification.id.asc(),
            )
        )
        .scalars()
        .all()
    )


def _load_certificate_rows(db, teacher_id: uuid.UUID) -> list[tuple]:
    """Block 3: certificates + linked program columns (many-to-one JOIN)."""
    return list(
        db.execute(
            select(TeacherCertificate, ITProgram.id, ITProgram.name)
            .outerjoin(ITProgram, ITProgram.id == TeacherCertificate.program_id)
            .where(TeacherCertificate.teacher_id == teacher_id)
            .order_by(
                TeacherCertificate.expires_at.asc().nulls_last(),
                TeacherCertificate.id.asc(),
            )
        ).all()
    )


def _load_program_rows(db, teacher_id: uuid.UUID) -> list[tuple]:
    """Block 4: teacher_programs + program/direction (many-to-one JOINs)."""
    return list(
        db.execute(
            select(TeacherProgram, ITProgram, ITDirection)
            .join(ITProgram, ITProgram.id == TeacherProgram.program_id)
            .join(ITDirection, ITDirection.id == ITProgram.direction_id)
            .where(TeacherProgram.teacher_id == teacher_id)
            .order_by(ITProgram.name.asc(), ITProgram.id.asc())
        ).all()
    )


def get_teacher_passport(db, teacher_id: uuid.UUID) -> TeacherPassport:
    """Compose the full teacher passport in exactly 4 SELECTs (no N+1)."""
    row = _load_teacher_row(db, teacher_id)
    if row is None:
        raise NotFound("Teacher not found")
    teacher, university_id, university_name, university_city = row

    qualifications = _load_qualifications(db, teacher_id)
    certificate_rows = _load_certificate_rows(db, teacher_id)
    program_rows = _load_program_rows(db, teacher_id)

    certificates = [cert for cert, _, _ in certificate_rows]

    # Canonical readiness (P1-05-03): the shared formula over already-loaded
    # ORM objects — scalar attributes only, zero extra queries.
    result = compute_teacher_readiness(certificates=certificates, qualifications=qualifications)

    return TeacherPassport(
        teacher=TeacherBlock(
            id=teacher.id,
            university_id=teacher.university_id,
            full_name=teacher.full_name,
            email=teacher.email,
            position=teacher.position or "",
            created_at=_ensure_tz(teacher.created_at),
            updated_at=_ensure_tz(teacher.updated_at),
        ),
        university=UniversityBrief(id=university_id, name=university_name, city=university_city),
        qualifications=[
            QualificationRead(
                id=q.id,
                qualification_name=q.qualification_name,
                obtained_at=q.obtained_at,
                expires_at=q.expires_at,
                document_ref=q.document_ref,
                created_at=_ensure_tz(q.created_at),
            )
            for q in qualifications
        ],
        certificates=[
            CertificateRead(
                id=cert.id,
                certificate_name=cert.certificate_name,
                issued_by=cert.issued_by,
                issued_at=cert.issued_at,
                expires_at=cert.expires_at,
                is_mandatory=cert.is_mandatory,
                program_id=cert.program_id,
                program=(
                    CertificateProgramShort(id=program_id, name=program_name)
                    if program_id is not None
                    else None
                ),
                document_ref=cert.document_ref,
                created_at=_ensure_tz(cert.created_at),
            )
            for cert, program_id, program_name in certificate_rows
        ],
        programs=[
            TeacherProgramRead(
                id=link.id,
                program=TeacherProgramLink(
                    id=program.id,
                    name=program.name,
                    direction_name=direction.name if direction is not None else "",
                ),
                can_teach=link.can_teach,
                assigned_at=link.assigned_at,
            )
            for link, program, direction in program_rows
        ],
        readiness=result.readiness,
        readiness_reasons=list(result.reasons),
        next_qualification_date=result.next_qualification_date,
    )
