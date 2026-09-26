"""Shared Pydantic DTOs for the whole backend (P1-02-04).

Single source of truth for API enums and reusable schemas::

    from app.schemas.common import LicenseStatus, PaginatedResponse, UniversityFilter

Layering note: the DB layer (``app.models.enums``) stores statuses as plain
``String`` columns and keeps its own small raw-value enums so Alembic
migrations stay stable. The enums below are the *API contract* (frozen after
contract-freeze, Day 1) — services map DB raw values onto these when
serializing. Canonical API names come from ``hackathon_rostelecom_tasks``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.errors import ErrorDetail, ErrorResponse

#: Days before ``expires_at`` when a license/contract/certificate counts as
#: "expiring soon". Mirrors ``app.models.enums.EXPIRY_WARNING_DAYS``.
EXPIRY_WARNING_DAYS = 30


# ------------------------------------------------------------- entity enums


class EntityStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class LicenseStatus(str, enum.Enum):
    """Derived license status (P1-06-02) — computed, never stored."""

    ACTIVE = "active"
    EXPIRES_SOON = "expires_soon"
    EXPIRED = "expired"


class ContractStatus(str, enum.Enum):
    """Contract status: stored raw values are draft/signed/terminated,
    active/expired are derived from dates (P1-06-01/P1-06-02)."""

    DRAFT = "draft"
    SIGNED = "signed"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class TransferStatus(str, enum.Enum):
    """License/contract handover status (P1-06-01)."""

    PENDING = "pending"
    TRANSFERRED = "transferred"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class DocumentType(str, enum.Enum):
    CONTRACT = "contract"
    LICENSE = "license"
    ACT = "act"
    PROTOCOL = "protocol"
    OTHER = "other"


class MeetingType(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    PHONE = "phone"
    EMAIL = "email"


class UniversityProgramStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    LAUNCHED = "launched"
    ARCHIVED = "archived"


class UniversityProductStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    EXPIRED = "expired"


# ----------------------------------------------------------- workflow enums


class WorkflowStageStatus(str, enum.Enum):
    PENDING = "pending"
    CURRENT = "current"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    OVERDUE = "overdue"


class TransitionAction(str, enum.Enum):
    NEXT = "next"
    PREVIOUS = "previous"
    SKIP = "skip"
    REOPEN = "reopen"


# ------------------------------------------------------------------ misc


class UserRole(str, enum.Enum):
    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"


class ReportFormat(str, enum.Enum):
    XLSX = "xlsx"
    PDF = "pdf"
    JSON = "json"


# ------------------------------------------------------- reusable schemas


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, examples=[1])
    page_size: int = Field(default=20, ge=1, le=100, examples=[20])


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    page: int = Field(examples=[1])
    page_size: int = Field(examples=[20])
    total: int = Field(examples=[128])

    model_config = {"from_attributes": True}


class FilterBase(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


class UniversityFilter(FilterBase):
    university_ids: list[uuid.UUID] | None = None
    direction_ids: list[uuid.UUID] | None = None
    program_ids: list[uuid.UUID] | None = None
    product_ids: list[uuid.UUID] | None = None
    responsible_ids: list[uuid.UUID] | None = None
    workflow_statuses: list[WorkflowStageStatus] | None = None


__all__ = [
    "EXPIRY_WARNING_DAYS",
    "ContractStatus",
    "DocumentStatus",
    "DocumentType",
    "EntityStatus",
    "ErrorDetail",
    "ErrorResponse",
    "FilterBase",
    "LicenseStatus",
    "MeetingType",
    "PaginatedResponse",
    "PaginationParams",
    "ReportFormat",
    "TransferStatus",
    "TransitionAction",
    "UniversityFilter",
    "UniversityProductStatus",
    "UniversityProgramStatus",
    "UserRole",
    "WorkflowStageStatus",
]
