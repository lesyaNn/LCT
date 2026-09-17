from fastapi import HTTPException


class NotFound(HTTPException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(status_code=404, detail=detail)


class Conflict(HTTPException):
    def __init__(self, detail: str = "Conflict"):
        super().__init__(status_code=409, detail=detail)


class BadTransition(HTTPException):
    def __init__(self, detail: str = "Transition not allowed"):
        super().__init__(status_code=422, detail=detail)
