"""Canonical, server-only LMS/Website integration API.

The mock adapter requires an explicit non-production setting. Real provider
contracts are not configured, so the default is a typed 503, never fixtures.
"""

from __future__ import annotations

import uuid
from typing import Literal
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.modules.integrations import service
from app.modules.workflow_instances.service import require_university_scope
from app.modules.students.schemas import StudentStatus

router = APIRouter(tags=["External integrations"])


class SyncRequest(BaseModel):
    university_id: uuid.UUID
    source: Literal["lms", "website"]


class ExternalWorkflowRequest(BaseModel):
    university_id: uuid.UUID
    source: Literal["website"]
    external_id: str
    template_id: uuid.UUID | None = None


class LmsLearnerRecord(BaseModel):
    """CRM-owned JSON contract; not a claim about the customer's LMS API."""
    external_id: str = Field(min_length=1, max_length=256)
    program_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=512)
    group_name: str | None = Field(default=None, max_length=256)
    status: StudentStatus = StudentStatus.ACTIVE
    started_at: date
    progress: int | None = Field(default=None, ge=0, le=100)


class LmsIngestRequest(BaseModel):
    university_id: uuid.UUID
    learners: list[LmsLearnerRecord] = Field(max_length=1000)


class WebsiteApplicationRecord(BaseModel):
    """CRM-owned website DTO; provider API can later map into this contract."""
    external_id: str = Field(min_length=1, max_length=256)
    program_id: uuid.UUID
    person_name: str | None = Field(default=None, max_length=512)
    status: str = Field(default="new", max_length=64)
    flow_name: str | None = Field(default=None, max_length=256)
    external_created_at: datetime


class WebsiteIngestRequest(BaseModel):
    university_id: uuid.UUID
    applications: list[WebsiteApplicationRecord] = Field(max_length=1000)


@router.get("/integrations/capabilities", summary="Configured external adapter capabilities")
def integration_capabilities(
    _user: CurrentUser = Depends(require_permission("university.read")),
) -> dict:
    return {"demo_lms_enabled": service.mock_enabled(),
            "demo_website_enabled": service.mock_enabled(),
            "live_provider_configured": False}


@router.post("/integrations/sync")
def sync_external(req: SyncRequest, db: Session = Depends(get_audit_db),
                  user: CurrentUser = Depends(require_permission("university.edit"))) -> dict:
    require_university_scope(user, req.university_id)
    return service.sync_mock(db, req.university_id, req.source)


@router.post("/integrations/lms/ingest", summary="Ingest CRM-owned LMS JSON contract")
def ingest_lms(req: LmsIngestRequest, db: Session = Depends(get_audit_db),
               user: CurrentUser = Depends(require_permission("university.edit"))) -> dict:
    require_university_scope(user, req.university_id)
    return service.ingest_lms(db, req.university_id,
                              [item.model_dump(mode="python") for item in req.learners])


@router.post("/integrations/website/ingest", summary="Ingest CRM-owned website JSON contract")
def ingest_website(req: WebsiteIngestRequest, db: Session = Depends(get_audit_db),
                   user: CurrentUser = Depends(require_permission("university.edit"))) -> dict:
    require_university_scope(user, req.university_id)
    return service.ingest_website(db, req.university_id,
                                  [item.model_dump(mode="python") for item in req.applications])


@router.get("/universities/{university_id}/external-data")
def get_university_external_data(
    university_id: uuid.UUID,
    source: Literal["lms", "website"] = Query(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> dict:
    require_university_scope(user, university_id)
    return service.university_data(db, university_id, source)


@router.get("/integrations/metrics")
def get_integration_metrics(db: Session = Depends(get_db),
                            _user: CurrentUser = Depends(require_permission("analytics.read"))) -> dict:
    return service.metrics(db, _user)


@router.post("/workflow/instances/from-external")
def create_workflow_from_external(
    req: ExternalWorkflowRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("workflow.change_status")),
) -> dict:
    require_university_scope(user, req.university_id)
    return service.create_workflow_from_application(db, req.university_id, req.external_id,
                                                    req.template_id, user.id)
