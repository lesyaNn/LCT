"""Catalog DTOs: directions, programs, products, vendors (P1-02-02).

List schemas are light (IDs, names, counters filled by services at read
time); Detail schemas embed nested objects; Create/Update carry only
editable fields. ``ProgramShort``/``ProductShort`` defined here are the
canonical versions reused by passports (P1-02-01, P1-02-03).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --------------------------------------------------------------- direction


class DirectionShort(BaseModel):
    id: uuid.UUID
    code: str
    name: str

    model_config = {"from_attributes": True}


class DirectionBase(BaseModel):
    code: str = Field(min_length=1, max_length=64, examples=["it-security"])
    name: str = Field(min_length=1, max_length=512, examples=["Информационная безопасность"])


class DirectionCreate(DirectionBase):
    pass


class DirectionUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=512)


class DirectionList(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    programs_count: int = 0

    model_config = {"from_attributes": True}


class DirectionDetail(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    programs: list[ProgramShort] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----------------------------------------------------------------- program


class ProgramShort(BaseModel):
    id: uuid.UUID
    name: str
    direction_name: str | None = None

    model_config = {"from_attributes": True}


class ProgramBase(BaseModel):
    direction_id: uuid.UUID
    name: str = Field(min_length=1, max_length=512, examples=["Анализ данных"])
    description: str = Field(default="", examples=["Программа по аналитике"])


class ProgramCreate(ProgramBase):
    pass


class ProgramUpdate(BaseModel):
    direction_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None


class ProgramList(BaseModel):
    id: uuid.UUID
    direction_id: uuid.UUID
    direction_name: str | None = None
    name: str
    universities_count: int = 0

    model_config = {"from_attributes": True}


class ProgramDetail(BaseModel):
    id: uuid.UUID
    direction_id: uuid.UUID
    name: str
    description: str = ""
    direction: DirectionShort | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----------------------------------------------------------------- product


class ProductShort(BaseModel):
    id: uuid.UUID
    name: str
    version: str | None = None
    vendor_name: str | None = None

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    vendor_id: uuid.UUID
    program_id: uuid.UUID | None = Field(default=None, description="Программа продукта (иерархия ТЗ: направление <- программа <- продукт).")
    name: str = Field(min_length=1, max_length=512, examples=["РЕД ОС"])
    version: str = Field(default="", max_length=128, examples=["8"])


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    vendor_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=512)
    version: str | None = Field(default=None, max_length=128)


class ProductList(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str | None = None
    name: str
    version: str = ""
    universities_count: int = 0

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    version: str = ""
    vendor: VendorShort | None = None
    licenses_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ vendor


class VendorShort(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class VendorBase(BaseModel):
    name: str = Field(min_length=1, max_length=512, examples=["РЕД СОФТ"])


class VendorContactInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=512)
    email: str = Field(min_length=1, max_length=512)
    phone: str | None = Field(default=None, max_length=64)
    communication_method: str | None = Field(default=None, max_length=256)


class VendorCreate(VendorBase):
    contacts: list[VendorContactInput] = Field(default_factory=list)


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    contacts: list[VendorContactInput] | None = None


class VendorList(BaseModel):
    id: uuid.UUID
    name: str
    products_count: int = 0

    model_config = {"from_attributes": True}


class VendorDetail(BaseModel):
    id: uuid.UUID
    name: str
    products: list[ProductShort] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


__all__ = [
    "DirectionBase",
    "DirectionCreate",
    "DirectionDetail",
    "DirectionList",
    "DirectionShort",
    "DirectionUpdate",
    "ProductBase",
    "ProductCreate",
    "ProductDetail",
    "ProductList",
    "ProductShort",
    "ProductUpdate",
    "ProgramBase",
    "ProgramCreate",
    "ProgramDetail",
    "ProgramList",
    "ProgramShort",
    "ProgramUpdate",
    "VendorBase",
    "VendorCreate",
    "VendorDetail",
    "VendorList",
    "VendorShort",
    "VendorUpdate",
]


# Resolve forward references (DirectionDetail -> ProgramShort,
# ProductDetail -> VendorShort are defined later in this module).
DirectionDetail.model_rebuild()
ProductDetail.model_rebuild()
