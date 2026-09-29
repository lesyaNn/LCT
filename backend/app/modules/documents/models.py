"""DEFERRED module — forward stub, see ``docs/DEFERRED_MODULES.md``.

Forward file-registry stub overlapping the canon ``documents`` table;
isolated on ``DeferredBase`` metadata. Canon:
``app.models.interactions.Document``.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.deferred import DeferredBase as Base


class FileMeta(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int] = mapped_column(Integer, default=0)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
