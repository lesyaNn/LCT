"""Names recorded with Workflow mutations, resolved in one query per page."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.audit.presentation import actor_display_name


def workflow_actor_names(db: Session, entity_type: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(AuditEvent.entity_id, AuditEvent.user_name, AuditEvent.user_id)
        .where(AuditEvent.entity_type == entity_type,
               AuditEvent.entity_id.in_(ids), AuditEvent.action == "CREATE")
        .order_by(AuditEvent.created_at)
    ).all()
    names: dict[uuid.UUID, str] = {}
    for entity_id, user_name, user_id in rows:
        names.setdefault(entity_id, actor_display_name(user_name, user_id))
    return names
