"""P1-05-01: GET /api/v1/teachers/{id}/passport.

Thin route: params -> auth/RBAC -> service -> DTO. No SQL, no business logic
here (architecture rule API -> Service -> Model/Repository).

The legacy int-PK teachers CRUD router (``app.modules.teachers.router``)
stays UNMOUNTED — it targets the pre-P1 integer schema and is incompatible
with the canonical UUID models. This passport router is UUID-native.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.teachers import passport_service
from app.modules.teachers.passport_schemas import TeacherPassport

router = APIRouter(prefix="/teachers", tags=["Teachers"])

_NOT_FOUND = {"description": "Teacher not found"}
_UNAUTHORIZED = {"description": "Missing bearer token"}
_FORBIDDEN = {"description": "Forbidden: need university.read"}


@router.get(
    "/{teacher_id}/passport",
    response_model=TeacherPassport,
    summary="Teacher digital passport (qualifications, certificates, programs, readiness)",
    responses={
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
def get_teacher_passport(
    teacher_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> TeacherPassport:
    return passport_service.get_teacher_passport(db, teacher_id)
