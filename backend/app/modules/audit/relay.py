"""Durable audit outbox relay with atomic, idempotent delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.audit_outbox import AuditOutbox
from app.modules.analytics.report_jobs import sanitize_error_message
from app.modules.audit.models import AuditEvent


def _sink_insert(db: Session, payload: dict, event_id: UUID) -> None:
    values = {
        "id": event_id,
        "user_id": payload["user_id"],
        "user_name": payload.get("user_name", ""),
        "role": payload.get("role", "user"),
        "entity_type": payload["entity_type"],
        "entity_id": UUID(payload["entity_id"]),
        "action": payload["action"],
        "university_id": UUID(payload["university_id"]) if payload.get("university_id") else None,
        "old_value": payload.get("old_value"),
        "new_value": payload.get("new_value"),
        "request_id": UUID(payload["request_id"]) if payload.get("request_id") else None,
        "ip_address": payload.get("ip_address"),
        "user_agent": payload.get("user_agent"),
    }
    if db.get_bind().dialect.name == "postgresql":
        db.execute(pg_insert(AuditEvent).values(**values).on_conflict_do_nothing(
            index_elements=[AuditEvent.id]
        ))
    else:
        db.execute(insert(AuditEvent).values(**values))


def relay_audit_events(db: Session, *, limit: int = 100) -> int:
    """Publish pending rows; failed sinks remain immediately retryable."""
    if limit < 1:
        return 0
    now = datetime.now(timezone.utc)
    stmt = (
        select(AuditOutbox)
        .where(AuditOutbox.status == "pending", AuditOutbox.available_at <= now)
        .order_by(AuditOutbox.created_at, AuditOutbox.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(db.execute(stmt).scalars())
    delivered = 0
    for row in rows:
        try:
            with db.begin_nested():
                _sink_insert(db, row.payload, row.id)
                db.flush()
            row.status = "published"
            row.published_at = datetime.now(timezone.utc)
            row.attempts += 1
            row.last_error = None
            delivered += 1
        except Exception as exc:
            row.status = "pending"
            row.attempts += 1
            row.last_error = sanitize_error_message(exc)
            row.available_at = datetime.now(timezone.utc)
            db.add(row)
    db.commit()
    return delivered


__all__ = ["relay_audit_events"]
