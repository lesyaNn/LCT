from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.db.session import get_db
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherIn, TeacherOut

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("", response_model=list[TeacherOut])
def list_teachers(university_id: int | None = None, db: Session = Depends(get_db),
                  _u: CurrentUser = Depends(get_current_user)):
    q = db.query(Teacher)
    if university_id:
        q = q.filter(Teacher.university_id == university_id)
    return q.order_by(Teacher.id.desc()).limit(200).all()


@router.post("", response_model=TeacherOut, status_code=201)
def create_teacher(data: TeacherIn, db: Session = Depends(get_db),
                   _u: CurrentUser = Depends(get_current_user)):
    obj = Teacher(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db),
                _u: CurrentUser = Depends(get_current_user)):
    obj = db.get(Teacher, teacher_id)
    if not obj:
        raise BusinessException(ErrorCode.NOT_FOUND)
    return obj
