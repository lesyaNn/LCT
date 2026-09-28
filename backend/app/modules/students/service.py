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

from app.config import settings
from app.core.errors import BusinessException
from app.core.exceptions import NotFound
from app.core.policies import ensure_university_visible
from app.models.catalog import ITProgram, University
from app.models.interactions import Student, UniversityProgram
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.students.schemas import ProgramStudentSummary, StudentCreate, StudentRead, StudentSummaryRead, StudentUpdate
from app.schemas.errors import ErrorCode

_AUDIT_FIELDS = (
    "university_id",
    "program_id",
    "status",
    "started_at",
    "finished_at",
    "source",
    "progress",
    "synced_at",
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
    demo_visible = settings.external_adapter_mode == "mock" and settings.app_env.strip().lower() not in {"prod", "production"}
    if student is None or (student.source == "mock_lms" and not demo_visible):
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
        source="manual",
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
    program_id: uuid.UUID | None = None,
    status: str | None = None,
) -> tuple[list[StudentRead], int]:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    base = select(Student).where(Student.university_id == university_id)
    if settings.external_adapter_mode != "mock" or settings.app_env.strip().lower() in {"prod", "production"}:
        base = base.where(Student.source != "mock_lms")
    if program_id is not None:
        base = base.where(Student.program_id == program_id)
    if status is not None:
        base = base.where(Student.status == status)
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


def student_summary(db: Session, university_id: uuid.UUID, *, user) -> StudentSummaryRead:
    _get_university_or_404(db, university_id)
    _check_scope(user, university_id)
    demo_visible = settings.external_adapter_mode == "mock" and settings.app_env.strip().lower() not in {"prod", "production"}
    visible_student = (Student.program_id == ITProgram.id) & (Student.university_id == university_id)
    if not demo_visible:
        visible_student &= Student.source != "mock_lms"
    rows = db.execute(select(
        ITProgram.id, ITProgram.name,
        func.count(Student.id),
        func.count(Student.id).filter(Student.status == "active"),
        func.count(func.distinct(Student.group_name)).filter(Student.group_name.is_not(None)),
        func.count(Student.id).filter(Student.source.in_(("lms", "mock_lms") if demo_visible else ("lms",))),
    ).join(UniversityProgram, UniversityProgram.program_id == ITProgram.id)
     .outerjoin(Student, visible_student)
     .where(UniversityProgram.university_id == university_id)
     .group_by(ITProgram.id, ITProgram.name).order_by(ITProgram.name)).all()
    programs = [ProgramStudentSummary(
        program_id=program_id, program_name=name, learners=learners,
        active_learners=active, flows=flows, lms_learners=lms,
    ) for program_id, name, learners, active, flows, lms in rows]
    return StudentSummaryRead(
        university_id=university_id,
        learners=sum(row.learners for row in programs),
        active_learners=sum(row.active_learners for row in programs),
        flows=sum(row.flows for row in programs),
        programs=programs,
    )


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
    before = {field: getattr(student, field) for field in fields if hasattr(student, field)}
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
    if any(before[field] != getattr(student, field) for field in before):
        _audit(db, student, AuditAction.UPDATE,
               old={**old, "changed_fields": sorted(before)},
               new={**new, "changed_fields": sorted(before)})
    db.commit()
    db.refresh(student)
    return StudentRead.model_validate(student)


def delete_student(db: Session, student_id: uuid.UUID, *, user) -> None:
    student = _get_student_or_404(db, student_id)
    _check_scope(user, student.university_id)
    _audit(db, student, AuditAction.DELETE, old=_snapshot(student))
    db.delete(student)
    db.commit()
