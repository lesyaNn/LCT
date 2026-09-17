from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.programs.models import Program
from app.modules.programs.schemas import ProgramIn, ProgramOut

router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("", response_model=list[ProgramOut])
def list_programs(university_id: int | None = None, db: Session = Depends(get_db),
                  _u: CurrentUser = Depends(get_current_user)):
    q = db.query(Program)
    if university_id:
        q = q.filter(Program.university_id == university_id)
    return q.order_by(Program.id.desc()).limit(200).all()


@router.post("", response_model=ProgramOut, status_code=201)
def create_program(data: ProgramIn, db: Session = Depends(get_db),
                   _u: CurrentUser = Depends(get_current_user)):
    obj = Program(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{program_id}", response_model=ProgramOut)
def update_program(program_id: int, data: ProgramIn, db: Session = Depends(get_db),
                   _u: CurrentUser = Depends(get_current_user)):
    obj = db.get(Program, program_id)
    if not obj:
        raise HTTPException(404, "Program not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj
