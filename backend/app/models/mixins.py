"""Shared column mixins for P1 models (P1-01-05)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid as SAUuid


class UUIDPKMixin:
    """PostgreSQL UUID primary key (``uuid4`` generated client-side).

    Uses generic ``Uuid`` so the same models run on PostgreSQL (native UUID)
    and on SQLite (CHAR(32)) for fast unit tests. IDs are always ``uuid.UUID``
    objects in Python.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(native_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Timezone-aware ``created_at`` / ``updated_at`` (P1-01-05).

    * ``TIMESTAMP WITH TIME ZONE`` on PostgreSQL (``DateTime(timezone=True)``).
    * ``created_at`` set once on INSERT (Python default + ``server_default``).
    * ``updated_at`` refreshed on every ORM UPDATE via ``onupdate`` and on
      the DB side via ``server_onupdate`` where supported.
    * Never naive: defaults use ``datetime.now(timezone.utc)``.
    """

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
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        server_onupdate=func.now(),
    )


# Re-export for migration scripts that prefer explicit imports.
_ = PG_UUID
