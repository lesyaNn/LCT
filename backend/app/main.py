"""Minimal auth stack entrypoint.

NOTE (minimal auth stage): only the auth module is mounted.
Domain modules (universities/teachers/programs/workflow/...) stay on disk
but are NOT imported — no domain tables are created at this stage.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import v1
from app.config import settings
from app.core.logging import request_log_middleware

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Minimal auth stack: Keycloak JWT -> FastAPI RBAC",
)
app.middleware("http")(request_log_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {
        "status": "ready",
        "issuer": settings.keycloak_issuer,
        "audience": settings.keycloak_audience,
        "dev_bypass": settings.auth_dev_bypass,
    }
