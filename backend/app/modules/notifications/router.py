"""Notifications stub (queue-ready for worker fan-out).

LEGACY QUARANTINE (H7) — DO NOT MOUNT. The ``task_queue`` backend was
removed (single ledger: ``report_jobs``); this stub stays importable and
answers 410 GONE until a notifications worker exists.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.errors import BusinessException
from app.core.security import CurrentUser, get_current_user
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotifyIn(BaseModel):
    channel: str = "email"
    to: str = ""
    text: str = ""


@router.post("", status_code=202)
def send(data: NotifyIn, _u: CurrentUser = Depends(get_current_user)):
    # H7: no worker behind this queue exists — fail closed with 410.
    raise BusinessException(ErrorCode.GONE)
