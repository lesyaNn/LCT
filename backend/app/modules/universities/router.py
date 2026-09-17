from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.audit.service import AuditService
from app.modules.universities.repository import UniversityRepository
from app.modules.universities.schemas import UniversityCreate, UniversityOut, UniversityUpdate
from app.modules.universities.service import UniversityService

router = APIRouter(prefix="/universities", tags=["universities"])


def _svc(db: Session = Depends(get_db)) -> UniversityService:
    return UniversityService(UniversityRepository(db))


@router.get("", response_model=list[UniversityOut])
def list_universities(q: str | None = None, region: str | None = None,
                      svc: UniversityService = Depends(_svc),
                      _u: CurrentUser = Depends(get_current_user)):
    return svc.list(q=q, region=region)


@router.post("", response_model=UniversityOut, status_code=201)
def create_university(data: UniversityCreate, svc: UniversityService = Depends(_svc),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    obj = svc.create(data)
    AuditService(db).log(user.id, "university", obj.id, "create", None, {"name": obj.name})
    return obj


@router.get("/{university_id}", response_model=UniversityOut)
def get_university(university_id: int, svc: UniversityService = Depends(_svc),
                   _u: CurrentUser = Depends(get_current_user)):
    return svc.get(university_id)


@router.patch("/{university_id}", response_model=UniversityOut)
def update_university(university_id: int, data: UniversityUpdate,
                      svc: UniversityService = Depends(_svc),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    before = svc.get(university_id)
    before_resp = before.responsible_person_id
    obj = svc.update(university_id, data)
    AuditService(db).log(user.id, "university", obj.id, "update",
                         {"responsible_person_id": before_resp},
                         {"responsible_person_id": obj.responsible_person_id,
                          "status": obj.status})
    return obj
