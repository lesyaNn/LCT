"""Program-level training counts from LMS, without learner identities."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ProgramEducationStats(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "program_education_stats"
    __table_args__ = (
        UniqueConstraint("university_id", "program_id", "source",
                         name="uq_program_education_stats_source"),
        Index("ix_program_education_stats_university_id", "university_id"),
        Index("ix_program_education_stats_program_id", "program_id"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id", ondelete="CASCADE"), nullable=False)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("it_programs.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    learners_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
