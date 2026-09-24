"""Request logging with request_id (see §23 of architecture)."""
import logging
import re
import time
import traceback
import uuid

from fastapi import Request

logger = logging.getLogger("rtk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|proxy-authorization|cookie|set-cookie|password|passwd|"
    r"secret|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|api[_-]?key|jwt)"
    r"(\s*[=:]\s*|\s+)([^,\s]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")


class SensitiveFilter(logging.Filter):
    """Redact credentials and bearer tokens from every configured log path."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            if record.exc_info:
                rendered += "\n" + "".join(traceback.format_exception(*record.exc_info))
                record.exc_info = None
                record.exc_text = None
            rendered = _BEARER.sub("Bearer [REDACTED]", rendered)
            rendered = _SENSITIVE_VALUE.sub(lambda m: f"{m.group(1)}=[REDACTED]", rendered)
            record.msg = rendered
            record.args = ()
        except Exception:
            # Logging must never break a request because a third-party object
            # cannot be formatted or sanitized.
            record.msg = "[log message redacted]"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


_sensitive_filter = SensitiveFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_sensitive_filter)
logger.addFilter(_sensitive_filter)


async def request_log_middleware(request: Request, call_next):
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
