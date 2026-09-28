"""P1-01-02: teachers, qualifications, certificates, teacher_programs.

* qualifications/certificates — CASCADE on teacher delete (spec).
* teacher_programs — M:N, Unique(teacher_id, program_id); teacher side
  CASCADE, program side RESTRICT (catalog protection: a program in use by a
  teacher cannot be deleted — P1-11-03). This is the documented deviation
  from the literal "CASCADE" on both sides in P1-01-02.
* No JSON/ARRAY program lists — strictly relational (P1 task §6).
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.catalog import ITProgram, University


class Teacher(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teachers"
    __table_args__ = (Index("ix_teachers_university_id", "university_id"),)

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", name="fk_teachers_university_id_universities",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    email: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    position: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    university: Mapped["University"] = relationship(back_populates="teachers")
    qualifications: Mapped[list["TeacherQualification"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    certificates: Mapped[list["TeacherCertificate"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    teacher_programs: Mapped[list["TeacherProgram"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )


class TeacherQualification(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teacher_qualifications"
    __table_args__ = (
        Index("ix_teacher_qualifications_teacher_id", "teacher_id"),
        # P1-10-02: passport readiness scalars filter
        # ``teacher_id = ? AND expires_at < / BETWEEN ...`` per teacher
        # (loops scale with teachers x programs); the composite turns the
        # per-loop Bitmap Heap Scan + Filter into an Index (Only) Scan.
        Index("ix_teacher_qualifications_teacher_expires", "teacher_id", "expires_at"),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teachers.id",
                   name="fk_teacher_qualifications_teacher_id_teachers",
                   ondelete="CASCADE"),
        nullable=False,
    )
    qualification_name: Mapped[str] = mapped_column(String(512), nullable=False)
    obtained_at: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    document_ref: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None
    )

    teacher: Mapped["Teacher"] = relationship(back_populates="qualifications")


class TeacherCertificate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teacher_certificates"
    __table_args__ = (
        Index("ix_teacher_certificates_teacher_id", "teacher_id"),
        Index("ix_teacher_certificates_expires_at", "expires_at"),
        Index("ix_teacher_certificates_mandatory", "is_mandatory", "expires_at"),
        # P1-10-02: same rationale as qualifications above; the mandatory
        # flag stays a Filter (3 rows/teacher), the range becomes Index Cond.
        Index("ix_teacher_certificates_teacher_expires", "teacher_id", "expires_at"),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teachers.id",
                   name="fk_teacher_certificates_teacher_id_teachers",
                   ondelete="CASCADE"),
        nullable=False,
    )
    certificate_name: Mapped[str] = mapped_column(String(512), nullable=False)
    issued_by: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_programs.id",
                   name="fk_teacher_certificates_program_id_it_programs",
                   ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    document_ref: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None
    )

    teacher: Mapped["Teacher"] = relationship(back_populates="certificates")
    program: Mapped["ITProgram | None"] = relationship(back_populates="teacher_links")


class TeacherProgram(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teacher_programs"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "program_id",
            name="uq_teacher_programs_teacher_program",
        ),
        Index("ix_teacher_programs_teacher_id", "teacher_id"),
        Index("ix_teacher_programs_program_id", "program_id"),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teachers.id", name="fk_teacher_programs_teacher_id_teachers",
                   ondelete="CASCADE"),
        nullable=False,
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id", name="fk_teacher_programs_program_id_it_programs",
                   ondelete="RESTRICT"),
        nullable=False,
    )
    can_teach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_at: Mapped[date] = mapped_column(Date, nullable=False)

    teacher: Mapped["Teacher"] = relationship(back_populates="teacher_programs")
