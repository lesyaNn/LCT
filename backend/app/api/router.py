"""API v1 router.

Mounted (production contract): ``auth / import / passport / catalog``.
Everything else in ``app.modules`` is DEFERRED forward scaffolding for the
next stages — see ``docs/AUDIT.md`` (§0) for the module table and the
reactivation checklist. Do NOT mount a deferred router without completing
that checklist (UUID PKs, keycloak_sub identity, SQL migration, RBAC,
pagination, tests).
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.imports.router import router as imports_router
from app.modules.universities.passport_router import router as passport_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
v1.include_router(passport_router)
v1.include_router(catalog_router)
