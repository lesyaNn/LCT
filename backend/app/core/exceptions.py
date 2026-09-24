"""Compatibility constructors for domain errors."""

from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode


class NotFound(BusinessException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(ErrorCode.NOT_FOUND, details={}, message=detail)


class Conflict(BusinessException):
    def __init__(self, detail: str = "Conflict"):
        super().__init__(ErrorCode.CONFLICT, details={}, message=detail)


class BadTransition(BusinessException):
    def __init__(self, detail: str = "Transition not allowed"):
        text = detail.lower()
        code = (ErrorCode.WORKFLOW_INSTANCE_NOT_ACTIVE if "active" in text
                else ErrorCode.STAGE_ALREADY_COMPLETED if "already" in text or "closed" in text
                else ErrorCode.WORKFLOW_INVALID_TRANSITION)
        super().__init__(code, details={}, message=detail)
