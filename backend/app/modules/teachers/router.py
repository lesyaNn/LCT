"""University educator records; manager/admin writes reuse university.edit."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.modules.teachers import service
from app.modules.teachers.schemas import (
    CertificateCreate, QualificationCreate, TeacherCreate, TeacherProgramCreate,
    TeacherRead, TeacherUpdate,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(tags=["Teachers"])
READ = require_permission("university.read")
WRITE = require_permission("university.edit")


@router.get("/universities/{university_id}/teachers", response_model=PaginatedResponse[TeacherRead])
def list_teachers(university_id: UUID, page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db), user: CurrentUser = Depends(READ)):
    items, total = service.list_teachers(db, university_id, page, page_size, user)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/universities/{university_id}/teachers", response_model=TeacherRead, status_code=201)
def create_teacher(university_id: UUID, data: TeacherCreate,
                   db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.create_teacher(db, university_id, data, user)


@router.get("/teachers/{teacher_id}", response_model=TeacherRead)
def get_teacher(teacher_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(READ)):
    return service._read(db, teacher_id, user)


@router.patch("/teachers/{teacher_id}", response_model=TeacherRead)
def update_teacher(teacher_id: UUID, data: TeacherUpdate,
                   db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.update_teacher(db, teacher_id, data, user)


@router.delete("/teachers/{teacher_id}", status_code=204)
def delete_teacher(teacher_id: UUID, db: Session = Depends(get_audit_db),
                   user: CurrentUser = Depends(WRITE)):
    service.delete_teacher(db, teacher_id, user)


@router.post("/teachers/{teacher_id}/qualifications", response_model=TeacherRead)
def add_qualification(teacher_id: UUID, data: QualificationCreate,
                      db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.add_qualification(db, teacher_id, data, user)


@router.post("/teachers/{teacher_id}/certificates", response_model=TeacherRead)
def add_certificate(teacher_id: UUID, data: CertificateCreate,
                    db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.add_certificate(db, teacher_id, data, user)


@router.post("/teachers/{teacher_id}/programs", response_model=TeacherRead)
def add_program(teacher_id: UUID, data: TeacherProgramCreate,
                db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.add_program(db, teacher_id, data, user)


@router.delete("/teachers/{teacher_id}/{child_type}/{child_id}", response_model=TeacherRead)
def remove_child(teacher_id: UUID, child_type: str, child_id: UUID,
                 db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    if child_type not in {"qualifications", "certificates", "programs"}:
        from app.core.exceptions import NotFound
        raise NotFound("Teacher record not found")
    return service.remove_child(db, teacher_id, child_id, child_type, user)
