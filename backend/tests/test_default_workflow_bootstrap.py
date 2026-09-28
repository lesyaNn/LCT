"""Regression tests for the startup default-workflow bootstrap.

Covers the task acceptance list (§17): creation on an empty DB, exact
5 stages in order, second-run idempotency (templates + stages), unrelated
templates/instances untouched, partial-state recovery, user-modification
preservation, no auto-created instances, audit/outbox silence on NO-OP,
and concurrent-initialization convergence.

Runs on plain SQLite (same DDL-equivalent fixture style as
``test_seed_demo.py``) so they execute with and without PostgreSQL.
"""

import uuid

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
import app.models.audit_outbox  # noqa: F401
import app.modules.audit.models  # noqa: F401
from app.bootstrap.workflow_defaults import (
    DEFAULT_STAGES,
    TEMPLATE_DESCRIPTION,
    TEMPLATE_NAME,
    ensure_default_workflow_template,
    ensure_spec_workflow_template,
)
from app.db.seed_workflow import STAGES_14, TEMPLATE_NAME as SPEC_TEMPLATE_NAME
from app.db.base import Base
from app.models.audit_outbox import AuditOutbox
from app.models.catalog import University
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.audit.models import AuditEvent


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    skip = {"instance_stages", "workflow_stages", "audit_events"}
    for name, table in Base.metadata.tables.items():
        if name not in skip:
            table.create(eng)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE workflow_stages ("
            "template_id CHAR(32) NOT NULL, name VARCHAR(512) NOT NULL, "
            "description TEXT, order_index INTEGER NOT NULL, "
            "is_required BOOLEAN NOT NULL DEFAULT 1, "
            "is_active BOOLEAN NOT NULL DEFAULT 1, sla_days INTEGER, "
            "id CHAR(32) NOT NULL PRIMARY KEY, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "UNIQUE (template_id, order_index), "
            "FOREIGN KEY(template_id) REFERENCES workflow_templates (id) "
            "ON DELETE CASCADE)"
        ))
        conn.execute(text(
            "CREATE TABLE instance_stages ("
            "instance_id CHAR(32) NOT NULL, template_stage_id CHAR(32), "
            "order_index INTEGER NOT NULL, name VARCHAR(512) NOT NULL, "
            "description TEXT, is_required BOOLEAN NOT NULL DEFAULT 1, "
            "status VARCHAR(32) NOT NULL DEFAULT 'pending', due_date DATE, "
            "completed_at DATETIME, id CHAR(32) NOT NULL PRIMARY KEY, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "UNIQUE (instance_id, order_index), "
            "FOREIGN KEY(instance_id) REFERENCES workflow_instances (id) "
            "ON DELETE CASCADE)"
        ))
        conn.execute(text(
            "CREATE TABLE audit_events ("
            "id CHAR(32) NOT NULL PRIMARY KEY, user_id TEXT NOT NULL, "
            "user_name VARCHAR(512) NOT NULL DEFAULT '', role VARCHAR(32) NOT NULL DEFAULT 'user', "
            "entity_type VARCHAR(64) NOT NULL, entity_id CHAR(32) NOT NULL, "
            "action VARCHAR(32) NOT NULL, old_value JSON, new_value JSON, "
            "ip_address VARCHAR(45), request_id CHAR(32), user_agent TEXT, "
            "university_id CHAR(32), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ))
    with Session(eng) as session:
        yield session
    eng.dispose()


def _counts(db: Session):
    n_templates = db.execute(
        select(func.count()).select_from(WorkflowTemplate).where(
            WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar()
    template = db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()
    n_stages = 0
    if template is not None:
        n_stages = db.execute(
            select(func.count()).select_from(WorkflowStage).where(
                WorkflowStage.template_id == template.id)
        ).scalar()
    n_instances = db.execute(select(func.count()).select_from(WorkflowInstance)).scalar()
    return template, n_templates, n_stages, n_instances


def _stage_rows(db: Session, template) -> list[WorkflowStage]:
    return list(db.execute(
        select(WorkflowStage).where(WorkflowStage.template_id == template.id)
        .order_by(WorkflowStage.order_index.asc())
    ).scalars())


# 1. Empty DB: default template is created.
def test_empty_db_creates_default_template(db):
    result = ensure_default_workflow_template(db)
    assert result["status"] == "created"
    template, n_templates, n_stages, n_instances = _counts(db)
    assert n_templates == 1
    assert template is not None
    assert template.name == TEMPLATE_NAME
    assert template.description == TEMPLATE_DESCRIPTION
    assert n_stages == 5
    assert n_instances == 0


def test_spec_route_has_fourteen_editable_stages_and_is_idempotent(db):
    assert ensure_spec_workflow_template(db)["status"] == "created"
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == SPEC_TEMPLATE_NAME))
    rows = _stage_rows(db, template)
    assert [(row.name, row.is_required) for row in rows] == STAGES_14
    assert all(row.sla_days is None for row in rows)
    rows[0].name = "Согласованный пользователем первый этап"
    db.commit()
    assert ensure_spec_workflow_template(db)["status"] == "ready"
    assert _stage_rows(db, template)[0].name == "Согласованный пользователем первый этап"
    assert len(_stage_rows(db, template)) == 14


# 2. Stages: exactly 5, correct order, names and SLA durations.
def test_stages_exact_order_and_sla(db):
    ensure_default_workflow_template(db)
    template, _, _, _ = _counts(db)
    rows = _stage_rows(db, template)
    assert [r.order_index for r in rows] == [1, 2, 3, 4, 5]
    assert [r.name for r in rows] == [name for name, _sla, _req in DEFAULT_STAGES]
    assert [r.sla_days for r in rows] == [sla for _name, sla, _req in DEFAULT_STAGES]
    assert [r.name for r in rows] == [
        "Первичный контакт",
        "Согласование программы",
        "Подготовка документов",
        "Согласование договора",
        "Запуск программы",
    ]
    assert all(r.is_required for r in rows)


# 3. Second run: no duplicate template.
def test_second_run_no_duplicate_template(db):
    ensure_default_workflow_template(db)
    result = ensure_default_workflow_template(db)
    assert result["status"] == "ready"
    _, n_templates, _, _ = _counts(db)
    assert n_templates == 1


# 4. Second run: no duplicate stages.
def test_second_run_no_duplicate_stages(db):
    ensure_default_workflow_template(db)
    first_ids = {r.id for r in _stage_rows(db, _counts(db)[0])}
    ensure_default_workflow_template(db)
    template, _, n_stages, _ = _counts(db)
    assert n_stages == 5
    assert {r.id for r in _stage_rows(db, template)} == first_ids


# 5. Existing unrelated templates are untouched.
def test_unrelated_templates_untouched(db):
    other = WorkflowTemplate(name="Custom user template", description="keep me")
    db.add(other)
    db.flush()
    db.add(WorkflowStage(template_id=other.id, name="Only stage",
                         order_index=1, is_required=True))
    db.commit()
    ensure_default_workflow_template(db)
    ensure_default_workflow_template(db)
    total = db.execute(select(func.count()).select_from(WorkflowTemplate)).scalar()
    assert total == 2
    kept = db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == "Custom user template")
    ).scalar_one()
    assert kept.description == "keep me"
    kept_stages = db.execute(
        select(WorkflowStage).where(WorkflowStage.template_id == kept.id)
    ).scalars().all()
    assert len(kept_stages) == 1 and kept_stages[0].name == "Only stage"


# 6. Existing workflow instances are untouched.
def test_existing_instances_untouched(db):
    uni = University(name="Test University " + uuid.uuid4().hex[:8])
    db.add(uni)
    db.flush()
    other = WorkflowTemplate(name="Other template")
    db.add(other)
    db.flush()
    db.add(WorkflowStage(template_id=other.id, name="S1", order_index=1))
    db.flush()
    instance = WorkflowInstance(university_id=uni.id, template_id=other.id)
    db.add(instance)
    db.commit()
    instance_id = instance.id
    ensure_default_workflow_template(db)
    ensure_default_workflow_template(db)
    assert db.execute(select(func.count()).select_from(WorkflowInstance)).scalar() == 1
    assert db.get(WorkflowInstance, instance_id) is not None


# 7. Partially initialized default template is safely recovered.
def test_partial_state_recovered(db):
    template = WorkflowTemplate(name=TEMPLATE_NAME, description=TEMPLATE_DESCRIPTION)
    db.add(template)
    db.flush()
    for pos in range(1, 4):  # interrupted bootstrap: only 3 of 5 stages
        name, sla, req = DEFAULT_STAGES[pos - 1]
        db.add(WorkflowStage(template_id=template.id, name=name,
                             order_index=pos, is_required=req, sla_days=sla))
    db.commit()
    result = ensure_default_workflow_template(db)
    assert result["status"] == "recovered"
    template, _, n_stages, _ = _counts(db)
    assert n_stages == 5
    rows = _stage_rows(db, template)
    assert [r.name for r in rows] == [n for n, _s, _r in DEFAULT_STAGES]
    # Recovery is itself idempotent.
    assert ensure_default_workflow_template(db)["status"] == "ready"
    assert _counts(db)[2] == 5


# 8. User-modified default template is not overwritten.
def test_user_modifications_preserved(db):
    ensure_default_workflow_template(db)
    template, _, _, _ = _counts(db)
    rows = _stage_rows(db, template)
    rows[0].name = "Первичный контакт с представителем ВУЗа"
    rows[1].sla_days = 99
    template.description = "Custom user description"
    db.commit()
    assert ensure_default_workflow_template(db)["status"] == "ready"
    template, _, n_stages, _ = _counts(db)
    assert n_stages == 5
    rows = _stage_rows(db, template)
    assert rows[0].name == "Первичный контакт с представителем ВУЗа"
    assert rows[1].sla_days == 99
    assert template.description == "Custom user description"


# 9. No workflow instances are created automatically.
def test_no_instances_created(db):
    ensure_default_workflow_template(db)
    ensure_default_workflow_template(db)
    ensure_default_workflow_template(db)
    assert db.execute(select(func.count()).select_from(WorkflowInstance)).scalar() == 0


# 10. Repeated runs do not grow audit/outbox.
def test_noop_produces_no_audit_or_outbox(db):
    ensure_default_workflow_template(db)
    n_audit = db.execute(select(func.count()).select_from(AuditEvent)).scalar()
    n_outbox = db.execute(select(func.count()).select_from(AuditOutbox)).scalar()
    ensure_default_workflow_template(db)
    ensure_default_workflow_template(db)
    assert db.execute(select(func.count()).select_from(AuditEvent)).scalar() == n_audit == 0
    assert db.execute(select(func.count()).select_from(AuditOutbox)).scalar() == n_outbox == 0


# 11. Concurrent initialization converges to a single template.
def test_concurrent_initialization_converges(db):
    import app.bootstrap.workflow_defaults as wd

    real_find = wd._find_template
    calls = {"n": 0}

    def flaky_find(session):
        # First caller behaves as if it saw an empty DB even though the
        # second caller already committed: forces the IntegrityError race.
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_find(session)

    # Session B wins the race first.
    ensure_default_workflow_template(db)
    template_b = real_find(db)
    assert template_b is not None

    # Session A lost the race: its INSERT collides, it must converge.
    wd._find_template = flaky_find
    try:
        result = ensure_default_workflow_template(db)
    finally:
        wd._find_template = real_find
    assert result["status"] in ("ready", "recovered")
    _, n_templates, n_stages, _ = _counts(db)
    assert n_templates == 1
    assert n_stages == 5


def test_diverged_template_left_untouched(db):
    """A same-named template with foreign structure (e.g. legacy 14-stage
    manual seed) is never destroyed: warning + NO-OP."""
    template = WorkflowTemplate(name=TEMPLATE_NAME, description="legacy")
    db.add(template)
    db.flush()
    for pos in range(1, 15):
        db.add(WorkflowStage(template_id=template.id, name=f"Legacy stage {pos}",
                             order_index=pos))
    db.commit()
    result = ensure_default_workflow_template(db)
    assert result["status"] == "diverged"
    _, _, n_stages, _ = _counts(db)
    assert n_stages == 14
