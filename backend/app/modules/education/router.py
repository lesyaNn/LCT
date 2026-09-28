"""Scoped read API for education statistics."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.education import service
from app.modules.education.schemas import UniversityEducationRead

router = APIRouter(tags=["Education statistics"])


@router.get("/universities/{university_id}/education-statistics", response_model=UniversityEducationRead)
def get_education_statistics(university_id: UUID, db: Session = Depends(get_db),
                             user: CurrentUser = Depends(require_permission("university.read"))):
    return service.university_education(db, university_id, user)
