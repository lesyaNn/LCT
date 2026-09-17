"""Integration adapters (§17): LMS / website via Adapter -> Internal DTO.

External API change => only adapter changes, domain untouched.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import CurrentUser, get_current_user
from app.infrastructure.http_client import http_client

router = APIRouter(prefix="/integrations", tags=["integrations"])


class SyncReq(BaseModel):
    source: str = "lms"  # lms | website


class LMSAdapter:
    @staticmethod
    def to_internal(external: dict) -> dict:
        return {"external_id": external.get("id"), "title": external.get("course_name", ""),
                "enrolled": external.get("students", 0)}


@router.post("/sync")
async def sync(req: SyncReq, _u: CurrentUser = Depends(get_current_user)):
    # Stub: in prod calls real LMS/website API via client + adapter.
    _ = http_client()
    sample = {"id": "ext-1", "course_name": "Python Base", "students": 120}
    dto = LMSAdapter.to_internal(sample) if req.source == "lms" else {"ok": True}
    return {"source": req.source, "status": "synced", "dto": dto}


@router.get("/status")
def status(_u: CurrentUser = Depends(get_current_user)):
    return {"lms": "not_configured", "website": "not_configured"}
