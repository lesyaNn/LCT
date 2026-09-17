"""Notifications stub (queue-ready for worker fan-out)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.infrastructure import task_queue

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotifyIn(BaseModel):
    channel: str = "email"
    to: str = ""
    text: str = ""


@router.post("", status_code=202)
def send(data: NotifyIn, _u: CurrentUser = Depends(get_current_user)):
    job_id = task_queue.enqueue("notify", data.model_dump())
    return {"job_id": job_id, "status": "queued"}
