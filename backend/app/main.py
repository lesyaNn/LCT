"""CRM ИТ-Школа Ростелеком API.

Methods for managing university relations: catalogs, passports,
XLSX import. Interactive docs: ``/docs`` (Swagger UI), ``/redoc``,
machine-readable spec: ``/openapi.json``.
"""

from fastapi import FastAPI
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
from app.schemas.errors import ERROR_MESSAGES, ErrorCode

import logging

log = logging.getLogger("rtk.bootstrap.workflow")

# Приёмная страница OAuth2-редиректа — дословный oauth2-redirect.js из
# swagger-ui-dist@5, заинлайненный в один файл (чтобы не тянуть лишний CDN
# и не расширять CSP). Критично передавать redirectUrl в callback: без него
# Swagger UI шлёт обмен кода на токен с redirect_uri=null и Keycloak отвечает
# invalid_grant/Incorrect redirect_uri.
_OAUTH2_REDIRECT_HTML = """<!doctype html>
<html lang="en-US">
<head><title>Swagger UI: OAuth2 Redirect</title></head>
<body>
<script>
"use strict";function run(){var e,r,t,a=window.opener.swaggerUIRedirectOauth2,o=a.state,n=a.redirectUrl;if((t=(r=/code|token|error/.test(window.location.hash)?window.location.hash.substring(1).replace("?","&"):location.search.substring(1)).split("&")).forEach((function(e,r,t){t[r]='"'+e.replace("=",'":"')+'"'})),e=(r=r?JSON.parse("{"+t.join()+"}",(function(e,r){return""===e?r:decodeURIComponent(r)})):{}).state===o,"accessCode"!==a.auth.schema.get("flow")&&"authorizationCode"!==a.auth.schema.get("flow")&&"authorization_code"!==a.auth.schema.get("flow")||a.auth.code)a.callback({auth:a.auth,token:r,isValid:e,redirectUrl:n});else if(e||a.errCb({authId:a.auth.name,source:"auth",level:"warning",message:"Authorization may be unsafe, passed state was changed in server Passed state wasn't returned from auth server"}),r.code)delete a.state,a.auth.code=r.code,a.callback({auth:a.auth,redirectUrl:n});else{let e;r.error&&(e="["+r.error+"]: "+(r.error_description?r.error_description+". ":"no accessCode received from the server. ")+(r.error_uri?"More info: "+r.error_uri:"")),a.errCb({authId:a.auth.name,source:"auth",level:"error",message:e||"[Authorization failed]: no accessCode received from the server"})}window.close()}"loading"!==document.readyState?run():document.addEventListener("DOMContentLoaded",(function(){run()}));
</script>
</body>
</html>"""


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
    # Swagger UI: вход через Keycloak по Authorization Code + PKCE
    # (публичный клиент rtk-frontend, без секрета). Кнопка Authorize ->
    # KeycloakLogin открывает страницу логина Keycloak.
    # prompt=login: страницу логина показывать всегда, даже при живой
    # SSO-сессии (иначе Keycloak молча входит текущим пользователем).
    swagger_ui_init_oauth={
        "clientId": "rtk-frontend",
        "usePkceWithAuthorizationCodeGrant": True,
        "additionalQueryStringParams": {"prompt": "login"},
    },
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


@app.get("/docs", include_in_schema=False)
async def swagger_docs() -> HTMLResponse:
    """Swagger UI. Своя страница вместо docs_url: нужен oauth2_redirect_url.

    Путь относительный: FastAPI сам рендерит
    ``window.location.origin + '/docs/oauth2-redirect.html'``. Абсолютный URL
    сюда передавать нельзя — получится двойной origin и Keycloak ответит
    «Неверный параметр: redirect_uri». Итоговый URI обязан совпадать с записью
    у клиента rtk-frontend в Keycloak.
    """
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url="/docs/oauth2-redirect.html",
        init_oauth=app.swagger_ui_init_oauth,
    )


@app.get("/docs/oauth2-redirect.html", include_in_schema=False)
async def swagger_oauth2_redirect() -> HTMLResponse:
    """Приёмник OAuth2-редиректа Swagger UI (точка возврата из Keycloak)."""
    return HTMLResponse(_OAUTH2_REDIRECT_HTML)


def custom_openapi():
    """Единственная схема входа в спеке — KeycloakLogin (OAuth2 code + PKCE).

    FastAPI выводит ``HTTPBearer`` из auth-зависимости; в Swagger UI она давала
    вторую кнопку Authorize (ручная вставка токена), которая только путала.
    Рантайм по-прежнему принимает Bearer JWT (зависимость не тронута) —
    меняется только документация: все защищённые операции ссылаются на
    KeycloakLogin. Незащищённые операции (``/health``, ``/ready``) остаются открытыми.
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
    # Убираем автогенерированный HTTPBearer: в Swagger остаётся один вход.
    schemes.pop("HTTPBearer", None)
    # OAuth2 authorization code + PKCE: вход через страницу логина Keycloak
    # прямо из Swagger UI (кнопка Authorize -> KeycloakLogin). Пароль вводится
    # только на стороне Keycloak и никогда не касается backend/Swagger.
    # Redirect URI зарегистрирован у клиента rtk-frontend в realm-export.json.
    base_url = settings.keycloak_issuer.rstrip("/")
    schemes["KeycloakLogin"] = {
        "type": "oauth2",
        "description": (
            "Вход через Keycloak (realm rtk, публичный клиент rtk-frontend, "
            "Authorization Code + PKCE). Для авторизации нажмите кнопку "
            "Authorize ниже: откроется страница логина Keycloak — войдите, "
            "токен подставится автоматически."
        ),
        "flows": {
            "authorizationCode": {
                "authorizationUrl": base_url + "/protocol/openid-connect/auth",
                "tokenUrl": base_url + "/protocol/openid-connect/token",
                "scopes": {},
            }
        },
    }
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
                operation["security"] = [{"KeycloakLogin": []}]
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
                if status not in {
                    "400", "401", "403", "404", "409", "410", "413", "415", "422", "429",
                    "500", "503", "504",
                }:
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
