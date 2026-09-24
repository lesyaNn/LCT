"""HTTP security middleware shared by the API and its error responses.

The middleware is deliberately ASGI-native.  Request bodies are counted as
they arrive, so a client cannot bypass the limit by omitting
``Content-Length`` or by using chunked transfer encoding.
"""

from __future__ import annotations

import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.errors import ERROR_MESSAGES, ErrorCode, ErrorResponse

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
# Multipart framing adds headers and boundaries around the canonical 50 MiB
# file-content limit.  Keep a bounded allowance without weakening the file
# stream limiter in workflow_attachments.service.
REQUEST_BODY_LIMIT_BYTES = MAX_FILE_SIZE_BYTES + 1024 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # FastAPI docs use jsDelivr for their pinned UI bundles and an inline
    # bootstrap script.  No wildcard sources are allowed.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "connect-src 'self'"
    ),
}


def _request_id(scope: Scope) -> str:
    headers = Headers(scope=scope)
    supplied = headers.get("x-request-id")
    try:
        return str(uuid.UUID(supplied)) if supplied else str(uuid.uuid4())
    except (ValueError, TypeError):
        return str(uuid.uuid4())


def _too_large_response(request_id: str):
    from starlette.responses import JSONResponse

    body = ErrorResponse(
        error={
            "code": ErrorCode.FILE_TOO_LARGE,
            "message": ERROR_MESSAGES[ErrorCode.FILE_TOO_LARGE],
            "request_id": request_id,
            "details": {"limit_bytes": REQUEST_BODY_LIMIT_BYTES},
        }
    )
    return JSONResponse(
        status_code=413,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


def _internal_error_response(request_id: str):
    from starlette.responses import JSONResponse

    body = ErrorResponse(
        error={
            "code": ErrorCode.INTERNAL_ERROR,
            "message": ERROR_MESSAGES[ErrorCode.INTERNAL_ERROR],
            "request_id": request_id,
            "details": {},
        }
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


class SecurityHeadersMiddleware:
    """Attach the security baseline to successful and error responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name not in headers:
                        headers.append(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            # Starlette's outer ServerErrorMiddleware is outside user-added
            # middleware.  Render its fallback here so a true unhandled 500
            # receives the same safe envelope and security headers.
            if response_started:
                raise
            await _internal_error_response(_request_id(scope))(scope, receive, send_with_headers)


class RequestSizeLimitMiddleware:
    """Reject oversized requests while preserving streaming semantics."""

    def __init__(self, app: ASGIApp, limit_bytes: int = REQUEST_BODY_LIMIT_BYTES) -> None:
        self.app = app
        self.limit_bytes = limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        try:
            declared = int(content_length) if content_length is not None else None
        except (TypeError, ValueError):
            declared = None
        if declared is not None and declared > self.limit_bytes:
            await _too_large_response(request_id)(scope, receive, send)
            return

        received = 0
        response_started = False

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _RequestTooLarge:
            if response_started:
                # A streaming response has already sent its headers; ASGI
                # cannot replace it with a second 413 response.
                raise
            await _too_large_response(request_id)(scope, receive, send)


class _RequestTooLarge(Exception):
    """Internal control flow for chunked bodies exceeding the hard limit."""


__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "REQUEST_BODY_LIMIT_BYTES",
    "SECURITY_HEADERS",
    "SecurityHeadersMiddleware",
    "RequestSizeLimitMiddleware",
]
