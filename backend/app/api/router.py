"""API v1 production router.

Mounted: auth, import, university passport, teacher passport, catalog
CRUD/overview, and the canonical B2 interaction pipeline. Deferred
forward-stub routers stay unmounted; see ``docs/AUDIT.md`` for their
reactivation requirements.
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health_score.health_router import router as health_router
from app.modules.health_score.ranking_router import router as ranking_router
from app.modules.imports.router import router as imports_router
from app.modules.interaction_pipeline.router import router as workflow_router
from app.modules.teachers.passport_router import router as teacher_passport_router
from app.modules.universities.passport_router import router as passport_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
# NOTE: health_router ДО catalog_router: точный путь /universities/health-score
# (batch, P2-08-02) иначе перехватывается GET /universities/{university_id}.
v1.include_router(health_router)
v1.include_router(ranking_router)
v1.include_router(passport_router)
v1.include_router(teacher_passport_router)
v1.include_router(catalog_router)
v1.include_router(workflow_router)
