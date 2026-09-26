"""P1-01-03 + P1-07-01: links, meetings, documents, notes.

* meetings.participants — JSONB (JSON on SQLite) array of objects.
* documents — file registry only, NOT the source of business dates/numbers
  (P1-06-01): signed_at/expires_at here are display copies; licenses/contracts
  win on conflict. CHECK: a file links to at most one business entity.
* meeting_documents — M:N meeting <-> document (P1-07-01), links only.
* interaction_notes — business history, NOT audit log.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.catalog import Contract, ITProgram, License, Responsible, University


class UniversityProgram(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "university_programs"
    __table_args__ = (
        UniqueConstraint("university_id", "program_id",
                         name="uq_university_programs_uni_prog"),
        Index("ix_univ_programs_university_id", "university_id"),
        Index("ix_univ_programs_program_id", "program_id"),
        Index("ix_univ_programs_status", "status"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id",
                   name="fk_university_programs_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id",
                   name="fk_university_programs_program_id_it_programs",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("responsibles.id",
                   name="fk_university_programs_responsible_id_responsibles",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    university: Mapped["University"] = relationship(
        back_populates="university_programs"
    )
    program: Mapped["ITProgram"] = relationship()
    responsible: Mapped["Responsible | None"] = relationship()


class UniversityProduct(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "university_products"
    __table_args__ = (
        UniqueConstraint("university_id", "product_id",
                         name="uq_university_products_uni_prod"),
        Index("ix_univ_products_university_id", "university_id"),
        Index("ix_univ_products_product_id", "product_id"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id",
                   name="fk_university_products_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_products.id",
                   name="fk_university_products_product_id_it_products",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    license_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("licenses.id", name="fk_university_products_license_id_licenses",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")

    university: Mapped["University"] = relationship(
        back_populates="university_products"
    )
    license: Mapped["License | None"] = relationship()


class Meeting(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "meetings"
    __table_args__ = (
        Index("ix_meetings_university_id", "university_id"),
        Index("ix_meetings_meeting_at", "meeting_at"),
        Index("ix_meetings_univ_meeting_at", "university_id", "meeting_at"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", name="fk_meetings_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    meeting_type: Mapped[str] = mapped_column(String(32), nullable=False, default="online")
    subject: Mapped[str] = mapped_column(String(1024), nullable=False)
    participants: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False, default=list
    )
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    next_action_due: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    meeting_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    university: Mapped["University"] = relationship(back_populates="meetings")
    document_links: Mapped[list["MeetingDocument"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class Document(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "NOT (license_id IS NOT NULL AND contract_id IS NOT NULL)",
            name="ck_documents_single_link",
        ),
        Index("ix_documents_university_id", "university_id"),
        Index("ix_documents_univ_created", "university_id", "created_at"),
        Index("ix_documents_status_raw", "status_raw"),
        Index("ix_documents_license_id", "license_id"),
        Index("ix_documents_contract_id", "contract_id"),
        Index("ix_documents_expires_at", "expires_at"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", name="fk_documents_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    license_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("licenses.id", name="fk_documents_license_id_licenses",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contracts.id", name="fk_documents_contract_id_contracts",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # Display copies — source of truth lives in licenses/contracts (P1-06-01).
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    status_raw: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    uploaded_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    university: Mapped["University"] = relationship(back_populates="documents")
    license: Mapped["License | None"] = relationship()
    contract: Mapped["Contract | None"] = relationship()


class InteractionNote(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "interaction_notes"
    __table_args__ = (
        Index("ix_interaction_notes_university_id", "university_id"),
        Index("ix_interaction_notes_created_at", "created_at"),
        Index("ix_interaction_notes_univ_created", "university_id", "created_at"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id",
                   name="fk_interaction_notes_university_id_universities",
                   ondelete="CASCADE"),
        nullable=False,
    )
    author_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MeetingDocument(UUIDPKMixin, TimestampMixin, Base):
    """M:N meeting <-> document. The ONLY attachment link (P1-07-01)."""

    __tablename__ = "meeting_documents"
    __table_args__ = (
        UniqueConstraint("meeting_id", "document_id",
                         name="uq_meeting_documents_meeting_document"),
        Index("ix_meeting_documents_meeting_id", "meeting_id"),
        Index("ix_meeting_documents_document_id", "document_id"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", name="fk_meeting_documents_meeting_id_meetings",
                   ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", name="fk_meeting_documents_document_id_documents",
                   ondelete="CASCADE"),
        nullable=False,
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="document_links")
