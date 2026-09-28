"""University-scoped teacher assignments and their workflow readiness."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError
from app.core.exceptions import NotFound
from app.core.policies import ensure_university_visible
from app.models.catalog import University
from app.models.interactions import UniversityProgram
from app.models.teachers import Teacher, TeacherProgram
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.teachers.schemas import (
    TeacherCreate, TeacherProgramCreate, TeacherProgramUpdate, TeacherRead, TeacherUpdate,
)


def _audit(db: Session, teacher: Teacher, action: AuditAction, fields: list[str]) -> None:
    if "audit_context" in db.info:
        AuditService(db).log_event(
            context=context_for(db), action=action, entity_type="teacher",
            entity_id=teacher.id, university_id=teacher.university_id,
            new_value={"changed_fields": fields},
        )


def _teacher(db: Session, teacher_id: UUID, user) -> Teacher:
    teacher = db.scalar(select(Teacher).options(selectinload(Teacher.teacher_programs)).where(Teacher.id == teacher_id))
    if teacher is None:
        raise NotFound("Teacher not found")
    ensure_university_visible(teacher.university_id, user)
    return teacher


def _program_link(db: Session, teacher: Teacher, program_id: UUID) -> TeacherProgram:
    link = db.scalar(select(TeacherProgram).where(
        TeacherProgram.teacher_id == teacher.id, TeacherProgram.program_id == program_id,
    ))
    if link is None:
        raise NotFound("Teacher program not found")
    return link


def _check_program(db: Session, university_id: UUID, program_id: UUID) -> None:
    if db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == university_id,
        UniversityProgram.program_id == program_id,
    )) is None:
        raise NotFound("University program not found")


def get_teacher(db: Session, teacher_id: UUID, user) -> TeacherRead:
    return TeacherRead.model_validate(_teacher(db, teacher_id, user))


def list_teachers(db: Session, university_id: UUID, page: int, page_size: int, user) -> tuple[list[TeacherRead], int]:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    ensure_university_visible(university_id, user)
    base = select(Teacher).where(Teacher.university_id == university_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.options(selectinload(Teacher.teacher_programs))
                      .order_by(Teacher.full_name, Teacher.id)
                      .limit(page_size).offset((page - 1) * page_size)).all()
    return [TeacherRead.model_validate(row) for row in rows], total


def create_teacher(db: Session, university_id: UUID, data: TeacherCreate, user) -> TeacherRead:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    ensure_university_visible(university_id, user)
    _check_program(db, university_id, data.program_id)
    teacher = Teacher(university_id=university_id, full_name=data.full_name)
    db.add(teacher)
    db.flush()
    db.add(TeacherProgram(teacher_id=teacher.id, program_id=data.program_id,
                          assigned_at=date.today(), can_teach=False))
    _audit(db, teacher, AuditAction.CREATE, ["full_name", "program_id"])
    db.commit()
    return get_teacher(db, teacher.id, user)


def update_teacher(db: Session, teacher_id: UUID, data: TeacherUpdate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    if teacher.full_name != data.full_name:
        teacher.full_name = data.full_name
        _audit(db, teacher, AuditAction.UPDATE, ["full_name"])
    db.commit()
    return get_teacher(db, teacher_id, user)


def add_program(db: Session, teacher_id: UUID, data: TeacherProgramCreate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    _check_program(db, teacher.university_id, data.program_id)
    if db.scalar(select(TeacherProgram.id).where(
        TeacherProgram.teacher_id == teacher_id, TeacherProgram.program_id == data.program_id,
    )) is not None:
        raise ConflictError(field="program_id")
    db.add(TeacherProgram(teacher_id=teacher.id, assigned_at=date.today(),
                          can_teach=data.training_status == "completed",
                          **data.model_dump()))
    _audit(db, teacher, AuditAction.UPDATE, ["teacher_programs"])
    db.commit()
    return get_teacher(db, teacher_id, user)


def update_program(db: Session, teacher_id: UUID, program_id: UUID,
                   data: TeacherProgramUpdate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    link = _program_link(db, teacher, program_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(link, field, value)
    if "training_status" in changes:
        link.can_teach = changes["training_status"] == "completed"
    if changes:
        _audit(db, teacher, AuditAction.UPDATE, sorted(changes))
    db.commit()
    return get_teacher(db, teacher_id, user)
