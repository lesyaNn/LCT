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


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def _integrity_conflict(request: Request, exc: IntegrityError):
        _ = (request, exc)  # never leak driver/SQL text into the response
        return JSONResponse(status_code=409, content={"detail": CONFLICT_DETAIL})
