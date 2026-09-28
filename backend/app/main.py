"""CRM ИТ-Школа Ростелеком API.

Methods for managing university relations: catalogs, passports,
XLSX import. Interactive docs: ``/docs`` (Swagger UI), ``/redoc``,
machine-readable spec: ``/openapi.json``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from contextlib import asynccontextmanager

from app.api.router import v1
from app.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import request_log_middleware
from app.core.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.schemas.errors import ERROR_MESSAGES, ErrorCode

import logging

log = logging.getLogger("rtk.bootstrap.workflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup baseline bootstraps (migrations already applied by entrypoint).

    Ensures the standard workflow template exists on every backend start.
    Fail-open by design (consistent with the rest of the startup path):
    a DB failure is logged with traceback and retried on the next
    start; it never prevents the API process from serving /health.
    """
    try:
        from app.bootstrap.workflow_defaults import ensure_default_workflow_template, ensure_spec_workflow_template
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            ensure_default_workflow_template(db)
            ensure_spec_workflow_template(db)
        finally:
            db.close()
    except Exception:
        log.exception("[bootstrap] Standard workflow template bootstrap failed")
    yield


app = FastAPI(
    title="CRM ИТ-Школа Ростелеком API",
    description="API для управления взаимодействием с ВУЗами",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Auth", "description": "Аутентификация через Keycloak"},
        {"name": "Universities", "description": "Каталог ВУЗов и паспорта"},
        {"name": "Workflow", "description": "Workflow engine: шаблоны, экземпляры, переходы"},
        {"name": "Analytics", "description": "Аналитика и дашборд"},
        {"name": "Reports", "description": "Генерация отчётов (XLSX, PDF, JSON)"},
        {"name": "Audit", "description": "Аудит действий"},
        {"name": "Import", "description": "Импорт данных из XLSX"},
        {"name": "Admin", "description": "Администрирование"},
        # Production tags retained as documented extensions for the catalog
        # sub-resources and operational endpoints.
        {"name": "Directions", "description": "Направления подготовки (CRUD)"},
        {"name": "Programs", "description": "Программы (CRUD, принадлежат направлению)"},
        {"name": "Products", "description": "Продукты вендоров (CRUD)"},
        {"name": "Vendors", "description": "Вендоры (CRUD)"},
        {"name": "Responsibles", "description": "Ответственные и связки с вузами (CRUD)"},
        {"name": "Catalog", "description": "Каталожный обзор и справочники"},
        {"name": "Service", "description": "Служебные проверки состояния"},
    ],
)
register_error_handlers(app)
app.middleware("http")(request_log_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# M10 last: runs first (innermost registration executes first) so abusive
# heavy-endpoint traffic is shed before auth/DB work. Fail-open by design.
app.add_middleware(
    RateLimitMiddleware,
    limit_per_minute=settings.rate_limit_per_minute,
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
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
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
    canonical_tag_map = {
        "universities-passport": "Universities",
        "analytics": "Analytics",
    }
    error_examples = {
        "401": ErrorCode.AUTH_REQUIRED,
        "403": ErrorCode.FORBIDDEN,
        "404": ErrorCode.NOT_FOUND,
        "409": ErrorCode.CONFLICT,
        "422": ErrorCode.VALIDATION_ERROR,
        "500": ErrorCode.INTERNAL_ERROR,
    }
    error_schema = {"$ref": "#/components/schemas/ErrorResponse"}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            # A small number of older routers supplied summaries only.  Keep
            # those stable while guaranteeing a useful, non-empty description.
            if not operation.get("description"):
                operation["description"] = operation.get("summary") or (
                    f"Операция {method.upper()} {path}."
                )
            operation["tags"] = [canonical_tag_map.get(tag, tag) for tag in operation.get("tags", [])]
            if path.startswith("/api/v1") and operation.get("security"):
                operation["security"] = [{"BearerAuth": []}]
                operation.setdefault("responses", {}).setdefault("401", {
                    "description": "Требуется действительный Bearer JWT.",
                })
                operation.setdefault("responses", {}).setdefault("403", {
                    "description": "Недостаточно прав.",
                })
            if path.startswith("/api/v1"):
                operation.setdefault("responses", {}).setdefault("422", {
                    "description": "Ошибка валидации запроса.",
                })
            for status, response in operation.get("responses", {}).items():
                if status not in {"400", "401", "403", "404", "409", "410", "413", "415", "422", "429", "500", "503"}:
                    continue
                response.setdefault("content", {})["application/json"] = {
                    "schema": error_schema,
                }
                code = error_examples.get(status, ErrorCode.HTTP_ERROR)
                message = ERROR_MESSAGES[code]
                response["content"]["application/json"]["examples"] = {
                    code: {"summary": code, "value": {"error": {
                        "code": code,
                        "message": message,
                        "request_id": "00000000-0000-4000-8000-000000000000",
                        "details": {},
                    }}}
                }

    # Representative payloads make the main flows reviewable in Swagger.
    for path, method, example in (
        ("/api/v1/universities", "post", {"name": "МГТУ им. Н.Э. Баумана", "city": "Москва"}),
        ("/api/v1/universities/{university_id}", "patch", {"name": "МГТУ им. Н.Э. Баумана"}),
        ("/api/v1/workflow/instances/{instance_id}/transition", "post", {
            "target_instance_stage_id": "00000000-0000-4000-8000-000000000001",
            "comment": "Документы проверены",
        }),
    ):
        body = schema["paths"].get(path, {}).get(method, {}).get("requestBody")
        if body:
            body.setdefault("content", {}).setdefault("application/json", {})["example"] = example

    # Keep an explicit list of response components for consumers that prefer
    # component-level references over inline operation responses.
    schema["components"].setdefault("responses", {})["ErrorResponse"] = {
        "description": "Единый формат ошибки API.",
        "content": {"application/json": {"schema": error_schema}},
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health", tags=["Service"], summary="Liveness-проверка",
         description="Возвращает ok, если API процесс жив.")
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Service"], summary="Readiness-проверка",
         description="Возвращает готовность API. Детали auth-конфигурации намеренно не раскрываются.")
def ready():
    return {"status": "ready"}
