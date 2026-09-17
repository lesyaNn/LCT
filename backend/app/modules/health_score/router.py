from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.health_score.service import HealthScoreService

router = APIRouter(prefix="/health-score", tags=["health-score"])


class CalcIn(BaseModel):
    missing_docs: bool = False
    stage_delay: bool = False
    teacher_training: bool = False
    missing_license: bool = False
    launch_delay: bool = False


class ScoreOut(BaseModel):
    id: int
    university_id: int
    score: int
    details_json: str

    model_config = {"from_attributes": True}


@router.post("/{university_id}/calculate", response_model=ScoreOut)
def calculate(university_id: int, data: CalcIn, db: Session = Depends(get_db),
              _u: CurrentUser = Depends(get_current_user)):
    return HealthScoreService(db).calculate(university_id, data.model_dump())


@router.get("/{university_id}", response_model=list[ScoreOut])
def history(university_id: int, db: Session = Depends(get_db),
            _u: CurrentUser = Depends(get_current_user)):
    return HealthScoreService(db).history(university_id)
