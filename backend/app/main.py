"""CRM ИТ-Школа Ростелеком API.

Methods for managing university relations: catalogs, passports,
XLSX import. Interactive docs: ``/docs`` (Swagger UI), ``/redoc``,
machine-readable spec: ``/openapi.json``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.router import v1
from app.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import request_log_middleware

app = FastAPI(
    title="CRM ИТ-Школа Ростелеком API",
    description=__doc__.strip(),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Universities", "description": "Каталог ВУЗов и паспорта"},
        {"name": "Teachers", "description": "Преподаватели и паспорта"},
        {"name": "Workflow", "description": "Workflow engine: шаблоны, экземпляры, переходы"},
        {"name": "Health Score", "description": "Расчёт и просмотр Health Score"},
        {"name": "Analytics", "description": "Аналитика и дашборд"},
        {"name": "Reports", "description": "Генерация отчётов (XLSX, PDF, JSON)"},
        {"name": "Audit", "description": "Аудит действий"},
        {"name": "Import", "description": "Импорт каталогов из XLSX"},
        {"name": "Admin", "description": "Администрирование (шаблоны, настройки)"},
        {"name": "Auth", "description": "Аутентификация через Keycloak"},
        {"name": "Service", "description": "Служебные проверки состояния"},
    ],
)
register_error_handlers(app)
app.middleware("http")(request_log_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1)


def custom_openapi():
    """Expose the auto-generated BearerAuth scheme under the contract name.

    FastAPI derives ``HTTPBearer`` from the auth dependency; the frozen
    contract (P5-11-01) calls it ``BearerAuth`` with a Keycloak hint, so we
    rename the scheme (and per-operation requirements) after generation.
    Unprotected operations (``/health``, ``/ready``) stay open.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    schemes = schema["components"].get("securitySchemes", {})
    if "HTTPBearer" in schemes:
        schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Keycloak JWT. Получите токен через Keycloak login "
                "(realm rtk) и нажмите Authorize."
            ),
        }
        del schemes["HTTPBearer"]
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if operation.get("security"):
                operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health", tags=["Service"], summary="Liveness-проверка",
         description="Возвращает ok, если API процесс жив.")
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Service"], summary="Readiness-проверка",
         description="Возвращает auth-конфигурацию (issuer, audience, dev bypass).")
def ready():
    return {
        "status": "ready",
        "issuer": settings.keycloak_issuer,
        "audience": settings.keycloak_audience,
        "dev_bypass": settings.auth_dev_bypass,
    }
