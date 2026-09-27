"""Report templates (ТЗ §6/§8): saved filter+column+format presets.

Table ``report_templates`` is owned by SQL migration ``000032`` (sole schema
source); this model only maps it. Personal templates (``owner_sub``) plus
admin-shared ones (``is_shared``). ``format``/``filters``/``columns`` reuse
the frozen ``ReportRequest`` contract — generators validate them already.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class ReportTemplate(UUIDPKMixin, Base):
    """One saved report parameter set."""

    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(native_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False, default=dict
    )
    columns: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


__all__ = ["ReportTemplate"]
