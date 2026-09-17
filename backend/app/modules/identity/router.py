from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.identity.schemas import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)):
    return UserOut(id=user.id, full_name=user.full_name, email=user.email or "admin@rtk.local")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _u: CurrentUser = Depends(get_current_user)):
    rows = db.query(User).limit(100).all()
    return [UserOut.model_validate(r) for r in rows]


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db),
                _u: CurrentUser = Depends(get_current_user)):
    u = User(full_name=data.full_name, email=str(data.email),
             organization_id=data.organization_id, external_id=str(data.email))
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)
