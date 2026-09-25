"""P2-02-01/02/04 service: templates CRUD + positional stage edits.

Ordering contract (mirrors migration 000011):

* ``order_index`` is 1-based, dense, unique per template.
* Omitted position on create = append (``max + 1``).
* Explicit position shifts ``[pos, max]`` one step right in the SAME
  transaction as the INSERT (``UNIQUE ... DEFERRABLE INITIALLY DEFERRED``
  makes the transient overlap legal; the committed state is still checked).
* Position past the end clamps to append (documented, pinned by tests);
  position ``< 1`` is rejected by the schema (422) before reaching here.
* Template lookups raise ``NotFound`` (404); a stage addressed under the
  wrong template id is also 404 (no cross-template leak).
* Stage PATCH accepts ``order_index`` moves (P2-02-04 reorder): the moved
  row is excluded from the shift ranges so the final sequence stays dense
  with no gaps; a move to the current position is a no-op.
* Concurrency (P2-02-04 §8): every positional write (add/move) first takes
  ``SELECT ... FOR UPDATE`` on the parent template row, serializing
  concurrent reorder/add writers of the SAME template so the committed
  sequence stays dense and unique. Different templates never block each
  other. No-op on SQLite (ignored there), enforced on PostgreSQL.
* Snapshot safety (P2-01-02): template/stage edits never touch
  ``instance_stages`` rows — old instances keep their copied
  name/description/is_required/order_index/due_date, new instances snapshot
  the current ACTIVE template stages (see workflow_instances.service).
* Retire path: stages are retired via ``is_active = FALSE`` (never
  hard-deleted while transition history references them — 000014 RESTRICT).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

from .schemas import StageRead, TemplateDetail, TemplateRead


# ---------------------------------------------------------------- templates


def list_template_page(db: Session, *, page: int, page_size: int) -> tuple[list[TemplateRead], int]:
    total = db.execute(select(func.count()).select_from(WorkflowTemplate)).scalar() or 0
    rows = (
        db.execute(
            select(WorkflowTemplate)
            .order_by(WorkflowTemplate.created_at.asc(), WorkflowTemplate.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return [TemplateRead.model_validate(r) for r in rows], total


def get_template_detail(db: Session, template_id: uuid.UUID) -> TemplateDetail:
    obj = (
        db.execute(
            select(WorkflowTemplate)
            .options(selectinload(WorkflowTemplate.stages))
            .where(WorkflowTemplate.id == template_id)
        )
        .scalars()
        .first()
    )
    if obj is None:
        raise NotFound("Workflow template not found")
    detail = TemplateDetail.model_validate(obj)
    detail.stages = sorted(detail.stages, key=lambda s: s.order_index)
    return detail


def create_template(
    db: Session, *, name: str, description: str | None, is_active: bool
) -> TemplateDetail:
    obj = WorkflowTemplate(name=name, description=description, is_active=is_active)
    db.add(obj)
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditAction, AuditService, context_for

        db.flush()
        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.ADMIN_CONFIG,
            entity_type="config", entity_id=obj.id,
            new_value={"name": obj.name, "is_active": obj.is_active},
        )
    db.commit()
    db.refresh(obj)
    return get_template_detail(db, obj.id)


def patch_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    fields: set[str],
    name: str | None,
    description: str | None,
    is_active: bool | None,
) -> TemplateDetail:
    obj = db.get(WorkflowTemplate, template_id)
    if obj is None:
        raise NotFound("Workflow template not found")
    old = {"name": obj.name, "description": obj.description,
           "is_active": obj.is_active}
    if "name" in fields and name is not None:
        obj.name = name
    if "description" in fields:
        obj.description = description
    if "is_active" in fields and is_active is not None:
        obj.is_active = is_active
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditAction, AuditService, context_for

        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.ADMIN_CONFIG,
            entity_type="config", entity_id=obj.id,
            old_value=old,
            new_value={"name": obj.name, "description": obj.description,
                       "is_active": obj.is_active},
        )
    db.commit()
    return get_template_detail(db, template_id)


# ------------------------------------------------------------------- stages


def _require_template(db: Session, template_id: uuid.UUID) -> WorkflowTemplate:
    obj = db.get(WorkflowTemplate, template_id)
    if obj is None:
        raise NotFound("Workflow template not found")
    return obj


def _lock_template(db: Session, template_id: uuid.UUID) -> WorkflowTemplate:
    """Load the template row taking ``FOR UPDATE`` (P2-02-04 §8).

    Serializes concurrent positional writers (add/reorder) of the same
    template: the second writer blocks until the first commits, then sees
    the fresh ordering. Raises ``NotFound`` (404) when missing. Ignored
    on SQLite, enforced on PostgreSQL.
    """
    obj = (
        db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.id == template_id).with_for_update()
        )
        .scalars()
        .first()
    )
    if obj is None:
        raise NotFound("Workflow template not found")
    return obj


def _require_stage(db: Session, template_id: uuid.UUID, stage_id: uuid.UUID) -> WorkflowStage:
    _require_template(db, template_id)
    obj = db.get(WorkflowStage, stage_id)
    if obj is None or obj.template_id != template_id:
        raise NotFound("Workflow stage not found")
    return obj


def _max_order(db: Session, template_id: uuid.UUID) -> int:
    return (
        db.execute(
            select(func.coalesce(func.max(WorkflowStage.order_index), 0)).where(
                WorkflowStage.template_id == template_id
            )
        ).scalar()
        or 0
    )


def create_stage(
    db: Session,
    template_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    order_index: int | None,
    is_required: bool,
    is_active: bool,
    sla_days: int | None,
) -> StageRead:
    _lock_template(db, template_id)  # serialize same-template writers (§8)
    top = _max_order(db, template_id)
    if order_index is None:
        pos = top + 1
    else:
        pos = max(1, min(order_index, top + 1))  # past-the-end clamps to append
    if pos <= top:
        db.execute(
            update(WorkflowStage)
            .where(
                WorkflowStage.template_id == template_id,
                WorkflowStage.order_index >= pos,
            )
            .values(order_index=WorkflowStage.order_index + 1)
        )
    obj = WorkflowStage(
        template_id=template_id,
        name=name,
        description=description,
        order_index=pos,
        is_required=is_required,
        is_active=is_active,
        sla_days=sla_days,
    )
    db.add(obj)
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditAction, AuditService, context_for

        db.flush()
        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.ADMIN_CONFIG,
            entity_type="workflow_stage", entity_id=obj.id,
            new_value={"template_id": template_id, "name": obj.name,
                       "order_index": obj.order_index, "is_active": obj.is_active},
        )
    db.commit()  # shift + insert atomically; UNIQUE checked at COMMIT (deferred)
    db.refresh(obj)
    return StageRead.model_validate(obj)


def _ensure_no_active_current(db: Session, stage: WorkflowStage) -> None:
    """P2-02-04: a template stage that is current in any active instance
    cannot be retired — the pointer would dangle for running workflows."""
    from app.models.workflow_instances import WorkflowInstance

    hit = db.execute(
        select(WorkflowInstance.id)
        .where(
            WorkflowInstance.status == "active",
            WorkflowInstance.current_stage_id == stage.id,
        )
        .limit(1)
    ).first()
    if hit is not None:
        raise Conflict(
            "Stage is current in an active workflow instance and cannot be disabled"
        )


def patch_stage(
    db: Session,
    template_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    fields: set[str],
    name: str | None,
    description: str | None,
    order_index: int | None,
    is_required: bool | None,
    is_active: bool | None,
    sla_days: int | None,
) -> StageRead:
    _lock_template(db, template_id)  # serialize same-template writers (§8)
    obj = _require_stage(db, template_id, stage_id)
    old = {"name": obj.name, "order_index": obj.order_index,
           "is_active": obj.is_active, "is_required": obj.is_required,
           "sla_days": obj.sla_days}
    if "name" in fields and name is not None:
        obj.name = name
    if "description" in fields:
        obj.description = description
    if "is_required" in fields and is_required is not None:
        obj.is_required = is_required
    if "is_active" in fields and is_active is not None:
        if not is_active:
            _ensure_no_active_current(db, obj)
        obj.is_active = is_active
    if "sla_days" in fields:
        obj.sla_days = sla_days
    if "order_index" in fields and order_index is not None:
        _move_stage(db, obj, order_index)
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditAction, AuditService, context_for

        AuditService(db).log_event(
            context=context_for(db), action=AuditAction.ADMIN_CONFIG,
            entity_type="workflow_stage", entity_id=obj.id,
            old_value=old,
            new_value={"name": obj.name, "order_index": obj.order_index,
                       "is_active": obj.is_active, "is_required": obj.is_required,
                       "sla_days": obj.sla_days},
        )
    db.commit()  # field updates + positional move atomically
    db.refresh(obj)
    return StageRead.model_validate(obj)


def _move_stage(db: Session, obj: WorkflowStage, new_pos: int) -> None:
    """Reposition ``obj`` inside its template, keeping the sequence dense."""
    top = _max_order(db, obj.template_id)
    new_pos = max(1, min(new_pos, top))
    old = obj.order_index
    if new_pos == old:
        return
    if new_pos < old:
        db.execute(
            update(WorkflowStage)
            .where(
                WorkflowStage.template_id == obj.template_id,
                WorkflowStage.id != obj.id,
                WorkflowStage.order_index >= new_pos,
                WorkflowStage.order_index < old,
            )
            .values(order_index=WorkflowStage.order_index + 1)
        )
    else:
        db.execute(
            update(WorkflowStage)
            .where(
                WorkflowStage.template_id == obj.template_id,
                WorkflowStage.id != obj.id,
                WorkflowStage.order_index > old,
                WorkflowStage.order_index <= new_pos,
            )
            .values(order_index=WorkflowStage.order_index - 1)
        )
    obj.order_index = new_pos
