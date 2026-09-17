from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(256))
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"), nullable=True)
    competencies: Mapped[str] = mapped_column(String(1024), default="")
    next_training_date: Mapped[date | None] = mapped_column(Date, nullable=True)
