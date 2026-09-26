"""Centralized public error handling for every API route."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.errors import (
    ERROR_MESSAGES,
    ERROR_STATUS_MAP,
    ConflictDetails,
    ErrorCode,
    ErrorResponse,
)

logger = logging.getLogger("rtk")


class BusinessException(HTTPException):
    """Canonical domain error resolved through the central registry."""

    def __init__(self, code: ErrorCode, *, details: Mapping[str, Any] | None = None,
                 message: str | None = None, status_code: int | None = None) -> None:
        self.code = ErrorCode(code)
        self.status_code = status_code if status_code is not None else ERROR_STATUS_MAP[self.code]
        self.message = message or ERROR_MESSAGES[self.code]
        self.details = dict(details or {})
        # HTTPException inheritance preserves status handling for small test
        # apps/third-party mounts that do not install the project handlers;
        # the production app replaces that default with the ErrorResponse
        # handler registered below.
        super().__init__(status_code=self.status_code, detail=self.code.value)
        # Keep the original domain text for server-side/unit-test diagnostics;
        # the HTTP handler always renders the safe registry message.
        self.args = (self.message,)

    def __str__(self) -> str:
        return self.message


class SecurityError(BusinessException):
    """Auth/RBAC error whose public details are always empty."""

    def __init__(self, code: ErrorCode):
        super().__init__(code, details={})


class ConflictError(BusinessException):
    """A 409 with an optional, safe field identifier (never a DB value)."""

    def __init__(self, *, field: str | None = None) -> None:
        details = ConflictDetails(field=field).model_dump() if field else {}
        super().__init__(ErrorCode.CONFLICT, details=details)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid4())


def _safe_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    blocked = re.compile(r"password|token|authorization|secret|cookie|binary|jwt", re.I)
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if blocked.search(str(key)):
            continue
        try:
            encoded = jsonable_encoder(value)
        except Exception:
            encoded = "[redacted]"
        text = str(encoded)
        safe[str(key)] = "[redacted]" if (blocked.search(text)
                                            or "postgresql://" in text.lower()
                                            or "/tmp/" in text) else encoded
    return safe


def _response(request: Request, code: ErrorCode, *, details: Mapping[str, Any] | None = None,
              status_code: int | None = None, headers: Mapping[str, str] | None = None) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorResponse(error={"code": code, "message": ERROR_MESSAGES[code],
                                "request_id": request_id, "details": _safe_details(details)})
    out_headers = {"X-Request-ID": request_id}
    if headers:
        out_headers.update(dict(headers))
    if code in {ErrorCode.AUTH_REQUIRED, ErrorCode.TOKEN_EXPIRED, ErrorCode.TOKEN_INVALID}:
        out_headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=status_code or ERROR_STATUS_MAP[code],
                        content=body.model_dump(mode="json"), headers=out_headers)


_DEFAULT_HTTP_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.HTTP_ERROR,
    401: ErrorCode.AUTH_REQUIRED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    410: ErrorCode.GONE,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.FILE_TYPE_NOT_ALLOWED,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE,
}


def _explicit_error_code(detail: Any) -> ErrorCode | None:
    """Read a code only from a typed/exact value; never infer it from prose."""
    raw = detail.get("code") if isinstance(detail, Mapping) else detail
    if isinstance(raw, ErrorCode):
        return raw
    if isinstance(raw, str):
        try:
            return ErrorCode(raw)
        except ValueError:
            return None
    return None


def _code_for_http(status: int, detail: Any = None) -> ErrorCode:
    explicit = _explicit_error_code(detail)
    if explicit is not None:
        return explicit
    if status >= 500:
        return ErrorCode.INTERNAL_ERROR
    return _DEFAULT_HTTP_CODES.get(status, ErrorCode.HTTP_ERROR)


def _http_details(detail: Any) -> Mapping[str, Any] | None:
    if not isinstance(detail, Mapping) or not isinstance(detail.get("details"), Mapping):
        return None
    return detail["details"]


_CONSTRAINT_FIELDS = {
    "universities_name_key": "name",
    "it_directions_code_key": "code",
    "vendors_name_key": "name",
    "responsibles_email_key": "email",
    "responsibles_keycloak_sub_key": "keycloak_sub",
    "uq_it_products_vendor_name_version": "vendor_id,name,version",
    "uq_university_programs_uni_prog": "program_id",
    "uq_university_responsibles_uni_resp": "responsible_id",
}


def _conflict_details(exc: IntegrityError) -> dict[str, str]:
    """Extract column names from driver metadata without exposing SQL/values."""
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    column = getattr(diagnostic, "column_name", None)
    if isinstance(column, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
        return ConflictDetails(field=column).model_dump()
    constraint = getattr(diagnostic, "constraint_name", None)
    if isinstance(constraint, str) and constraint in _CONSTRAINT_FIELDS:
        return ConflictDetails(field=_CONSTRAINT_FIELDS[constraint]).model_dump()
    match = re.search(r"Key \(([^)]+)\)=", str(original or ""))
    if match:
        fields = [part.strip() for part in match.group(1).split(",")]
        if fields and all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in fields
        ):
            return ConflictDetails(field=",".join(fields)).model_dump()
    return {}


def _validation_details(exc: RequestValidationError) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    for item in exc.errors():
        loc = item.get("loc", ())
        parts = [str(part) for part in loc if part not in {"body", "query", "path", "header"}]
        field = ".".join(parts) or "request"
        if re.search(r"password|token|authorization|secret|binary|file", field, re.I):
            field = "request"
        msg = str(item.get("msg", "Некорректное значение"))
        if re.search(r"password|token|authorization|secret|binary|file|postgresql://|/tmp/", msg, re.I):
            msg = "Некорректное значение"
        errors.append({"field": field, "message": msg, "type": str(item.get("type", "value_error"))})
    return {"field_errors": errors}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessException)
    async def _business(request: Request, exc: BusinessException):
        return _response(request, exc.code, details={} if exc.code == ErrorCode.FORBIDDEN else exc.details,
                         status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _response(request, ErrorCode.VALIDATION_ERROR, details=_validation_details(exc))

    @app.exception_handler(ResponseValidationError)
    async def _response_validation(request: Request, exc: ResponseValidationError):
        logger.exception("response validation error request_id=%s", _request_id(request), exc_info=exc)
        return _response(request, ErrorCode.INTERNAL_ERROR)

    async def _http(request: Request, exc: HTTPException | StarletteHTTPException):
        return _response(request, _code_for_http(exc.status_code, exc.detail),
                         details=_http_details(exc.detail), status_code=exc.status_code,
                         headers=exc.headers or {})

    app.exception_handler(HTTPException)(_http)
    app.exception_handler(StarletteHTTPException)(_http)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        logger.exception("integrity error request_id=%s", _request_id(request), exc_info=exc)
        return _response(request, ErrorCode.CONFLICT, details=_conflict_details(exc))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error request_id=%s %s %s", _request_id(request), request.method,
                         request.url.path, exc_info=exc)
        return _response(request, ErrorCode.INTERNAL_ERROR)


__all__ = ["BusinessException", "ConflictError", "SecurityError", "register_error_handlers"]
