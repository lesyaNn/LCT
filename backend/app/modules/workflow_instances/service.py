"""P2-02-03/P2-06-01 service: workflow instance creation + runtime detail.

Creation is atomic (single transaction)::

    validate university -> validate template (+ responsible) ->
    create WorkflowInstance -> snapshot active template stages ->
    wire current pointers -> record creation transition -> commit

Snapshot semantics (P2-01-02): the runtime stages are copied from the
*active* template stages at creation time (anchor + denormalized
name/description/is_required/order_index). Later template edits never touch
``instance_stages`` rows, so an old instance keeps its history.

Due-date cascade: ``workflow_stages.sla_days`` is a per-stage duration in
calendar days. Stage due dates accumulate in template order
(``start + cumsum(sla)``); ``sla_days NULL`` means "no deadline" and yields a
NULL stage due date (never invented). The instance ``due_date`` is the last
non-NULL stage due date (overall deadline) or NULL when no stage has one.

Overdue math is never local: every ``is_overdue``/``days_overdue`` comes
from :mod:`overdue.compute_overdue`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFound
from app.core.permissions import user_permissions
from app.models.catalog import Responsible, University
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowStageTransition,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

from .overdue import compute_overdue, today_utc
from .schemas import InstanceDetail, InstanceStageRead


def authorize_scope(user, instance) -> None:
    """University-scope gate for one instance (permission checked by router).

    Mirrors the P2-05 attachments gate: admins (``*``) skip scoping; other
    roles are confined to ``user.university_ids`` when the token carries that
    optional claim. Tokens without the claim keep the global RBAC behaviour.
    """
    perms = user_permissions(user)
    if "*" in perms:
        return
    scope = getattr(user, "university_ids", None)
    if scope is not None and str(instance.university_id) not in set(scope):
        raise HTTPException(status_code=403, detail="Forbidden: other university")


def require_university_scope(user, university_id: uuid.UUID) -> None:
    """Scope gate for creation (no instance row exists yet)."""
    authorize_scope(user, SimpleNamespace(university_id=university_id))


def get_instance_or_404(db: Session, instance_id: uuid.UUID) -> WorkflowInstance:
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None:
        raise NotFound("Workflow instance not found")
    return instance


def stage_due_dates(
    stages: list[WorkflowStage], start: date
) -> list[date | None]:
    """Cascade ``sla_days`` into per-stage due dates (pure, pinned by tests).

    ``sla_days`` NULL -> NULL due date (no deadline invented); otherwise the
    due date accumulates in order (``start + cumsum(sla)`` over non-NULL
    entries, NULL predecessors contributing 0 to later stages).
    """
    out: list[date | None] = []
    lag = 0
    for stage in stages:
        if stage.sla_days is None:
            out.append(None)
            continue
        lag += stage.sla_days
        out.append(start + timedelta(days=lag))
    return out


def _stage_to_read(row: InstanceStage, today: date) -> InstanceStageRead:
    overdue, days = compute_overdue(row.due_date, row.completed_at, today)
    return InstanceStageRead(
        id=row.id,
        template_stage_id=row.template_stage_id,
        order_index=row.order_index,
        name=row.name,
        description=row.description,
        is_required=row.is_required,
        status=row.status,
        due_date=row.due_date,
        completed_at=row.completed_at,
        is_overdue=overdue,
        days_overdue=days,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_instance_detail(
    db: Session, instance_id: uuid.UUID, today: date | None = None
) -> InstanceDetail:
    """Instance + runtime stages in stable order (no N+1 via selectinload)."""
    day = today if today is not None else today_utc()
    instance = (
        db.execute(
            select(WorkflowInstance)
            .options(selectinload(WorkflowInstance.instance_stages))
            .where(WorkflowInstance.id == instance_id)
        )
        .scalars()
        .first()
    )
    if instance is None:
        raise NotFound("Workflow instance not found")
    rows = sorted(instance.instance_stages, key=lambda r: r.order_index)
    overdue, days = compute_overdue(instance.due_date, instance.completed_at, day)
    return InstanceDetail(
        id=instance.id,
        university_id=instance.university_id,
        template_id=instance.template_id,
        current_stage_id=instance.current_stage_id,
        current_instance_stage_id=instance.current_instance_stage_id,
        responsible_id=instance.responsible_id,
        status=instance.status,
        due_date=instance.due_date,
        completed_at=instance.completed_at,
        is_overdue=overdue,
        days_overdue=days,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        stages=[_stage_to_read(r, day) for r in rows],
    )


def create_instance(
    db: Session,
    *,
    university_id: uuid.UUID,
    template_id: uuid.UUID,
    responsible_id: uuid.UUID | None = None,
    actor_sub: str = "",
    today: date | None = None,
) -> InstanceDetail:
    """Atomic creation: header + snapshot + pointers + creation transition."""
    university = db.get(University, university_id)
    if university is None:
        raise NotFound("University not found")
    template = db.get(WorkflowTemplate, template_id)
    if template is None:
        raise NotFound("Workflow template not found")
    if responsible_id is not None and db.get(Responsible, responsible_id) is None:
        raise NotFound("Responsible not found")

    day = today if today is not None else today_utc()
    template_stages = (
        db.execute(
            select(WorkflowStage)
            .where(
                WorkflowStage.template_id == template.id,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.order_index.asc())
        )
        .scalars()
        .all()
    )
    dues = stage_due_dates(list(template_stages), day)
    instance_due = next((d for d in reversed(dues) if d is not None), None)

    instance = WorkflowInstance(
        university_id=university.id,
        template_id=template.id,
        responsible_id=responsible_id,
        status="active",
        due_date=instance_due,
    )
    db.add(instance)
    db.flush()  # instance.id for the snapshot rows (same transaction)

    snapshots: list[InstanceStage] = []
    for position, (stage, due) in enumerate(zip(template_stages, dues), start=1):
        snapshots.append(
            InstanceStage(
                instance_id=instance.id,
                template_stage_id=stage.id,
                order_index=position,
                name=stage.name,
                description=stage.description,
                is_required=stage.is_required,
                status="pending",
                due_date=due,
            )
        )
    db.add_all(snapshots)
    if snapshots:
        db.flush()  # snapshot ids for the current pointer (same transaction)
        first = snapshots[0]
        instance.current_instance_stage_id = first.id
        instance.current_stage_id = first.template_stage_id
        db.add(
            WorkflowStageTransition(
                instance_id=instance.id,
                from_stage_id=None,
                to_stage_id=first.template_stage_id,
                actor_keycloak_sub=actor_sub or "",
            )
        )
    db.commit()  # header + snapshot + pointers + transition atomically
    return get_instance_detail(db, instance.id, today=day)
