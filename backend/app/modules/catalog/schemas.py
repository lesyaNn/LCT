"""P1-03 CRUD response DTOs + Responsible write DTOs.

Create/Update contracts for universities, directions, programs, products and
vendors are reused from ``app.schemas`` (single source of truth, also used by
passports/import). Response DTOs are flat (id + real columns + timestamps);
Detail variants embed only directly-related objects loaded in the same
statement(s) — never per-item queries. No counters here: list items stay
flat so list endpoints are always exactly 2 SELECTs (COUNT + page).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.catalog import (
    DirectionShort,
    ProductShort,
    ProgramShort,
    VendorShort,
)
from app.schemas.licenses import LicenseShort
from app.services.license_status import days_to_expiry as _days_to_expiry
from app.services.license_status import derive_contract_status as _derive_contract_status
from app.services.license_status import derive_license_status as _derive_license_status

# ------------------------------------------------------------------ shared


class ResponsibleAssign(BaseModel):
    """Optional body for POST /universities/{id}/responsibles/{rid}."""

    role_in_university: str | None = Field(default=None, max_length=64)
    is_primary: bool = False


class UniversityResponsibleRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    responsible_id: uuid.UUID
    role_in_university: str | None = None
    is_primary: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrimaryResponsibleChange(BaseModel):
    responsible_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)


class UniversityProgramAttach(BaseModel):
    program_id: uuid.UUID
    status: str = Field(default="planned", pattern="^(planned|active|launched|archived)$")


class UniversityProgramRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    program_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UniversityProductAttach(BaseModel):
    product_id: uuid.UUID
    status: str = Field(default="planned", pattern="^(planned|active|expired)$")


class UniversityProductRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    product_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --------------------------------------------------------------- university


class ResponsibleShort(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None = None
    role: str = ""
    is_primary: bool = False

    model_config = {"from_attributes": True}


class UniversityRead(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None = None
    created_at: datetime
    updated_at: datetime
    # Populated only when the list is filtered/sorted by health (P1-03-01);
    # None otherwise (scores are computed, never stored).

    model_config = {"from_attributes": True}


class UniversityDetail(UniversityRead):
    # M:N via university_responsibles (the ONLY university<->responsible
    # binding). Loaded with ONE join query, never per-item.
    responsibles: list[ResponsibleShort] = Field(default_factory=list)


# --------------------------------------------------------------- responsible


class ResponsibleCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=512)
    email: str = Field(min_length=1, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    role: str = Field(default="", max_length=256)
    keycloak_sub: str | None = Field(default=None, max_length=256)


class ResponsibleUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=512)
    email: str | None = Field(default=None, min_length=1, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    role: str | None = Field(default=None, max_length=256)
    keycloak_sub: str | None = Field(default=None, max_length=256)


class ResponsibleRead(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None = None
    role: str = ""
    keycloak_sub: str | None = None
    created_at: datetime
    updated_at: datetime
    # Universities of this responsible, for the whole page in ONE extra query
    # (list_responsibles_for_universities), never per item. Empty by default
    # so single-row validates keep working without the link table.
    universities: list[UniversityRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ResponsibleDetail(ResponsibleRead):
    # Universities this responsible is linked to (ONE join query). Same field as
    # in the list response, declared here only to document the source.
    universities: list[UniversityRead] = Field(default_factory=list)


# --------------------------------------------------------------- direction


class DirectionRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DirectionDetail(DirectionRead):
    # Global programs of this direction (ONE query, no N+1).
    programs: list[ProgramShort] = Field(default_factory=list)


# ----------------------------------------------------------------- program


class ProgramRead(BaseModel):
    id: uuid.UUID
    direction_id: uuid.UUID
    direction_name: str | None = None
    name: str
    description: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProgramDetail(ProgramRead):
    # Many-to-one parent, joined in the same statement.
    direction: DirectionShort | None = None


# ----------------------------------------------------------------- product


class ProductRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str | None = None
    program_id: uuid.UUID | None = None
    program_name: str | None = None
    name: str
    version: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductDetail(ProductRead):
    # Many-to-one parents, joined in the same statement.
    vendor: VendorShort | None = None
    contacts: list["VendorContactRead"] = Field(default_factory=list)


# ------------------------------------------------------------------ vendor


class VendorRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VendorContactRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    full_name: str
    phone: str | None = None
    email: str
    communication_method: str | None = None

    model_config = {"from_attributes": True}


class VendorDetail(VendorRead):
    # Products of this vendor (ONE query, no N+1).
    products: list[ProductShort] = Field(default_factory=list)
    contacts: list[VendorContactRead] = Field(default_factory=list)


# ---------------------------------------------------- contracts & licenses
#
# Write DTOs. ``status``/``days_to_expiry`` are derived on the fly
# (app.services.license_status) and are therefore never accepted as input.


class ContractCreate(BaseModel):
    university_id: uuid.UUID
    contract_number: str = Field(min_length=1, max_length=256)
    product_id: uuid.UUID | None = None
    signed_at: date
    expires_at: date | None = None
    status_raw: str = Field(default="signed", pattern="^(draft|signed|terminated)$")
    transfer_status_raw: str = Field(
        default="pending", pattern="^(pending|transferred|accepted|rejected)$"
    )
    comment: str | None = None

    model_config = {"from_attributes": True}


class ContractUpdate(BaseModel):
    university_id: uuid.UUID | None = None
    contract_number: str | None = Field(default=None, min_length=1, max_length=256)
    product_id: uuid.UUID | None = None
    signed_at: date | None = None
    expires_at: date | None = None
    status_raw: str | None = Field(default=None, pattern="^(draft|signed|terminated)$")
    transfer_status_raw: str | None = Field(
        default=None, pattern="^(pending|transferred|accepted|rejected)$"
    )
    comment: str | None = None

    model_config = {"from_attributes": True}


class ContractRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    contract_number: str
    product_id: uuid.UUID | None = None
    signed_at: date
    expires_at: date | None = None
    status_raw: str
    transfer_status_raw: str
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    # Resolved labels for the list/detail views: the tables keep FKs only, and
    # per-row lookups would be N+1.
    university_name: str = ""
    product_name: str | None = None
    vendor_name: str | None = None
    license_count: int = 0

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> str:
        return _derive_contract_status(self.status_raw, self.expires_at)

    @computed_field  # type: ignore[misc]
    @property
    def days_to_expiry(self) -> int | None:
        return _days_to_expiry(self.expires_at)


class ContractDetail(ContractRead):
    # Licenses issued under this contract (ONE query, no N+1).
    licenses: list[LicenseShort] = Field(default_factory=list)


class LicenseCreate(BaseModel):
    university_id: uuid.UUID
    product_id: uuid.UUID
    license_number: str = Field(min_length=1, max_length=256)
    contract_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    direction_id: uuid.UUID | None = None
    signed_at: date
    expires_at: date
    transfer_status_raw: str = Field(
        default="pending", pattern="^(pending|transferred|accepted|rejected)$"
    )
    comment: str | None = None

    model_config = {"from_attributes": True}


class LicenseUpdate(BaseModel):
    university_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    license_number: str | None = Field(default=None, min_length=1, max_length=256)
    contract_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    direction_id: uuid.UUID | None = None
    signed_at: date | None = None
    expires_at: date | None = None
    transfer_status_raw: str | None = Field(
        default=None, pattern="^(pending|transferred|accepted|rejected)$"
    )
    comment: str | None = None

    model_config = {"from_attributes": True}


class LicenseRead(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    product_id: uuid.UUID
    license_number: str
    contract_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    direction_id: uuid.UUID | None = None
    signed_at: date
    expires_at: date
    transfer_status_raw: str
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    university_name: str = ""
    product_name: str = ""
    vendor_name: str | None = None
    contract_number: str | None = None
    program_name: str | None = None
    direction_name: str | None = None

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> str:
        return _derive_license_status(self.expires_at)

    @computed_field  # type: ignore[misc]
    @property
    def days_to_expiry(self) -> int | None:
        return _days_to_expiry(self.expires_at)


__all__ = [
    "ContractCreate",
    "ContractDetail",
    "ContractRead",
    "ContractUpdate",
    "DirectionDetail",
    "DirectionRead",
    "LicenseCreate",
    "LicenseRead",
    "LicenseUpdate",
    "ProductDetail",
    "ProductRead",
    "ProgramDetail",
    "ProgramRead",
    "ResponsibleAssign",
    "ResponsibleCreate",
    "ResponsibleDetail",
    "ResponsibleRead",
    "ResponsibleShort",
    "ResponsibleUpdate",
    "UniversityDetail",
    "UniversityRead",
    "UniversityResponsibleRead",
    "VendorDetail",
    "VendorRead",
]
