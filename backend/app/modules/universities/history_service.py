"""Scoped, user-facing university history built from the canonical audit ledger."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.workflow_instances import WorkflowAttachment, WorkflowInstance
from app.modules.audit.presentation import actor_display_name, summarize_event
from app.modules.audit.resolver import resolve_names
from app.modules.audit.service import AuditService
from app.modules.workflow_attachments.storage import StorageBackend


_ENTITIES = frozenset({
    "university", "workflow_instance", "workflow_stage", "workflow_comment",
    "document", "meeting", "responsible", "program", "product", "license",
})
_ACTIONS = frozenset({"WORKFLOW_TRANSITION", "ASSIGN_RESPONSIBLE"})


def _attachment(event) -> dict | None:
    if event.entity_type.lower() != "document" or event.action.upper() == "DELETE":
        return None
    payload = event.new_value if isinstance(event.new_value, dict) else event.old_value
    if not isinstance(payload, dict) or payload.get("audit_object_type") != "workflow_attachment":
        return None
    try:
        instance_id = str(uuid.UUID(str(payload["instance_id"])))
    except (KeyError, ValueError, TypeError):
        return None
    filename = payload.get("original_filename")
    if not isinstance(filename, str) or not filename.strip():
        return None
    return {
        "instance_id": instance_id,
        "attachment_id": str(event.entity_id),
        "file_name": filename,
        "mime_type": payload.get("mime_type") if isinstance(payload.get("mime_type"), str) else None,
    }


def present_history_event(event, names: dict[str, str], university_name: str | None) -> dict | None:
    """Discard technical entries and expose only presentation fields."""
    entity = str(event.entity_type or "").lower()
    action = str(event.action or "").upper()
    if entity not in _ENTITIES and action not in _ACTIONS:
        return None
    attachment = _attachment(event)
    if entity == "document" and attachment is None:
        return None  # Legacy document metadata has no downloadable file.
    summary = summarize_event(action, entity, event.old_value, event.new_value, names, university_name)
    if summary["title"] in ("Системное изменение", "Изменение данных"):
        return None
    return {
        "id": str(event.id),
        "timestamp": event.created_at,
        "user_name": actor_display_name(event.user_name, event.user_id),
        "role": event.role,
        "action": action,
        "entity_type": entity,
        "entity_id": str(event.entity_id),
        "title": summary["title"],
        "section": summary["section"],
        "object_name": summary.get("object_name"),
        "changes": summary.get("changes", []),
        "note": summary.get("note"),
        "attachment": attachment,
    }


def university_history(db, university_id: uuid.UUID, storage: StorageBackend) -> list[dict]:
    events = AuditService(db).recent_for_university(university_id, limit=100)
    names = resolve_names(db, events)
    university_name = names.get(str(university_id).lower())
    items = [item for event in events if (item := present_history_event(event, names, university_name)) is not None]
    attachment_ids = [uuid.UUID(item["attachment"]["attachment_id"]) for item in items if item["attachment"]]
    if not attachment_ids:
        return items
    rows = db.execute(
        select(WorkflowAttachment, WorkflowInstance.university_id)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowAttachment.instance_id)
        .where(WorkflowAttachment.id.in_(attachment_ids))
    ).all()
    persisted = {
        str(attachment.id): str(attachment.instance_id)
        for attachment, owner_university_id in rows
        if owner_university_id == university_id and storage.exists(attachment.storage_key)
    }
    return [item for item in items if not item["attachment"] or
            persisted.get(item["attachment"]["attachment_id"]) == item["attachment"]["instance_id"]]
