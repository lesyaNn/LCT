import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """Append-only audit log (P5).

    P1-04-05 addition: nullable ``university_id`` (UUID, SET NULL) so audit
    events can be attributed to UUID universities and filtered per-university
    in SQL (``WHERE university_id = ? ORDER BY created_at DESC LIMIT 5``).
    The legacy ``entity_type``/``entity_id`` (Integer) columns are kept
    untouched for backward compatibility.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_university_id", "university_id"),
        Index("ix_audit_events_univ_created", "university_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    before_data: Mapped[str] = mapped_column(Text, default="{}")
    after_data: Mapped[str] = mapped_column(Text, default="{}")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(native_uuid=True),
        ForeignKey(
            "universities.id",
            name="fk_audit_events_university_id_universities",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _dump(v) -> str:
    try:
        return json.dumps(v or {}, ensure_ascii=False, default=str)
    except Exception:
        return "{}"
