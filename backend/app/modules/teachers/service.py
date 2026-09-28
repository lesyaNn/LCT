"""Persist educator training evidence within the actor's university scope."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFound
from app.core.policies import ensure_university_visible
from app.models.catalog import University
from app.models.interactions import UniversityProgram
from app.models.teachers import Teacher, TeacherCertificate, TeacherProgram, TeacherQualification
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.teachers.schemas import (
    CertificateCreate, QualificationCreate, TeacherCreate, TeacherProgramCreate,
    TeacherRead, TeacherUpdate,
)


def _audit(db: Session, teacher: Teacher, action: AuditAction, *, detail: dict) -> None:
    if "audit_context" not in db.info:
        return
    AuditService(db).log_event(
        context=context_for(db), action=action, entity_type="teacher",
        entity_id=teacher.id, university_id=teacher.university_id,
        new_value=detail if action != AuditAction.DELETE else None,
        old_value=detail if action == AuditAction.DELETE else None,
    )


def _teacher(db: Session, teacher_id: UUID, user) -> Teacher:
    teacher = db.scalar(select(Teacher).options(
        selectinload(Teacher.qualifications),
        selectinload(Teacher.certificates),
        selectinload(Teacher.teacher_programs),
    ).where(Teacher.id == teacher_id))
    if teacher is None:
        raise NotFound("Teacher not found")
    ensure_university_visible(teacher.university_id, user)
    return teacher


def _read(db: Session, teacher_id: UUID, user) -> TeacherRead:
    return TeacherRead.model_validate(_teacher(db, teacher_id, user))


def list_teachers(db: Session, university_id: UUID, page: int, page_size: int, user) -> tuple[list[TeacherRead], int]:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    ensure_university_visible(university_id, user)
    base = select(Teacher).where(Teacher.university_id == university_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.options(
        selectinload(Teacher.qualifications), selectinload(Teacher.certificates),
        selectinload(Teacher.teacher_programs),
    ).order_by(Teacher.full_name, Teacher.id).limit(page_size).offset((page - 1) * page_size)).all()
    return [TeacherRead.model_validate(row) for row in rows], total


def create_teacher(db: Session, university_id: UUID, data: TeacherCreate, user) -> TeacherRead:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    ensure_university_visible(university_id, user)
    teacher = Teacher(university_id=university_id, **data.model_dump())
    db.add(teacher)
    db.flush()
    _audit(db, teacher, AuditAction.CREATE, detail={"university_id": str(university_id)})
    db.commit()
    return _read(db, teacher.id, user)


def update_teacher(db: Session, teacher_id: UUID, data: TeacherUpdate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(teacher, key, value)
    _audit(db, teacher, AuditAction.UPDATE, detail={"fields": sorted(data.model_fields_set)})
    db.commit()
    return _read(db, teacher_id, user)


def delete_teacher(db: Session, teacher_id: UUID, user) -> None:
    teacher = _teacher(db, teacher_id, user)
    _audit(db, teacher, AuditAction.DELETE, detail={"university_id": str(teacher.university_id)})
    db.delete(teacher)
    db.commit()


def add_qualification(db: Session, teacher_id: UUID, data: QualificationCreate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    db.add(TeacherQualification(teacher_id=teacher.id, **data.model_dump()))
    _audit(db, teacher, AuditAction.UPDATE, detail={"added": "qualification"})
    db.commit()
    return _read(db, teacher_id, user)


def add_certificate(db: Session, teacher_id: UUID, data: CertificateCreate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    if data.program_id is not None and not db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == teacher.university_id,
        UniversityProgram.program_id == data.program_id,
    )):
        raise NotFound("University program not found")
    db.add(TeacherCertificate(teacher_id=teacher.id, **data.model_dump()))
    _audit(db, teacher, AuditAction.UPDATE, detail={"added": "certificate"})
    db.commit()
    return _read(db, teacher_id, user)


def add_program(db: Session, teacher_id: UUID, data: TeacherProgramCreate, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    if not db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == teacher.university_id,
        UniversityProgram.program_id == data.program_id,
    )):
        raise NotFound("University program not found")
    existing = db.scalar(select(TeacherProgram).where(
        TeacherProgram.teacher_id == teacher.id, TeacherProgram.program_id == data.program_id,
    ))
    if existing is None:
        db.add(TeacherProgram(teacher_id=teacher.id, **data.model_dump()))
    else:
        existing.can_teach = data.can_teach
        existing.assigned_at = data.assigned_at
    _audit(db, teacher, AuditAction.UPDATE, detail={"program_id": str(data.program_id)})
    db.commit()
    return _read(db, teacher_id, user)


def remove_child(db: Session, teacher_id: UUID, child_id: UUID, child_type: str, user) -> TeacherRead:
    teacher = _teacher(db, teacher_id, user)
    model = {"qualifications": TeacherQualification, "certificates": TeacherCertificate,
             "programs": TeacherProgram}[child_type]
    child = db.get(model, child_id)
    if child is None or child.teacher_id != teacher_id:
        raise NotFound("Teacher record not found")
    db.delete(child)
    _audit(db, teacher, AuditAction.UPDATE, detail={"removed": child_type})
    db.commit()
    return _read(db, teacher_id, user)
