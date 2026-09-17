from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512))
    direction_id: Mapped[str] = mapped_column(String(128), default="")
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="draft")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_id: Mapped[int | None] = mapped_column(nullable=True)
