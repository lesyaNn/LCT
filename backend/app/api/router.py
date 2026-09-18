"""API v1 router.

MINIMAL AUTH STAGE: only `auth` is mounted.
Domain routers (universities/teachers/programs/workflow/documents/...)
will be re-enabled at the next stage (PostgreSQL domain schema).
"""
from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.imports.router import router as imports_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
