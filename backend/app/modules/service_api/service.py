"""Describe mounted routes without duplicating CRUD or executing dependencies."""

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.config import settings
from app.core.middleware import RATE_LIMITED_PATHS
from app.core.permissions import PUBLIC_ROLE_NAMES, effective_role, user_permissions
from app.core.security import CurrentUser
from app.modules.service_api.examples import REQUEST_EXAMPLES
from app.modules.service_api.schemas import (
    ApiError,
    Authentication,
    Limits,
    Operation,
    ServiceApiCatalog,
)
from app.schemas.errors import ERROR_MESSAGES, ERROR_STATUS_MAP

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Access:
    permissions: frozenset[str]
    role_checks: tuple[frozenset[str], ...]

    def permits(self, user: CurrentUser) -> bool:
        return self.permissions <= user_permissions(user) and all(
            check & user.roles for check in self.role_checks
        )

    @property
    def roles(self) -> list[str]:
        return sorted(role for role in PUBLIC_ROLE_NAMES if self.permits(CurrentUser(roles={role})))


def access_for(dependant: Dependant) -> Access:
    permissions: set[str] = set()
    role_checks: list[frozenset[str]] = []
    pending = [dependant]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        permission = getattr(current.call, "api_required_permission", None)
        if permission:
            permissions.add(permission)
        roles = getattr(current.call, "api_allowed_roles", None)
        if roles is not None:
            role_checks.append(frozenset(roles))
        pending.extend(current.dependencies)
    return Access(frozenset(permissions), tuple(role_checks))


def api_routes(app: FastAPI):
    for route in app.routes:
        if (
            isinstance(route, APIRoute)
            and route.include_in_schema
            and route.path.startswith("/api/v1/")
        ):
            for method in sorted(route.methods & METHODS):
                yield route, method


def enrich_openapi(app: FastAPI, schema: dict) -> None:
    """Static access metadata only. Never put a caller's identity in cached OpenAPI."""
    for route, method in api_routes(app):
        operation = schema["paths"][route.path_format][method.lower()]
        access = access_for(route.dependant)
        authentication_required = bool(operation.get("security"))
        operation["x-authentication-required"] = authentication_required
        operation["x-required-permissions"] = sorted(access.permissions)
        operation["x-allowed-roles"] = access.roles if authentication_required else []
        example = REQUEST_EXAMPLES.get((route.path_format, method.lower()))
        if example is not None:
            operation["requestBody"]["content"]["application/json"]["example"] = example


def catalog(app: FastAPI, user: CurrentUser) -> ServiceApiCatalog:
    schema = app.openapi()
    operations = []
    for route, method in api_routes(app):
        operation = schema["paths"][route.path_format][method.lower()]
        access = access_for(route.dependant)
        authentication_required = bool(operation.get("security"))
        operations.append(
            Operation(
                operation_id=operation["operationId"],
                method=method,
                path=route.path_format,
                summary=operation["summary"],
                tags=operation.get("tags", []),
                authentication_required=authentication_required,
                required_permissions=sorted(access.permissions),
                allowed_roles=access.roles if authentication_required else [],
                role_allowed=not authentication_required or access.permits(user),
                deprecated=operation.get("deprecated", False),
            )
        )
    operations.sort(key=lambda item: (item.path, item.method))
    issuer = settings.keycloak_issuer.rstrip("/")
    return ServiceApiCatalog(
        version=app.version,
        base_path="/api/v1",
        documentation_path="/api",
        openapi_path="/api/v1/openapi.json",
        authentication=Authentication(
            issuer=issuer,
            token_url=issuer + "/protocol/openid-connect/token",
            audience=settings.keycloak_audience,
        ),
        role=effective_role(user),
        permissions=sorted(user_permissions(user)),
        operation_count=len(operations),
        operations=operations,
        limits=Limits(
            heavy_requests_per_minute=settings.rate_limit_per_minute,
            heavy_paths=list(RATE_LIMITED_PATHS),
            assistant_requests_per_minute=settings.assistant_rate_limit_per_minute,
            assistant_timeout_seconds=settings.assistant_timeout_seconds,
            max_upload_mb=settings.max_upload_mb,
        ),
        errors=[
            ApiError(code=code.value, status=ERROR_STATUS_MAP[code], message=message)
            for code, message in ERROR_MESSAGES.items()
        ],
    )
