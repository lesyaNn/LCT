"""Request logging with request_id (see §23 of architecture)."""
import logging
import re
import time
import traceback
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import Request

logger = logging.getLogger("rtk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|proxy-authorization|cookie|set-cookie|password|passwd|"
    r"secret|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|api[_-]?key|jwt)"
    r"(\s*[=:]\s*|\s+)([^,\s]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_DATABASE_URL = re.compile(r"(?i)\b(postgresql|postgres|redis)://[^\s/@:]+:[^\s/@]+@")
_SENSITIVE_KEY = re.compile(
    r"(?i)authorization|cookie|password|passwd|secret|token|api[_-]?key|jwt"
)
_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def _redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return _DATABASE_URL.sub(lambda match: f"{match.group(1)}://[REDACTED]@", value)


def _redact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key))
            else _redact_value(item, depth=depth + 1)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, str):
        return _redact_text(value)
    return value


class SensitiveFilter(logging.Filter):
    """Redact credentials and bearer tokens from every configured log path."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            for key in list(record.__dict__):
                if key in _STANDARD_RECORD_FIELDS:
                    continue
                record.__dict__[key] = (
                    "[REDACTED]" if _SENSITIVE_KEY.search(key)
                    else _redact_value(record.__dict__[key])
                )
            # Preserve the record shape: third-party formatters (notably
            # uvicorn's AccessFormatter) unpack ``record.args`` positionally,
            # so pre-rendering msg + clearing args breaks them with ValueError
            # on every request. Redact in place instead.
            if isinstance(record.msg, str):
                record.msg = _redact_text(record.msg)
            else:
                record.msg = _redact_value(record.msg)
            args = record.args
            if isinstance(args, tuple):
                record.args = tuple(_redact_value(arg) for arg in args)
            elif isinstance(args, Mapping):
                record.args = {
                    str(key): _redact_value(item) for key, item in args.items()
                }
            if record.exc_info:
                # Formatter.format appends exc_text verbatim, so a redacted
                # snapshot keeps tracebacks safe without touching args.
                record.exc_text = _redact_text(
                    "".join(traceback.format_exception(*record.exc_info))
                )
                record.exc_info = None
        except Exception:
            # Logging must never break a request because a third-party object
            # cannot be formatted or sanitized.
            record.msg = "[log message redacted]"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


_sensitive_filter = SensitiveFilter()


def install_sensitive_filter() -> None:
    """Install redaction on current logger handlers, including Uvicorn's."""
    root = logging.getLogger()
    named = [
        candidate
        for candidate in logging.Logger.manager.loggerDict.values()
        if isinstance(candidate, logging.Logger)
    ]
    for current in (root, logger, *named):
        if _sensitive_filter not in current.filters:
            current.addFilter(_sensitive_filter)
        for handler in current.handlers:
            if _sensitive_filter not in handler.filters:
                handler.addFilter(_sensitive_filter)


install_sensitive_filter()


async def request_log_middleware(request: Request, call_next):
    # Uvicorn may replace handlers after importing the application.
    install_sensitive_filter()
    supplied_id = request.headers.get("X-Request-ID")
    try:
        request_id = str(uuid.UUID(supplied_id)) if supplied_id else str(uuid.uuid4())
    except ValueError:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    user = getattr(request.state, "user_id", "-")
    logger.info(
        "request_id=%s user_id=%s %s %s %s %sms",
        request_id, user, request.method, request.url.path,
        response.status_code, duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response
