"""Shared status/type enums for P1 (P1-02-04 subset needed by the DB layer).

Stored in the DB as plain ``String`` columns with CHECK constraints (see the
Alembic migration) — no native Postgres ENUM types, so ``downgrade base`` is
clean and SQLite stays compatible for unit tests. Validation / OpenAPI enums
live here in one place and are reused by services and (later) Pydantic DTOs.
"""

import enum


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    TRANSFERRED = "transferred"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ContractStatusRaw(str, enum.Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    TERMINATED = "terminated"


class LicenseDerivedStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRES_SOON = "expires_soon"
    EXPIRED = "expired"


class ContractDerivedStatus(str, enum.Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    ACTIVE = "active"
    EXPIRES_SOON = "expires_soon"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class MeetingType(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    PHONE = "phone"
    EMAIL = "email"


class DocumentType(str, enum.Enum):
    CONTRACT = "contract"
    LICENSE = "license"
    ACT = "act"
    PROTOCOL = "protocol"
    OTHER = "other"


class DocumentStatusRaw(str, enum.Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    ARCHIVED = "archived"


class StudentStatus(str, enum.Enum):
    ACTIVE = "active"
    GRADUATED = "graduated"
    EXPELLED = "expelled"
    ACADEMIC_LEAVE = "academic_leave"


class UniversityProgramStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    LAUNCHED = "launched"
    ARCHIVED = "archived"


class UniversityProductStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    EXPIRED = "expired"


class TeacherReadiness(str, enum.Enum):
    READY = "ready"
    ATTENTION = "attention"
    EXPIRED = "expired"


#: Days before ``expires_at`` when a license/contract/certificate counts as
#: "expiring soon" (P1-06-02, P1-05-03).
EXPIRY_WARNING_DAYS = 30
