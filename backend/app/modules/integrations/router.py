"""Canonical, server-only LMS/Website integration API.

The mock adapter requires an explicit non-production setting. Real provider
contracts are not configured, so the default is a typed 503, never fixtures.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.modules.integrations import service
from app.modules.workflow_instances.service import require_university_scope

router = APIRouter(tags=["External integrations"])


class SyncRequest(BaseModel):
    university_id: uuid.UUID
    source: Literal["lms", "website"]


class ExternalWorkflowRequest(BaseModel):
    university_id: uuid.UUID
    source: Literal["website"]
    external_id: str
    template_id: uuid.UUID | None = None


@router.post("/integrations/sync")
def sync_external(req: SyncRequest, db: Session = Depends(get_audit_db),
                  user: CurrentUser = Depends(require_permission("university.edit"))) -> dict:
    require_university_scope(user, req.university_id)
    return service.sync_mock(db, req.university_id, req.source)


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
