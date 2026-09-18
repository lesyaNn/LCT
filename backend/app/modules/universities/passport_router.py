"""P1-04-01/05/06: GET /api/v1/universities/{id}/passport + subresources.

Thin routes: params -> auth/RBAC -> service -> DTO. No SQL, no business
logic here (architecture rule API -> Service -> Model/Repository).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.universities.passport_schemas import (
    PaginatedPrograms,
    PaginatedTeachers,
    UniversityPassport,
)
from app.modules.universities.passport_service import (
    get_passport,
    get_programs_page,
    get_teachers_page,
    parse_include,
)

router = APIRouter(prefix="/universities", tags=["universities-passport"])


@router.get(
    "/{university_id}/passport",
    response_model=UniversityPassport,
    summary="University digital passport (aggregated)",
)
def get_university_passport(
    university_id: uuid.UUID,
    include: str | None = Query(
        default=None,
        description="Optional blocks, comma-separated: health_score, audit",
    ),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> UniversityPassport:
    blocks = parse_include(include)
    return get_passport(db, university_id, include=blocks)


@router.get(
    "/{university_id}/passport/programs",
    response_model=PaginatedPrograms,
    summary="University passport programs (paginated)",
)
def get_university_passport_programs(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> PaginatedPrograms:
    items, total = get_programs_page(db, university_id, page, page_size)
    return PaginatedPrograms(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/{university_id}/passport/teachers",
    response_model=PaginatedTeachers,
    summary="University passport teachers (paginated)",
)
def get_university_passport_teachers(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> PaginatedTeachers:
    items, total = get_teachers_page(db, university_id, page, page_size)
    return PaginatedTeachers(items=items, page=page, page_size=page_size, total=total)
