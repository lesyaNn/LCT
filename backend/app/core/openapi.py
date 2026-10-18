"""Reusable documentation for binary responses and the public error envelope."""

import re

from app.core.middleware import RATE_LIMITED_PATHS
from app.schemas.errors import ERROR_MESSAGES, ERROR_STATUS_MAP, ErrorCode


def file_response(description: str, *media_types: str, disposition: str = "attachment") -> dict:
    return {
        "description": description,
        "headers": {"Content-Disposition": {
            "description": f"{disposition} с именем файла",
            "schema": {"type": "string"},
        }},
        "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                    for mime in media_types or ("application/octet-stream", "*/*")},
    }


def document_errors(path: str, method: str, operation: dict) -> None:
    responses = operation.setdefault("responses", {})
    if path.startswith("/api/v1/"):
        defaults = {422: ErrorCode.VALIDATION_ERROR, 500: ErrorCode.INTERNAL_ERROR}
        if operation.get("security"):
            defaults.update({401: ErrorCode.AUTH_REQUIRED, 403: ErrorCode.FORBIDDEN,
                             503: ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE})
        if "{" in path:
            defaults[404] = ErrorCode.NOT_FOUND
        if method in {"post", "put", "patch", "delete"}:
            defaults[409] = ErrorCode.CONFLICT
        if path in RATE_LIMITED_PATHS:
            defaults[429] = ErrorCode.RATE_LIMITED
        content = operation.get("requestBody", {}).get("content", {})
        if "multipart/form-data" in content:
            defaults.update({413: ErrorCode.FILE_TOO_LARGE, 415: ErrorCode.FILE_TYPE_NOT_ALLOWED})
        for status, code in defaults.items():
            responses.setdefault(str(status), {"description": f"{code.value}: {ERROR_MESSAGES[code]}"})

    fallback = {
        400: ErrorCode.HTTP_ERROR, 401: ErrorCode.AUTH_REQUIRED, 403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND, 405: ErrorCode.METHOD_NOT_ALLOWED, 409: ErrorCode.CONFLICT,
        410: ErrorCode.GONE, 413: ErrorCode.FILE_TOO_LARGE, 415: ErrorCode.FILE_TYPE_NOT_ALLOWED,
        422: ErrorCode.VALIDATION_ERROR, 429: ErrorCode.RATE_LIMITED, 500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE, 504: ErrorCode.ASSISTANT_TIMEOUT,
    }
    for status, response in responses.items():
        if not status.isdigit() or int(status) not in fallback:
            continue
        number = int(status)
        # Keep route-specific codes such as REPORT_NOT_READY and existing examples.
        codes = [code for code in ErrorCode if ERROR_STATUS_MAP[code] == number
                 and re.search(r"\b" + re.escape(code.value) + r"\b", response.get("description", ""))]
        media = response.setdefault("content", {}).setdefault("application/json", {})
        media["schema"] = {"$ref": "#/components/schemas/ErrorResponse"}
        examples = media.setdefault("examples", {})
        for code in codes or [fallback[number]]:
            examples.setdefault(code.value, {"summary": code.value, "value": {"error": {
                "code": code.value, "message": ERROR_MESSAGES[code],
                "request_id": "00000000-0000-4000-8000-000000000000", "details": {},
            }}})
