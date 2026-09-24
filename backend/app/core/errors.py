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
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.errors import ERROR_MESSAGES, ERROR_STATUS_MAP, ErrorCode, ErrorResponse

logger = logging.getLogger("rtk")
CONFLICT_DETAIL = "Conflict: duplicate or referenced resource"


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


def _code_for_http(status: int, detail: Any = None) -> ErrorCode:
    text = str(detail or "").lower()
    if status == 401:
        if "expired" in text or "истек" in text:
            return ErrorCode.TOKEN_EXPIRED
        if "invalid" in text or "недейств" in text:
            return ErrorCode.TOKEN_INVALID
        return ErrorCode.AUTH_REQUIRED
    if status == 403:
        return ErrorCode.FORBIDDEN
    if status == 404:
        return ErrorCode.FILE_NOT_FOUND if any(x in text for x in ("file", "файл", "attachment")) else ErrorCode.NOT_FOUND
    if status == 405:
        return ErrorCode.METHOD_NOT_ALLOWED
    if status == 409:
        if "not ready" in text or "не готов" in text:
            return ErrorCode.REPORT_NOT_READY
        if "workflow" in text and "active" in text:
            return ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE
        if "already" in text and ("stage" in text or "closed" in text):
            return ErrorCode.STAGE_ALREADY_COMPLETED
        return ErrorCode.CONFLICT
    if status == 410:
        return ErrorCode.GONE
    if status == 413:
        return ErrorCode.FILE_TOO_LARGE
    if status == 415:
        return ErrorCode.FILE_TYPE_NOT_ALLOWED
    if status == 422:
        return ErrorCode.VALIDATION_ERROR
    if status == 429:
        return ErrorCode.RATE_LIMITED
    if status == 503:
        return ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE
    if status >= 500:
        return ErrorCode.INTERNAL_ERROR
    if status == 400:
        if "transition" in text or "переход" in text:
            return ErrorCode.WORKFLOW_INVALID_TRANSITION
        if "import" in text or "импорт" in text:
            return ErrorCode.IMPORT_VALIDATION_FAILED
    return ErrorCode.HTTP_ERROR


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
                         status_code=exc.status_code, headers=exc.headers or {})

    app.exception_handler(HTTPException)(_http)
    app.exception_handler(StarletteHTTPException)(_http)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        logger.exception("integrity error request_id=%s", _request_id(request), exc_info=exc)
        return _response(request, ErrorCode.CONFLICT)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error request_id=%s %s %s", _request_id(request), request.method,
                         request.url.path, exc_info=exc)
        return _response(request, ErrorCode.INTERNAL_ERROR)


__all__ = ["BusinessException", "SecurityError", "register_error_handlers"]
