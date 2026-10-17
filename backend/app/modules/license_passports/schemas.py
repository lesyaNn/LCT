from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LicenseVerification(BaseModel):
    status: Literal["confirmed", "invalid", "revoked", "expired"]
    status_label: str
    reason: str
    checked_at: datetime
    university_name: str | None = None
    product_name: str | None = None
    license_number: str | None = None
    contract_number: str | None = None
    signed_at: date | None = None
    expires_at: date | None = None


class LicensePassport(BaseModel):
    license_id: UUID
    university_id: UUID
    passport_number: str
    university_name: str
    product_name: str
    vendor_name: str | None
    license_number: str
    contract_number: str
    contract_signed_at: date
    signed_at: date
    expires_at: date
    status_label: str
    status_reason: str
    generated_at: datetime
    verification_url: str
