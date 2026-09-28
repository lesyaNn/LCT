"""P1-08-01 students HTTP API (mounted under /api/v1).

Thin routes: path/body params -> RBAC -> service -> DTO. No SQL and no
business logic here. RBAC reuses the frozen permission names:
``university.read`` for GET, ``university.edit`` for mutations.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.audit.service import get_audit_db
from app.modules.students import service
from app.modules.students.schemas import StudentCreate, StudentRead, StudentSummaryRead, StudentUpdate
from app.schemas.common import PaginatedResponse

router = APIRouter()

READ = require_permission("university.read")
WRITE = require_permission("university.edit")


@router.post(
    "/universities/{university_id}/students",
    response_model=StudentRead,
    status_code=201,
    tags=["Universities"],
    summary="Create student for a university",
)
def create_student(
    university_id: uuid.UUID,
    data: StudentCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> StudentRead:
    return service.create_student(db, university_id, data, user=user)


@router.get(
    "/universities/{university_id}/students",
    response_model=PaginatedResponse[StudentRead],
    tags=["Universities"],
    summary="List university students (paginated, ordered by name)",
)
def list_students(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    program_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(active|graduated|expelled|academic_leave)$"),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[StudentRead]:
    items, total = service.list_student_page(
        db, university_id, page=page, page_size=page_size, user=user,
        program_id=program_id, status=status,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/universities/{university_id}/students/summary", response_model=StudentSummaryRead,
            tags=["Universities"], summary="Learner and flow counts by program")
def get_student_summary(university_id: uuid.UUID, db: Session = Depends(get_audit_db),
                        user: CurrentUser = Depends(READ)) -> StudentSummaryRead:
    return service.student_summary(db, university_id, user=user)


@router.get(
    "/students/{student_id}",
    response_model=StudentRead,
    tags=["Universities"],
    summary="Get student by id",
)
def get_student(
    student_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> StudentRead:
    return service.get_student(db, student_id, user=user)


@router.patch(
    "/students/{student_id}",
    response_model=StudentRead,
    tags=["Universities"],
    summary="Partially update student",
)
def patch_student(
    student_id: uuid.UUID,
    data: StudentUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> StudentRead:
    return service.patch_student(db, student_id, data, user=user)


@router.delete(
    "/students/{student_id}",
    status_code=204,
    response_model=None,
    tags=["Universities"],
    summary="Delete student",
)
def delete_student(
    student_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_student(db, student_id, user=user)
