"""Contextual teacher training API; no global HR catalogue."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.modules.teachers import service
from app.modules.teachers.schemas import (
    TeacherCreate, TeacherProgramCreate, TeacherProgramUpdate, TeacherRead, TeacherUpdate,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(tags=["Teacher training"])
READ = require_permission("university.read")
WRITE = require_permission("university.edit")


@router.get(
    "/universities/{university_id}/teachers",
    response_model=PaginatedResponse[TeacherRead],
    summary="Список преподавателей вуза",
    description="Возвращает пагинированный список преподавателей вуза (query-параметры page, page_size). Требуется право university.read.",
)
def list_teachers(university_id: UUID, page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db), user: CurrentUser = Depends(READ)):
    items, total = service.list_teachers(db, university_id, page, page_size, user)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "/universities/{university_id}/teachers",
    response_model=TeacherRead,
    status_code=201,
    summary="Создание преподавателя",
    description="Создаёт преподавателя в контексте вуза (university_id в пути). Требуется право university.edit.",
)
def create_teacher(university_id: UUID, data: TeacherCreate,
                   db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.create_teacher(db, university_id, data, user)


@router.get(
    "/teachers/{teacher_id}",
    response_model=TeacherRead,
    summary="Карточка преподавателя",
    description="Возвращает преподавателя по идентификатору teacher_id. Требуется право university.read.",
)
def get_teacher(teacher_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(READ)):
    return service.get_teacher(db, teacher_id, user)


@router.patch(
    "/teachers/{teacher_id}",
    response_model=TeacherRead,
    summary="Обновление преподавателя",
    description="Частично обновляет данные преподавателя по идентификатору teacher_id. Требуется право university.edit.",
)
def update_teacher(teacher_id: UUID, data: TeacherUpdate,
                   db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.update_teacher(db, teacher_id, data, user)


@router.post(
    "/teachers/{teacher_id}/programs",
    response_model=TeacherRead,
    summary="Добавление программы преподавателю",
    description="Привязывает образовательную программу к преподавателю (teacher_id в пути). Требуется право university.edit.",
)
def add_program(teacher_id: UUID, data: TeacherProgramCreate,
                db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.add_program(db, teacher_id, data, user)


@router.patch(
    "/teachers/{teacher_id}/programs/{program_id}",
    response_model=TeacherRead,
    summary="Обновление программы преподавателя",
    description="Обновляет привязку программы program_id у преподавателя teacher_id. Требуется право university.edit.",
)
def update_program(teacher_id: UUID, program_id: UUID, data: TeacherProgramUpdate,
                   db: Session = Depends(get_audit_db), user: CurrentUser = Depends(WRITE)):
    return service.update_program(db, teacher_id, program_id, data, user)
