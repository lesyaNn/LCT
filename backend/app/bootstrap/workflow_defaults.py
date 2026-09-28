"""Startup bootstrap: the standard university-interaction workflow template.

Creates (once, idempotently) the production baseline template
``"Стандартный маршрут взаимодействия с вузом"`` with its 5 stages.
Runs from the FastAPI lifespan at every backend start; the second and all
later starts are a NO-OP (no duplicates, no rewrites, no audit noise).

Design notes (pinned by ``tests/test_default_workflow_bootstrap.py``):

* Natural key is the template ``name`` (``uq_workflow_templates_name``).
  No ``code``/``slug`` column exists, and no migration is added for this —
  the exact name is the stable identifier.
* Stages are keyed by ``(template_id, order_index)``
  (``uq_workflow_stages_template_order``). Stages are only INSERTed when
  their ``order_index`` is missing; existing rows are never UPDATEed, so
  user renames/SLA edits survive restarts.
* ``sla_days`` semantics (see
  ``app.modules.workflow_instances.service.stage_due_dates``): per-stage
  duration in calendar days, accumulated into due dates; ``NULL`` means
  "no deadline". The values below are stage durations, not absolute dates.
* No workflow *instances* are ever created here — an instance appears only
  when a user launches the template for a concrete university/program.
* No audit/outbox writes: the bootstrap session never carries
  ``audit_context`` in ``db.info``, so the audit service (which only logs
  when that key is present) stays silent on both first and repeat runs.
* Concurrency: two backends starting at once may both pass the SELECT and
  attempt INSERT. The UNIQUE constraints reject the loser with
  ``IntegrityError``; it rolls back, re-reads, and converges to the same
  single template (no filesystem locks).
* Legacy collision: ``app.db.seed_workflow`` seeds a 14-stage template
  under the SAME name (manual ``python -m app.db.seed`` path, never run at
  startup). If such a diverged template is found (more than 5 stages, or
  existing stage names that do not match this spec), it is left untouched
  and a warning is logged — never destroyed or rewritten.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.db.seed_workflow import STAGES_14, TEMPLATE_NAME as SPEC_TEMPLATE_NAME

log = logging.getLogger("rtk.bootstrap.workflow")

TEMPLATE_NAME = "Стандартный маршрут взаимодействия с вузом"
TEMPLATE_DESCRIPTION = (
    "Базовый процесс взаимодействия с вузом от первого контакта "
    "до запуска образовательной программы."
)

# (stage name, sla_days, is_required) in canonical order;
# order_index = position (1-based). All standard stages are required:
# transitions only allow skipping optional stages, so the default route
# is strictly sequential.
DEFAULT_STAGES: list[tuple[str, int, bool]] = [
    ("Первичный контакт", 5, True),
    ("Согласование программы", 10, True),
    ("Подготовка документов", 10, True),
    ("Согласование договора", 15, True),
    ("Запуск программы", 10, True),
]

EXPECTED_COUNT = len(DEFAULT_STAGES)


def _find_template(db: Session) -> WorkflowTemplate | None:
    return db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()


def ensure_spec_workflow_template(db: Session) -> dict:
    """Create the 14-stage ТЗ route once; preserve all existing user edits."""
    existing = db.scalar(select(WorkflowTemplate.id).where(WorkflowTemplate.name == SPEC_TEMPLATE_NAME))
    if existing is not None:
        return {"status": "ready", "template_id": existing, "stages": 14}
    try:
        template = WorkflowTemplate(name=SPEC_TEMPLATE_NAME, is_active=True)
        db.add(template)
        db.flush()
        for position, (name, required) in enumerate(STAGES_14, start=1):
            db.add(WorkflowStage(template_id=template.id, name=name,
                                 order_index=position, is_required=required,
                                 is_active=True, sla_days=None))
        db.commit()
        return {"status": "created", "template_id": template.id, "stages": 14}
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(WorkflowTemplate.id).where(WorkflowTemplate.name == SPEC_TEMPLATE_NAME))
        if existing is None:
            raise
        return {"status": "ready", "template_id": existing, "stages": 14}


def _ordered_stages(db: Session, template_id) -> list[WorkflowStage]:
    return list(
        db.execute(
            select(WorkflowStage)
            .where(WorkflowStage.template_id == template_id)
            .order_by(WorkflowStage.order_index.asc())
        ).scalars()
    )


def ensure_default_workflow_template(db: Session) -> dict:
    """Ensure the standard template + its 5 stages exist. Idempotent.

    Returns a small status dict (``status`` is one of ``created``,
    ``ready``, ``recovered`` or ``diverged``). Never raises on the
    expected race (``IntegrityError`` converges to a re-read); unexpected
    DB errors propagate to the caller (lifespan logs them with traceback).
    """
    template = _find_template(db)
    if template is None:
        try:
            return _create_full(db)
        except IntegrityError:
            # Lost the creation race (or a concurrent seed won):
            # roll back and fall through to the found-path below.
            db.rollback()
            template = _find_template(db)
            if template is None:  # pragma: no cover - defensive
                raise
            log.info("[bootstrap] Standard workflow template race resolved, reusing existing")
    return _ensure_stages(db, template)


def _create_full(db: Session) -> dict:
    log.info("[bootstrap] Standard workflow template not found, creating")
    template = WorkflowTemplate(
        name=TEMPLATE_NAME,
        description=TEMPLATE_DESCRIPTION,
        is_active=True,
    )
    db.add(template)
    db.flush()  # assign template.id for the stage rows (same transaction)
    for position, (name, sla_days, is_required) in enumerate(DEFAULT_STAGES, start=1):
        db.add(
            WorkflowStage(
                template_id=template.id,
                name=name,
                description=None,
                order_index=position,
                is_required=is_required,
                is_active=True,
                sla_days=sla_days,
            )
        )
    db.commit()
    log.info("[bootstrap] Standard workflow template created: %d stages", EXPECTED_COUNT)
    return {
        "status": "created",
        "template_id": template.id,
        "templates": 1,
        "stages": EXPECTED_COUNT,
        "instances_created": 0,
    }


def _ensure_stages(db: Session, template: WorkflowTemplate) -> dict:
    stages = _ordered_stages(db, template.id)
    orders = [s.order_index for s in stages]

    # Happy path: exactly the 5 dense positions -> NO-OP, whatever the
    # names/SLA are (user renames and SLA tuning survive restarts).
    if orders == [1, 2, 3, 4, 5]:
        log.info("[bootstrap] Standard workflow template ready")
        return {
            "status": "ready",
            "template_id": template.id,
            "templates": 1,
            "stages": len(stages),
            "instances_created": 0,
        }

    # Diverged template (e.g. the legacy manual 14-stage seed under the
    # same name, or a heavily customized one): never destroy, just warn.
    if len(stages) > EXPECTED_COUNT or not _prefix_matches(stages):
        log.warning(
            "[bootstrap] Standard workflow template %r exists with unexpected "
            "structure (%d stages), leaving untouched",
            TEMPLATE_NAME,
            len(stages),
        )
        return {
            "status": "diverged",
            "template_id": template.id,
            "templates": 1,
            "stages": len(stages),
            "instances_created": 0,
        }

    # Partial state (interrupted first bootstrap): refill ONLY the missing
    # order positions with spec values; existing rows are untouched.
    expected_by_order = {i + 1: spec for i, spec in enumerate(DEFAULT_STAGES)}
    missing = [pos for pos in range(1, EXPECTED_COUNT + 1) if pos not in set(orders)]
    try:
        for pos in missing:
            name, sla_days, is_required = expected_by_order[pos]
            db.add(
                WorkflowStage(
                    template_id=template.id,
                    name=name,
                    description=None,
                    order_index=pos,
                    is_required=is_required,
                    is_active=True,
                    sla_days=sla_days,
                )
            )
        db.commit()
    except IntegrityError:
        # Concurrent bootstrap filled the gap first: converge to re-read.
        db.rollback()
        stages = _ordered_stages(db, template.id)
        log.info("[bootstrap] Standard workflow template race resolved during recovery")
        return {
            "status": "ready",
            "template_id": template.id,
            "templates": 1,
            "stages": len(stages),
            "instances_created": 0,
        }
    total = len(_ordered_stages(db, template.id))
    log.info("[bootstrap] Standard workflow template recovered: added %d stage(s)", len(missing))
    return {
        "status": "recovered",
        "template_id": template.id,
        "templates": 1,
        "stages": total,
        "instances_created": 0,
    }


def _prefix_matches(stages: list[WorkflowStage]) -> bool:
    """True when every existing stage carries the expected spec name.

    Guards the partial-recovery path: a same-named template whose stages
    were customized/renamed by a user (or seeded differently) must not be
    silently "completed" with spec stages mixed into custom ones.
    """
    by_order = {s.order_index: s for s in stages}
    for position, (expected_name, _sla, _req) in enumerate(DEFAULT_STAGES, start=1):
        row = by_order.get(position)
        if row is not None and row.name != expected_name:
            return False
    return True
