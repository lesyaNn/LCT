from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealthScoreHistory(Base):
    __tablename__ = "health_score_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    score: Mapped[int] = mapped_column(Integer)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details_json: Mapped[str] = mapped_column(Text, default="{}")
