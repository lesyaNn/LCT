"""Canonical public API error vocabulary (P5-06 unified errors).

This module is the single source of truth for the public error contract.  The
HTTP mapping and user-facing messages deliberately live next to the enum so a
new code cannot be added without making its response deterministic.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    FORBIDDEN = "FORBIDDEN"
    ADMIN_REQUIRED = "ADMIN_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    GONE = "GONE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    WORKFLOW_INVALID_TRANSITION = "WORKFLOW_INVALID_TRANSITION"
    WORKFLOW_INSTANCE_NOT_ACTIVE = "WORKFLOW_INSTANCE_NOT_ACTIVE"
    STAGE_ALREADY_COMPLETED = "STAGE_ALREADY_COMPLETED"
    FILE_TYPE_NOT_ALLOWED = "FILE_TYPE_NOT_ALLOWED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    IMPORT_FAILED = "IMPORT_FAILED"
    IMPORT_VALIDATION_FAILED = "IMPORT_VALIDATION_FAILED"
    REPORT_FAILED = "REPORT_FAILED"
    REPORT_NOT_READY = "REPORT_NOT_READY"
    EXTERNAL_SOURCE_UNAVAILABLE = "EXTERNAL_SOURCE_UNAVAILABLE"
    EXTERNAL_SYNC_FAILED = "EXTERNAL_SYNC_FAILED"
    ASSISTANT_DISABLED = "ASSISTANT_DISABLED"
    ASSISTANT_UNAVAILABLE = "ASSISTANT_UNAVAILABLE"
    ASSISTANT_TIMEOUT = "ASSISTANT_TIMEOUT"
    ASSISTANT_BUSY = "ASSISTANT_BUSY"
    ASSISTANT_KNOWLEDGE_UNAVAILABLE = "ASSISTANT_KNOWLEDGE_UNAVAILABLE"
    ASSISTANT_INVALID_RESPONSE = "ASSISTANT_INVALID_RESPONSE"
    ASSISTANT_STORAGE_UNAVAILABLE = "ASSISTANT_STORAGE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ADMIN_REQUIRED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.GONE: 410,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.WORKFLOW_INVALID_TRANSITION: 400,
    ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE: 409,
    ErrorCode.STAGE_ALREADY_COMPLETED: 409,
    ErrorCode.FILE_TYPE_NOT_ALLOWED: 400,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.FILE_NOT_FOUND: 404,
    ErrorCode.IMPORT_FAILED: 500,
    ErrorCode.IMPORT_VALIDATION_FAILED: 400,
    ErrorCode.REPORT_FAILED: 500,
    ErrorCode.REPORT_NOT_READY: 400,
    ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE: 503,
    ErrorCode.EXTERNAL_SYNC_FAILED: 500,
    ErrorCode.ASSISTANT_DISABLED: 503,
    ErrorCode.ASSISTANT_UNAVAILABLE: 503,
    ErrorCode.ASSISTANT_TIMEOUT: 504,
    ErrorCode.ASSISTANT_BUSY: 429,
    ErrorCode.ASSISTANT_KNOWLEDGE_UNAVAILABLE: 503,
    ErrorCode.ASSISTANT_INVALID_RESPONSE: 503,
    ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE: 503,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.HTTP_ERROR: 500,
    ErrorCode.INTERNAL_ERROR: 500,
}

# Backwards compatible name used by the frozen P5-01 tests.
ERROR_HTTP_STATUS = ERROR_STATUS_MAP

ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.AUTH_REQUIRED: "Требуется авторизация. Пожалуйста, войдите в систему.",
    ErrorCode.TOKEN_EXPIRED: "Сессия истекла. Пожалуйста, войдите снова.",
    ErrorCode.TOKEN_INVALID: "Недействительный токен. Пожалуйста, войдите снова.",
    ErrorCode.FORBIDDEN: "У вас нет прав для выполнения этого действия.",
    ErrorCode.ADMIN_REQUIRED: "Требуются права администратора.",
    ErrorCode.NOT_FOUND: "Запрашиваемый ресурс не найден.",
    ErrorCode.CONFLICT: "Конфликт данных.",
    ErrorCode.GONE: "Ресурс больше недоступен.",
    ErrorCode.VALIDATION_ERROR: "Проверьте правильность заполнения полей.",
    ErrorCode.WORKFLOW_INVALID_TRANSITION: "Нельзя перейти на этот этап.",
    ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE: "Workflow неактивен. Переход невозможен.",
    ErrorCode.STAGE_ALREADY_COMPLETED: "Этап уже завершён.",
    ErrorCode.FILE_TYPE_NOT_ALLOWED: "Тип файла не поддерживается.",
    ErrorCode.FILE_TOO_LARGE: "Файл слишком большой. Максимум 50 МБ.",
    ErrorCode.FILE_NOT_FOUND: "Файл не найден.",
    ErrorCode.IMPORT_FAILED: "Не удалось выполнить импорт.",
    ErrorCode.IMPORT_VALIDATION_FAILED: "Импортируемые данные не прошли проверку.",
    ErrorCode.REPORT_FAILED: "Не удалось сгенерировать отчёт. Попробуйте позже.",
    ErrorCode.REPORT_NOT_READY: "Отчёт ещё формируется. Подождите немного.",
    ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE: "Внешний источник данных временно недоступен.",
    ErrorCode.EXTERNAL_SYNC_FAILED: "Ошибка синхронизации с внешним источником.",
    ErrorCode.ASSISTANT_DISABLED: "Помощник пока не включён.",
    ErrorCode.ASSISTANT_UNAVAILABLE: "Модель помощника временно недоступна.",
    ErrorCode.ASSISTANT_TIMEOUT: "Помощник не успел ответить. Попробуйте позже.",
    ErrorCode.ASSISTANT_BUSY: "Помощник занят. Попробуйте через несколько секунд.",
    ErrorCode.ASSISTANT_KNOWLEDGE_UNAVAILABLE: "Документация помощника недоступна.",
    ErrorCode.ASSISTANT_INVALID_RESPONSE: "Помощник не смог подготовить проверяемый ответ.",
    ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE: "История помощника временно недоступна.",
    ErrorCode.RATE_LIMITED: "Слишком много запросов. Попробуйте позже.",
    ErrorCode.METHOD_NOT_ALLOWED: "Метод запроса не поддерживается для этого ресурса.",
    ErrorCode.HTTP_ERROR: "Не удалось обработать запрос.",
    ErrorCode.INTERNAL_ERROR: "Внутренняя ошибка сервера.",
}

if set(ERROR_STATUS_MAP) != set(ErrorCode) or set(ERROR_MESSAGES) != set(ErrorCode):
    raise RuntimeError("ErrorCode registry is incomplete")


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: UUID
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Проверьте правильность заполнения полей.",
                        "request_id": "00000000-0000-4000-8000-000000000000",
                        "details": {"field_errors": []},
                    }
                }
            ]
        }
    }

    error: ErrorDetail


class ConflictDetails(BaseModel):
    """Safe machine-readable location of a uniqueness/reference conflict."""

    field: str
