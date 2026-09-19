"""API v1 router.

Mounted: auth, import, university passport, teacher passport (P1-05),
catalog CRUD (P1-03: universities/directions/programs/products/vendors/
responsibles).
Legacy ``universities``/``programs``/``teachers`` routers stay unmounted:
they target the pre-P1 integer schema and are incompatible with the
canonical UUID models (see gap pins in ``tests/test_p1_crud.py`` history).
"""

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.imports.router import router as imports_router
from app.modules.teachers.passport_router import router as teacher_passport_router
from app.modules.universities.passport_router import router as passport_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(imports_router)
v1.include_router(passport_router)
v1.include_router(teacher_passport_router)
v1.include_router(catalog_router)
