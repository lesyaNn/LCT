"""API v1 production router.

Mounted: auth, import, university passport, teacher passport, meetings,
students, catalog CRUD/overview, workflow templates/stages, workflow instances (+ canonical
B2 transitions/comments), workflow instance attachments, health-score
(batch/ranking/history/attention), and async analytics reports (P4-06-01:
POST queued job + status + download). Deferred forward-stub routers stay
unmounted; see ``docs/AUDIT.md`` for their reactivation requirements.
"""

from fastapi import APIRouter

from app.modules.analytics.reports_router import router as reports_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health_score.health_router import router as health_router
from app.modules.health_score.ranking_router import router as ranking_router
from app.modules.imports.router import router as imports_router
from app.modules.meetings.router import router as meetings_router
from app.modules.students.router import router as students_router
from app.modules.teachers.passport_router import router as teacher_passport_router
from app.modules.universities.passport_router import router as passport_router
from app.modules.workflow_attachments.router import router as workflow_attachments_router
from app.modules.workflow_instances.router import router as workflow_instances_router
from app.modules.workflow_templates.router import router as workflow_templates_router
from app.modules.workflow_transitions.router import router as workflow_transitions_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
# NOTE: health_router ДО catalog_router: точный путь /universities/health-score
# (batch, P2-08-02) иначе перехватывается GET /universities/{university_id}.
v1.include_router(health_router)
v1.include_router(ranking_router)
v1.include_router(passport_router)
v1.include_router(teacher_passport_router)
v1.include_router(meetings_router)
v1.include_router(students_router)
v1.include_router(catalog_router)
v1.include_router(workflow_templates_router)
v1.include_router(workflow_instances_router)
v1.include_router(workflow_transitions_router)
v1.include_router(workflow_attachments_router)
v1.include_router(reports_router)
v1.include_router(analytics_router)
