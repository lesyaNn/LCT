from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.audit.models import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    user_id: int
    entity_type: str
    entity_id: int
    action: str
    before_data: str
    after_data: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditOut])
def list_audit(entity_type: str | None = None, entity_id: int | None = None,
               db: Session = Depends(get_db),
               _u: CurrentUser = Depends(get_current_user)):
    q = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(200)
    rows = q.all()
    if entity_type:
        rows = [r for r in rows if r.entity_type == entity_type]
    if entity_id:
        rows = [r for r in rows if r.entity_id == entity_id]
    return rows
