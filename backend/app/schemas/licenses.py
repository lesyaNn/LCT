"""License/contract short DTOs with derived status (P1-06-02).

``status`` and ``days_to_expiry`` are ``computed_field``s — derived on the
fly at serialization time, never stored, never accepted as input::

    LicenseShort.model_validate(license_orm).model_dump()
    # {'id': ..., 'status': 'expires_soon', 'days_to_expiry': 5, ...}

The date math lives in ``app.services.license_status`` (shared with the ORM
``@property``s and P2 Health Score); these schemas only wrap it into the
API enum values.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import ContractStatus, LicenseStatus
from app.services.license_status import (
    days_to_expiry as _days_to_expiry,
)
from app.services.license_status import (
    derive_contract_status as _derive_contract_status,
)
from app.services.license_status import (
    derive_license_status as _derive_license_status,
)


class LicenseShort(BaseModel):
    """Passport/aggregate license row with derived status."""

    id: uuid.UUID
    license_number: str
    product_name: str | None = None
    expires_at: date | None = None

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> LicenseStatus:
        return LicenseStatus(_derive_license_status(self.expires_at))

    @computed_field  # type: ignore[misc]
    @property
    def days_to_expiry(self) -> int | None:
        return _days_to_expiry(self.expires_at)


class ContractShort(BaseModel):
    """Passport/aggregate contract row with derived status.

    ``status_raw`` is the stored value (``draft``/``signed``/``terminated``);
    ``status`` is the API-facing derived value.
    """

    id: uuid.UUID
    contract_number: str
    status_raw: str = Field(default="signed", exclude=True)
    expires_at: date | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> ContractStatus:
        return ContractStatus(_derive_contract_status(self.status_raw, self.expires_at))

    @computed_field  # type: ignore[misc]
    @property
    def days_to_expiry(self) -> int | None:
        return _days_to_expiry(self.expires_at)


__all__ = [
    "ContractShort",
    "LicenseShort",
]
