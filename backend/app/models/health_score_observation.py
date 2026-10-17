"""Stored results of the operational university Health Score calculation."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, desc
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealthScoreObservation(Base):
    __tablename__ = "health_score_observations"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        Index("ix_health_score_observations_univ_calculated", "university_id", desc("calculated_at")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=True), ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
