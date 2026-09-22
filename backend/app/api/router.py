"""API v1 production router.

Mounted: auth, import, university passport, teacher passport, catalog
CRUD/overview, workflow templates/stages, workflow instances, and workflow
instance attachments. Deferred forward-stub routers stay unmounted; see
``docs/AUDIT.md`` for their reactivation requirements.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.imports.router import router as imports_router
from app.modules.teachers.passport_router import router as teacher_passport_router
from app.modules.universities.passport_router import router as passport_router
from app.modules.workflow_attachments.router import router as workflow_attachments_router
from app.modules.workflow_instances.router import router as workflow_instances_router
from app.modules.workflow_templates.router import router as workflow_templates_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
v1.include_router(passport_router)
v1.include_router(teacher_passport_router)
v1.include_router(catalog_router)
v1.include_router(workflow_templates_router)
v1.include_router(workflow_instances_router)
v1.include_router(workflow_attachments_router)
