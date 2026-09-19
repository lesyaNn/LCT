"""Central DB error mapping (P1-11-01 minimal fix).

Any :class:`sqlalchemy.exc.IntegrityError` escaping the service/repository
layers becomes HTTP 409 with a sanitized body instead of a raw 500 with
driver/SQL internals. Per-task rule: one central handler, no per-router
``try/except IntegrityError``.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

CONFLICT_DETAIL = "Conflict: duplicate or referenced resource"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def _integrity_conflict(request: Request, exc: IntegrityError):
        _ = (request, exc)  # never leak driver/SQL text into the response
        return JSONResponse(status_code=409, content={"detail": CONFLICT_DETAIL})

    @app.exception_handler(Exception)
    async def _unhandled_envelope(request: Request, exc: Exception):
        # NOTE: HTTPException / RequestValidationError keep their stock
        # FastAPI shapes (pinned by contract tests — see
        # test_validation_422_contract_unchanged); only truly unhandled
        # 500s get the ErrorResponse envelope with request_id.
        # (Re-raising here would bypass response rendering, so the stock
        # shapes are reproduced explicitly instead.)
        import logging

        from fastapi.encoders import jsonable_encoder
        from fastapi.exceptions import HTTPException, RequestValidationError

        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": jsonable_encoder(exc.detail)},
                headers=dict(exc.headers or {}),
            )
        if isinstance(exc, RequestValidationError):
            return JSONResponse(
                status_code=422,
                content={"detail": jsonable_encoder(exc.errors())},
            )
        logging.getLogger("rtk").exception(
            "unhandled error request_id=%s %s %s",
            _request_id(request), request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error",
                    "request_id": _request_id(request),
                }
            },
        )
