"""P1-01-01: catalog + core tables.

universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles.

ON DELETE policy (explicit per spec, see IMPORTANT DECISIONS in README):
* catalog references (direction, vendor) — RESTRICT (default NO ACTION):
  a direction/vendor with children cannot be deleted (P1-11-03).
* licenses/contracts/students/teachers reference to universities/products —
  RESTRICT: deleting a university/product in use is blocked.
* licenses.contract_id, contracts.product_id — SET NULL.
* university_responsibles — CASCADE on both sides (spec: "связка чистится
  CASCADE").
* documents.license_id / contract_id — SET NULL (scan survives business
  entity deletion).
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.interactions import (
        Document,
        Meeting,
        Student,
        UniversityProduct,
        UniversityProgram,
    )
    from app.models.teachers import Teacher, TeacherCertificate


class University(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "universities"
    __table_args__ = (
        Index("ix_universities_name", "name"),
        Index("ix_universities_city", "city"),
    )

    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    city: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)

    # NOTE: there is deliberately NO direct responsible_id column here.
    # The only binding is the M:N university_responsibles table (P1-01-01 AC).
    university_responsibles: Mapped[list["UniversityResponsible"]] = relationship(
        back_populates="university", cascade="all, delete-orphan", lazy="selectin"
    )
    licenses: Mapped[list["License"]] = relationship(back_populates="university")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="university")
    teachers: Mapped[list["Teacher"]] = relationship(back_populates="university")
    students: Mapped[list["Student"]] = relationship(back_populates="university")
    university_programs: Mapped[list["UniversityProgram"]] = relationship(
        back_populates="university", cascade="all, delete-orphan"
    )
    university_products: Mapped[list["UniversityProduct"]] = relationship(
        back_populates="university", cascade="all, delete-orphan"
    )
    meetings: Mapped[list["Meeting"]] = relationship(
        back_populates="university", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="university", cascade="all, delete-orphan"
    )


class ITDirection(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "it_directions"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)

    programs: Mapped[list["ITProgram"]] = relationship(back_populates="direction")


class ITProgram(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "it_programs"
    __table_args__ = (Index("ix_it_programs_direction_id", "direction_id"),)

    direction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_directions.id", name="fk_it_programs_direction_id_it_directions",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    direction: Mapped["ITDirection"] = relationship(back_populates="programs")
    teacher_links: Mapped[list["TeacherCertificate"]] = relationship(
        back_populates="program"
    )


class Vendor(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)

    products: Mapped[list["ITProduct"]] = relationship(back_populates="vendor")


class ITProduct(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "it_products"
    __table_args__ = (
        UniqueConstraint("vendor_id", "name", "version",
                         name="uq_it_products_vendor_name_version"),
        Index("ix_it_products_vendor_id", "vendor_id"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", name="fk_it_products_vendor_id_vendors",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    vendor: Mapped["Vendor"] = relationship(back_populates="products")
    licenses: Mapped[list["License"]] = relationship(back_populates="product")


class Contract(UUIDPKMixin, TimestampMixin, Base):
    """Договоры. Source of truth for business dates/numbers (P1-06-01).

    No direct vendor_id column by design: vendor is resolved via product
    (or via linked licenses for framework contracts with product_id NULL).
    Derived ``status`` (active/expires_soon/expired) is a @property
    (P1-06-02), never a DB column.
    """

    __tablename__ = "contracts"
    __table_args__ = (
        Index("ix_contracts_university_id", "university_id"),
        Index("ix_contracts_expires_at", "expires_at"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", name="fk_contracts_university_id_universities",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    contract_number: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_products.id", name="fk_contracts_product_id_it_products",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    signed_at: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    status_raw: Mapped[str] = mapped_column(String(32), nullable=False, default="signed")
    transfer_status_raw: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    university: Mapped["University"] = relationship(back_populates="contracts")
    product: Mapped["ITProduct | None"] = relationship()
    licenses: Mapped[list["License"]] = relationship(back_populates="contract")

    @property
    def days_to_expiry(self) -> int | None:
        from app.services.license_status import days_to_expiry as _dte

        return _dte(self.expires_at)

    @property
    def derived_status(self) -> str:
        """P1-06-02 contract status logic (delegates to the shared service)."""
        from app.services.license_status import derive_contract_status

        return derive_contract_status(self.status_raw, self.expires_at)


class License(UUIDPKMixin, TimestampMixin, Base):
    """Лицензии. Derived ``status`` is a @property, never a column (P1-06-02)."""

    __tablename__ = "licenses"
    __table_args__ = (
        Index("ix_licenses_university_id", "university_id"),
        Index("ix_licenses_product_id", "product_id"),
        Index("ix_licenses_expires_at", "expires_at"),
        Index("ix_licenses_transfer_status_raw", "transfer_status_raw"),
        Index("ix_licenses_univ_expires", "university_id", "expires_at"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", name="fk_licenses_university_id_universities",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_products.id", name="fk_licenses_product_id_it_products",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contracts.id", name="fk_licenses_contract_id_contracts",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    license_number: Mapped[str] = mapped_column(String(256), nullable=False)
    signed_at: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    transfer_status_raw: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    university: Mapped["University"] = relationship(back_populates="licenses")
    product: Mapped["ITProduct"] = relationship(back_populates="licenses")
    contract: Mapped["Contract | None"] = relationship(back_populates="licenses")

    @property
    def days_to_expiry(self) -> int | None:
        from app.services.license_status import days_to_expiry as _dte

        return _dte(self.expires_at)

    @property
    def derived_status(self) -> str:
        """P1-06-02 license status logic (delegates to the shared service)."""
        from app.services.license_status import derive_license_status

        return derive_license_status(self.expires_at)


class Responsible(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "responsibles"

    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    email: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    role: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    keycloak_sub: Mapped[str | None] = mapped_column(
        String(256), unique=True, nullable=True, default=None
    )

    university_links: Mapped[list["UniversityResponsible"]] = relationship(
        back_populates="responsible", cascade="all, delete-orphan"
    )


class UniversityResponsible(UUIDPKMixin, TimestampMixin, Base):
    """M:N university <-> responsible. The ONLY binding (P1-01-01)."""

    __tablename__ = "university_responsibles"
    __table_args__ = (
        UniqueConstraint("university_id", "responsible_id",
                         name="uq_university_responsibles_uni_resp"),
        Index("ix_university_responsibles_university_id", "university_id"),
        Index("ix_university_responsibles_responsible_id", "responsible_id"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id",
                   name="fk_university_responsibles_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    responsible_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("responsibles.id",
                   name="fk_university_responsibles_responsible_id_responsibles",
                   ondelete="CASCADE"),
        nullable=False,
    )
    role_in_university: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    university: Mapped["University"] = relationship(
        back_populates="university_responsibles"
    )
    responsible: Mapped["Responsible"] = relationship(
        back_populates="university_links"
    )


_ = PG_UUID
