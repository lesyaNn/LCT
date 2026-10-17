from typing import Literal

from pydantic import BaseModel


class Operation(BaseModel):
    operation_id: str
    method: str
    path: str
    summary: str
    tags: list[str]
    required_permissions: list[str]
    allowed_roles: list[str]
    role_allowed: bool
    deprecated: bool


class Authentication(BaseModel):
    type: Literal["bearer"] = "bearer"
    issuer: str
    token_url: str
    audience: str
    service_account_setup_required: bool = True


class Limits(BaseModel):
    heavy_requests_per_minute: int
    heavy_paths: list[str]
    assistant_requests_per_minute: int
    assistant_timeout_seconds: float
    max_upload_mb: int


class ApiError(BaseModel):
    code: str
    status: int
    message: str


class ServiceApiCatalog(BaseModel):
    version: str
    base_path: str
    documentation_path: str
    openapi_path: str
    authentication: Authentication
    role: str
    permissions: list[str]
    operation_count: int
    operations: list[Operation]
    limits: Limits
    errors: list[ApiError]
