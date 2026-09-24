"""P1-08-01 service: student rows -> DTOs, NotFound mapping.

No SQL outside this module's functions. UNIQUE/FK violations surface as
``IntegrityError`` and are mapped centrally to HTTP 409 — never caught
per-endpoint, never leaked to the client.  A student's program must be
assigned to the same university through ``university_programs``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.exceptions import NotFound
from app.core.policies import ensure_university_visible
from app.models.catalog import ITProgram, University
from app.models.interactions import Student, UniversityProgram
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.students.schemas import StudentCreate, StudentRead, StudentUpdate
from app.schemas.errors import ErrorCode

_AUDIT_FIELDS = (
    "external_id",
    "university_id",
    "program_id",
    "full_name",
    "group_name",
    "status",
    "started_at",
    "finished_at",
)


def _check_scope(user, university_id: uuid.UUID) -> None:
    """University-scope gate shared with P5 policy."""
    ensure_university_visible(university_id, user)


def _get_university_or_404(db: Session, university_id: uuid.UUID) -> University:
    university = db.get(University, university_id)
    if university is None:
        raise NotFound("University not found")
    return university


def _get_program_or_404(db: Session, program_id: uuid.UUID) -> ITProgram:
    program = db.get(ITProgram, program_id)
    if program is None:
        raise NotFound("Program not found")
    return program


def _ensure_program_belongs_to_university(
    db: Session, university_id: uuid.UUID, program_id: uuid.UUID
) -> None:
    linked = db.scalar(
        select(UniversityProgram.id).where(
            UniversityProgram.university_id == university_id,
            UniversityProgram.program_id == program_id,
        )
    )
    if linked is None:
        raise BusinessException(
            ErrorCode.VALIDATION_ERROR,
            details={
                "field_errors": [
                    {
                        "field": "program_id",
                        "message": "Программа не закреплена за указанным вузом.",
                        "type": "value_error.program_university_mismatch",
                    }
                ]
            },
        )


def _get_student_or_404(db: Session, student_id: uuid.UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFound("Student not found")
    return student


def _snapshot(student: Student) -> dict:
    return {field: getattr(student, field) for field in _AUDIT_FIELDS}


def _audit(
    db: Session, student: Student, action: AuditAction, *, old=None, new=None
) -> None:
    if "audit_context" not in db.info:
        return
    AuditService(db).log_event(
        context=context_for(db),
        action=action,
        entity_type="student",
        entity_id=student.id,
        university_id=student.university_id,
        old_value=old,
        new_value=new,
    )


def create_student(
    db: Session,
    university_id: uuid.UUID,
    data: StudentCreate,
    *,
    user,
) -> StudentRead:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    _get_program_or_404(db, data.program_id)
    _ensure_program_belongs_to_university(db, university_id, data.program_id)
    student = Student(
        external_id=data.external_id,
        university_id=university_id,
        program_id=data.program_id,
        full_name=data.full_name,
        group_name=data.group_name,
        status=data.status.value,
        started_at=data.started_at,
        finished_at=data.finished_at,
    )
    db.add(student)
    if "audit_context" in db.info:
        db.flush()
        _audit(db, student, AuditAction.CREATE, new=_snapshot(student))
    db.commit()
    db.refresh(student)
    return StudentRead.model_validate(student)


def list_student_page(
    db: Session,
    university_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    user,
) -> tuple[list[StudentRead], int]:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    base = select(Student).where(Student.university_id == university_id)
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Student.full_name.asc(), Student.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return [StudentRead.model_validate(r) for r in rows], total


def get_student(db: Session, student_id: uuid.UUID, *, user) -> StudentRead:
    student = _get_student_or_404(db, student_id)
    _check_scope(user, student.university_id)
    return StudentRead.model_validate(student)


def patch_student(
    db: Session, student_id: uuid.UUID, data: StudentUpdate, *, user
) -> StudentRead:
    student = _get_student_or_404(db, student_id)
    _check_scope(user, student.university_id)
    old = _snapshot(student)
    fields = data.model_fields_set
    if "program_id" in fields and data.program_id is not None:
        _get_program_or_404(db, data.program_id)
        _ensure_program_belongs_to_university(
            db, student.university_id, data.program_id
        )
        student.program_id = data.program_id
    if "status" in fields and data.status is not None:
        student.status = data.status.value
    for field in ("full_name", "group_name", "started_at", "finished_at"):
        if field in fields:
            setattr(student, field, getattr(data, field))
    new = _snapshot(student)
    if old != new:
        _audit(db, student, AuditAction.UPDATE, old=old, new=new)
    db.commit()
    db.refresh(student)
    return StudentRead.model_validate(student)


def delete_student(db: Session, student_id: uuid.UUID, *, user) -> None:
    student = _get_student_or_404(db, student_id)
    _check_scope(user, student.university_id)
    _audit(db, student, AuditAction.DELETE, old=_snapshot(student))
    db.delete(student)
    db.commit()
