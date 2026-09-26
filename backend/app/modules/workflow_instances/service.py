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

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFound
from app.core.policies import apply_university_scope, ensure_university_access
from app.models.catalog import ITProduct, ITProgram, Responsible, University, UniversityResponsible
from app.models.external import ExternalApplication
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowStageTransition,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

from .overdue import compute_overdue, today_utc
from .schemas import InstanceDetail, InstanceStageRead


def authorize_scope(user, instance) -> None:
    """Compatibility adapter for existing P2 call sites."""
    ensure_university_access(instance.university_id, user)


def require_university_scope(user, university_id: uuid.UUID) -> None:
    """Scope gate for creation (no instance row exists yet)."""
    ensure_university_access(university_id, user)


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


def _stage_to_read(row: InstanceStage, today: date, counts: tuple[int, int] = (0, 0)) -> InstanceStageRead:
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
        tasks_total=counts[0],
        tasks_completed=counts[1],
    )


def get_instance_detail(
    db: Session, instance_id: uuid.UUID, today: date | None = None
) -> InstanceDetail:
    """Instance + runtime stages in stable order (no N+1 via selectinload)."""
    day = today if today is not None else today_utc()
    result = db.execute(
        select(WorkflowInstance, University.name, University.city, ITProgram.name, ITProduct.name, Responsible.full_name, Responsible.email, Responsible.phone)
        .join(University, University.id == WorkflowInstance.university_id)
        .outerjoin(ITProgram, ITProgram.id == WorkflowInstance.program_id)
        .outerjoin(ITProduct, ITProduct.id == WorkflowInstance.product_id)
        .outerjoin(Responsible, Responsible.id == WorkflowInstance.responsible_id)
        .options(
            selectinload(WorkflowInstance.instance_stages),
            selectinload(WorkflowInstance.tasks),
        )
        .where(WorkflowInstance.id == instance_id)
    ).first()
    if result is None:
        raise NotFound("Workflow instance not found")
    instance, university_name, university_city, program_name, product_name, responsible_name, responsible_email, responsible_phone = result
    return _to_detail(instance, university_name, university_city, program_name, product_name, responsible_name, responsible_email, responsible_phone, day)


def _to_detail(instance: WorkflowInstance, university_name: str,
               university_city: str | None, program_name: str | None,
               product_name: str | None, responsible_name: str | None,
               responsible_email: str | None, responsible_phone: str | None,
               day: date) -> InstanceDetail:
    rows = sorted(instance.instance_stages, key=lambda r: r.order_index)
    task_counts: dict[uuid.UUID | None, tuple[int, int]] = {}
    for task in instance.tasks:
        total, completed = task_counts.get(task.stage_id, (0, 0))
        task_counts[task.stage_id] = (total + 1, completed + (task.status == "done"))
    overdue, days = compute_overdue(instance.due_date, instance.completed_at, day)
    return InstanceDetail(
        id=instance.id,
        university_id=instance.university_id,
        template_id=instance.template_id,
        program_id=instance.program_id,
        product_id=instance.product_id,
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
        stages=[_stage_to_read(r, day, task_counts.get(r.template_stage_id, (0, 0))) for r in rows],
        university_name=university_name,
        university_city=university_city,
        program_name=program_name,
        product_name=product_name,
        responsible_name=responsible_name,
        responsible_email=responsible_email,
        responsible_phone=responsible_phone,
    )


def get_instance_by_program(db: Session, university_id: uuid.UUID, program_id: uuid.UUID) -> InstanceDetail | None:
    """A missing binding is a valid empty state; never infer it by name/template."""
    instance_id = db.scalar(select(WorkflowInstance.id).where(
        WorkflowInstance.university_id == university_id,
        WorkflowInstance.program_id == program_id,
    ))
    return get_instance_detail(db, instance_id) if instance_id else None


def list_instance_page(db: Session, user, page: int, page_size: int, university_id: uuid.UUID | None = None):
    stmt = select(WorkflowInstance.id)
    if university_id is not None:
        stmt = stmt.where(WorkflowInstance.university_id == university_id)
    stmt = apply_university_scope(stmt, WorkflowInstance.university_id, user)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    ids = db.scalars(stmt.order_by(WorkflowInstance.created_at.desc(), WorkflowInstance.id)
                     .offset((page - 1) * page_size).limit(page_size)).all()
    if not ids:
        return [], total
    rows = db.execute(
        select(WorkflowInstance, University.name, University.city, ITProgram.name, ITProduct.name, Responsible.full_name, Responsible.email, Responsible.phone)
        .join(University, University.id == WorkflowInstance.university_id)
        .outerjoin(ITProgram, ITProgram.id == WorkflowInstance.program_id)
        .outerjoin(ITProduct, ITProduct.id == WorkflowInstance.product_id)
        .outerjoin(Responsible, Responsible.id == WorkflowInstance.responsible_id)
        .options(
            selectinload(WorkflowInstance.instance_stages),
            selectinload(WorkflowInstance.tasks),
        )
        .where(WorkflowInstance.id.in_(ids))
    ).all()
    day = today_utc()
    details = {instance.id: _to_detail(instance, name, city, program_name, product_name, responsible_name, responsible_email, responsible_phone, day)
               for instance, name, city, program_name, product_name, responsible_name, responsible_email, responsible_phone in rows}
    return [details[instance_id] for instance_id in ids], total


def list_task_page(db: Session, instance_id: uuid.UUID, page: int, page_size: int):
    stmt = select(WorkflowTask).where(WorkflowTask.instance_id == instance_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(WorkflowTask.created_at.asc(), WorkflowTask.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def create_instance(
    db: Session,
    *,
    university_id: uuid.UUID,
    template_id: uuid.UUID,
    program_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    responsible_id: uuid.UUID | None = None,
    actor_sub: str = "",
    today: date | None = None,
    external_application: ExternalApplication | None = None,
) -> InstanceDetail:
    """Atomic creation: header + snapshot + pointers + creation transition."""
    university = db.get(University, university_id)
    if university is None:
        raise NotFound("University not found")
    if program_id is not None and db.scalar(
        select(UniversityProgram.id).where(
            UniversityProgram.university_id == university_id,
            UniversityProgram.program_id == program_id,
        )
    ) is None:
        raise NotFound("Program is not linked to university")
    template = db.get(WorkflowTemplate, template_id)
    if template is None:
        raise NotFound("Workflow template not found")
    if product_id is not None and db.get(ITProduct, product_id) is None:
        raise NotFound("Product not found")
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
        program_id=program_id,
        product_id=product_id,
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
    if external_application is not None:
        external_application.workflow_instance_id = instance.id
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
    if "audit_context" in db.info:
        # H3: instance creation is audited in a follow-up statement (the core
        # creation stays atomic above); without audit_context (seeds/scripts)
        # this is skipped, like other services.
        from app.modules.audit.service import AuditService, context_for

        AuditService(db).log_event(
            context=context_for(db, actor_sub or "system"),
            action="CREATE",
            entity_type="workflow_instance",
            entity_id=instance.id,
            university_id=university.id,
            new_value={
                "template_id": str(template.id),
                "program_id": str(program_id) if program_id else None,
                "product_id": str(product_id) if product_id else None,
                "stages": len(snapshots),
                "external_application_id": str(external_application.id) if external_application else None,
            },
        )
        db.commit()
    return get_instance_detail(db, instance.id, today=day)


def set_instance_responsible(
    db: Session,
    instance_id: uuid.UUID,
    responsible_id: uuid.UUID | None,
    actor_sub: str = "",
) -> InstanceDetail:
    """Assign (or clear) the instance responsible.

    Only a responsible linked to the instance university
    (``university_responsibles``) can be assigned; ``None`` clears it.
    """
    instance = get_instance_or_404(db, instance_id)
    old_responsible_id = instance.responsible_id
    if responsible_id is not None:
        if db.get(Responsible, responsible_id) is None:
            raise NotFound("Responsible not found")
        linked = db.scalar(
            select(UniversityResponsible.id).where(
                UniversityResponsible.university_id == instance.university_id,
                UniversityResponsible.responsible_id == responsible_id,
            )
        )
        if linked is None:
            raise NotFound("Responsible is not linked to university")
    instance.responsible_id = responsible_id
    db.commit()
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditService, context_for

        AuditService(db).log_event(
            context=context_for(db, actor_sub or "system"),
            action="UPDATE",
            entity_type="workflow_instance",
            entity_id=instance.id,
            university_id=instance.university_id,
            old_value={"responsible_id": str(old_responsible_id) if old_responsible_id else None},
            new_value={"responsible_id": str(responsible_id) if responsible_id else None},
        )
        db.commit()
    return get_instance_detail(db, instance.id)
