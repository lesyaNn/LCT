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
    """Invalid workflow move. M3: the public code is an EXPLICIT argument —
    never derived by substring-matching the human message (a reworded
    message used to silently change the HTTP contract)."""

    def __init__(
        self,
        detail: str = "Transition not allowed",
        code: ErrorCode = ErrorCode.WORKFLOW_INVALID_TRANSITION,
    ):
        super().__init__(code, details={}, message=detail)
