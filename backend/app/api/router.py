"""API v1 production router.

Mounted: auth, import (file upload + single-sheet catalog import), explicit
external integrations, university passport, meetings,
catalog CRUD/overview, workflow templates/stages, workflow instances (+ canonical
B2 transitions/comments), workflow instance attachments,
and async analytics reports (P4-06-01:
POST queued job + status + download). Deferred forward-stub routers stay
unmounted; see ``docs/DEFERRED_MODULES.md`` for their reactivation requirements.
"""

from fastapi import APIRouter

from app.modules.analytics.reports_router import router as reports_router
from app.modules.analytics.stats_router import router as report_statistics_router
from app.modules.analytics.report_templates import router as report_templates_router
from app.modules.admin_users.router import router as admin_users_router
from app.modules.audit.router import router as audit_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.imports.router import router as imports_router
from app.modules.integrations.router import router as integrations_router
from app.modules.meetings.router import router as meetings_router
from app.modules.education.router import router as education_router
from app.modules.teachers.router import router as teachers_router
from app.modules.universities.passport_router import router as passport_router
from app.modules.workflow_attachments.router import router as workflow_attachments_router
from app.modules.workflow_instances.router import router as workflow_instances_router
from app.modules.workflow_templates.router import router as workflow_templates_router
from app.modules.workflow_transitions.router import router as workflow_transitions_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(admin_users_router)
v1.include_router(imports_router)
v1.include_router(integrations_router)
v1.include_router(passport_router)
v1.include_router(meetings_router)
v1.include_router(education_router)
v1.include_router(teachers_router)
v1.include_router(catalog_router)
v1.include_router(workflow_templates_router)
v1.include_router(workflow_instances_router)
v1.include_router(workflow_transitions_router)
v1.include_router(workflow_attachments_router)
# Templates and statistics BEFORE reports: GET /reports/templates and
# POST /reports/statistics must win over the generic /{job_id} route.
v1.include_router(report_templates_router)
v1.include_router(report_statistics_router)
v1.include_router(reports_router)
v1.include_router(audit_router)
v1.include_router(analytics_router)
