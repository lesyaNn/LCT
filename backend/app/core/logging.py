"""Request logging with request_id (see §23 of architecture)."""
import logging
import time
import uuid

from fastapi import Request

logger = logging.getLogger("rtk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def request_log_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
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
