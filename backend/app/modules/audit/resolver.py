"""Batch UUID → display-name resolution for audit presentation.

One query per table at most, regardless of page size — never a query per
audit row. All lookups are best-effort: missing rows simply stay unresolved
and the presentation layer falls back to explicit «unavailable» labels
(never raw UUIDs, never invented names).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    Responsible,
    University,
    Vendor,
)
from app.models.workflow_instances import WorkflowAttachment, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

from .presentation import FALLBACK_OBJECT_NAMES, is_uuid_like


def _parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _collect_from_payload(
    payload: Any,
    buckets: dict[str, set[uuid.UUID]],
    key_map: dict[str, str],
) -> None:
    if not isinstance(payload, dict):
        return
    for key, bucket in key_map.items():
        parsed = _parse_uuid(payload.get(key))
        if parsed is not None:
            buckets[bucket].add(parsed)
    # scope arrays (user access lists) resolve against universities.
    for key in ("value",):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                parsed = _parse_uuid(item)
                if parsed is not None:
                    buckets["university"].add(parsed)


_PAYLOAD_KEY_MAP = {
    "university_id": "university",
    "direction_id": "direction",
    "program_id": "program",
    "product_id": "product",
    "vendor_id": "vendor",
    "template_id": "template",
    "responsible_id": "responsible",
    "stage_responsible_id": "responsible",
    "stage_id": "stage",
    "instance_id": "instance",
}


def collect_ids(events: list[Any]) -> dict[str, set[uuid.UUID]]:
    """Gather every resolvable UUID referenced by a page of events."""
    buckets: dict[str, set[uuid.UUID]] = {
        "university": set(),
        "direction": set(),
        "program": set(),
        "product": set(),
        "vendor": set(),
        "template": set(),
        "stage": set(),
        "responsible": set(),
        "instance": set(),
        "attachment": set(),
    }
    for event in events:
        entity = str(getattr(event, "entity_type", "") or "").lower()
        if getattr(event, "university_id", None) is not None:
            parsed = _parse_uuid(event.university_id)
            if parsed is not None:
                buckets["university"].add(parsed)
        entity_id = _parse_uuid(getattr(event, "entity_id", None))
        if entity_id is not None:
            if entity == "university":
                buckets["university"].add(entity_id)
            elif entity == "direction":
                buckets["direction"].add(entity_id)
            elif entity == "program":
                # NOTE: attach events store the *link* id here; resolving it
                # best-effort against programs is harmless (miss → fallback).
                buckets["program"].add(entity_id)
            elif entity == "product":
                buckets["product"].add(entity_id)
            elif entity == "vendor":
                buckets["vendor"].add(entity_id)
            elif entity in ("responsible",):
                buckets["responsible"].add(entity_id)
            elif entity == "workflow_stage":
                buckets["stage"].add(entity_id)
            elif entity == "workflow_instance":
                buckets["instance"].add(entity_id)
            elif entity == "document":
                buckets["attachment"].add(entity_id)
            elif entity == "config":
                pass  # template/user ids resolved via payload, not entity_id
        _collect_from_payload(getattr(event, "old_value", None), buckets, _PAYLOAD_KEY_MAP)
        _collect_from_payload(getattr(event, "new_value", None), buckets, _PAYLOAD_KEY_MAP)
    return buckets


def _names_for(
    db: Session, model: Any, ids: set[uuid.UUID], label: Any
) -> dict[str, str]:
    if not ids:
        return {}
    try:
        rows = db.execute(
            select(model.id, label).where(model.id.in_(list(ids)))
        ).all()
    except Exception:
        return {}
    result: dict[str, str] = {}
    for row_id, name in rows:
        if name and str(name).strip():
            result[str(row_id).lower()] = str(name).strip()
    return result


def resolve_names(db: Session, events: list[Any]) -> dict[str, str]:
    """Return {lowercase-uuid: display name} for everything on the page."""
    buckets = collect_ids(events)
    resolved: dict[str, str] = {}
    resolved.update(_names_for(db, University, buckets["university"], University.name))
    resolved.update(_names_for(db, ITDirection, buckets["direction"], ITDirection.name))
    resolved.update(_names_for(db, ITProgram, buckets["program"], ITProgram.name))
    resolved.update(_names_for(db, ITProduct, buckets["product"], ITProduct.name))
    resolved.update(_names_for(db, Vendor, buckets["vendor"], Vendor.name))
    resolved.update(
        _names_for(db, Responsible, buckets["responsible"], Responsible.full_name)
    )
    resolved.update(
        _names_for(db, WorkflowTemplate, buckets["template"], WorkflowTemplate.name)
    )
    resolved.update(
        _names_for(db, WorkflowStage, buckets["stage"], WorkflowStage.name)
    )
    # Instances/attachments have no own display name; map them to a context
    # label via their university/template for «ВУЗ / Раздел» rendering.
    if buckets["instance"]:
        try:
            rows = db.execute(
                select(WorkflowInstance.id, WorkflowInstance.university_id,
                       WorkflowInstance.template_id)
                .where(WorkflowInstance.id.in_(list(buckets["instance"])))
            ).all()
            for row_id, uni_id, template_id in rows:
                if uni_id is not None:
                    buckets["university"].add(uni_id)
                if template_id is not None:
                    buckets["template"].add(template_id)
        except Exception:
            pass
    if buckets["attachment"]:
        try:
            rows = db.execute(
                select(WorkflowAttachment.id, WorkflowAttachment.instance_id)
                .where(WorkflowAttachment.id.in_(list(buckets["attachment"])))
            ).all()
            for row_id, instance_id in rows:
                if instance_id is not None:
                    buckets["instance"].add(instance_id)
        except Exception:
            pass
    # Second wave: universities/templates discovered via instances.
    if buckets["university"]:
        for key, name in _names_for(
            db, University, buckets["university"], University.name
        ).items():
            resolved.setdefault(key, name)
    if buckets["template"]:
        for key, name in _names_for(
            db, WorkflowTemplate, buckets["template"], WorkflowTemplate.name
        ).items():
            resolved.setdefault(key, name)
    return resolved


def entity_display_name(
    entity_type: str,
    entity_id: Any,
    old: Any,
    new: Any,
    names: dict[str, str],
) -> str | None:
    """Best-effort object name for an event; None means «use fallback»."""
    for payload in (new, old):
        if isinstance(payload, dict):
            for name_key in (
                "name", "full_name", "subject", "original_filename",
                "template_name", "program_name", "product_name",
                "responsible_name", "university_name", "target_name",
                "stage_name", "content",
            ):
                value = payload.get(name_key)
                if isinstance(value, str) and value.strip() and not is_uuid_like(value):
                    return value.strip()
    parsed = _parse_uuid(entity_id)
    if parsed is not None:
        resolved = names.get(str(parsed).lower())
        if resolved:
            return resolved
    return None


def fallback_name(entity_type: str, deleted: bool = False) -> str:
    from .presentation import DELETED_OBJECT_NAMES

    key = str(entity_type or "").lower()
    if deleted:
        return DELETED_OBJECT_NAMES.get(
            key, FALLBACK_OBJECT_NAMES.get(key, "Удалённый объект"))
    return FALLBACK_OBJECT_NAMES.get(key, "Объект (данные недоступны)")
