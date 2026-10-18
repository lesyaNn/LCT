"""CRM ИТ-Школа Ростелеком API.

Methods for managing university relations: catalogs, passports,
XLSX import. Interactive docs: ``/docs`` (Swagger UI), ``/redoc``,
machine-readable spec: ``/openapi.json``.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

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
from app.core.openapi import document_errors
from app.core.swagger import OAUTH2_REDIRECT_HTML

import logging

log = logging.getLogger("rtk.bootstrap.workflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the API without creating visible workflow templates."""
    yield


app = FastAPI(
    title="CRM ИТ-Школа Ростелеком API",
    description="API для управления взаимодействием с ВУЗами",
    version="1.0.0",
    docs_url=None,  # своя страница /docs ниже: нужен oauth2_redirect_url
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_init_oauth={
        "clientId": settings.swagger_oauth_client_id,
        "appName": "CRM API",
        "usePkceWithAuthorizationCodeGrant": True,
        "scopes": ["openid"],
        "additionalQueryStringParams": {"prompt": "login"},
    },
    swagger_ui_parameters={"persistAuthorization": False, "displayRequestDuration": True},
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Assistant", "description": "Помощник по документации и личные диалоги"},
        {"name": "Auth", "description": "Аутентификация через Keycloak"},
        {"name": "Universities", "description": "Каталог ВУЗов и паспорта"},
        {"name": "Workflow", "description": "Workflow engine: шаблоны, экземпляры, переходы"},
        {"name": "Analytics", "description": "Аналитика и дашборд"},
        {"name": "Reports", "description": "Генерация отчётов (XLSX, PDF, JSON)"},
        {"name": "Audit", "description": "Аудит действий"},
        {"name": "Import", "description": "Импорт данных из XLSX"},
        {"name": "Admin Users", "description": "Администрирование пользователей"},
        {"name": "Contracts", "description": "Договоры и файлы"},
        {"name": "Licenses", "description": "Лицензии и PDF-паспорта"},
        {"name": "Education statistics", "description": "Статистика обучения"},
        {"name": "External integrations", "description": "Внешние интеграции"},
        {"name": "Meeting agenda", "description": "Повестки встреч"},
        {"name": "Notifications", "description": "Уведомления"},
        {"name": "Teacher training", "description": "Обучение преподавателей"},
        {"name": "search", "description": "Глобальный поиск"},
        # Production tags retained as documented extensions for the catalog
        # sub-resources and operational endpoints.
        {"name": "Directions", "description": "Направления подготовки (CRUD)"},
        {"name": "Programs", "description": "Программы (CRUD, принадлежат направлению)"},
        {"name": "Products", "description": "Продукты вендоров (CRUD)"},
        {"name": "Vendors", "description": "Вендоры (CRUD)"},
        {"name": "Responsibles", "description": "Ответственные и связки с вузами (CRUD)"},
        {"name": "Catalog", "description": "Каталожный обзор и справочники"},
        {"name": "Service", "description": "Служебные проверки состояния"},
        {"name": "Service API", "description": "Каталог методов и схема интеграции"},
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


@app.get("/docs", include_in_schema=False)
async def swagger_docs(request: Request) -> HTMLResponse:
    """Use the public proxy prefix for both schema and OAuth callback URLs."""
    root_path = request.scope.get("root_path", "").rstrip("/")
    return get_swagger_ui_html(
        openapi_url=root_path + (app.openapi_url or "/openapi.json"),
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=root_path + "/docs/oauth2-redirect.html",
        init_oauth=app.swagger_ui_init_oauth,
        swagger_ui_parameters=app.swagger_ui_parameters,
    )


@app.get("/docs/oauth2-redirect.html", include_in_schema=False)
async def swagger_oauth2_redirect() -> HTMLResponse:
    """Приёмник OAuth2-редиректа Swagger UI (точка возврата из Keycloak)."""
    return HTMLResponse(OAUTH2_REDIRECT_HTML, headers={"Cache-Control": "no-store"})


def custom_openapi():
    """Document either an existing Bearer JWT or Keycloak Authorization Code + PKCE."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
    )
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["HTTPBearer"] = {
        "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        "description": "Вставьте access_token без префикса Bearer. Токен выдаёт Keycloak.",
    }
    base_url = settings.keycloak_issuer.rstrip("/")
    schemes["KeycloakLogin"] = {
        "type": "oauth2",
        "description": (
            "Вход через Keycloak с PKCE. Нажмите Authorize; client_secret не нужен. "
            "Используйте один способ входа: KeycloakLogin или HTTPBearer."
        ),
        "flows": {
            "authorizationCode": {
                "authorizationUrl": base_url + "/protocol/openid-connect/auth",
                "tokenUrl": base_url + "/protocol/openid-connect/token",
                "scopes": {"openid": "Вход через Keycloak"},
            }
        },
    }
    canonical_tag_map = {
        "universities-passport": "Universities",
        "analytics": "Analytics",
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
                # Separate objects mean OR, never require two Authorization headers.
                operation["security"] = [{"HTTPBearer": []}, {"KeycloakLogin": []}]
            document_errors(path, method, operation)

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
    from app.modules.service_api.service import enrich_openapi

    enrich_openapi(app, schema)
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
