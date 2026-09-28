"""Seed demo script tests (pure-unit, sqlite).

Covers: full creation on an empty DB, rerun idempotency (stable counts),
preservation of unrelated data, reuse of pre-existing demo entities,
partial-seed completion, no-op update behaviour, frozen workflow stages on
rerun, audit silence on rerun, and the production guard.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
import app.models.audit_outbox  # noqa: F401
import app.modules.audit.models  # noqa: F401
from app.db.base import Base
from app.models.audit_outbox import AuditOutbox
from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    Vendor,
)
from app.models.interactions import Meeting, UniversityProduct, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowStageTransition
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.audit.models import AuditEvent
from app.scripts.seed_demo import (
    DEMO_TEMPLATE_NAME,
    main,
    run_seed,
)


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    skip = {"instance_stages", "workflow_stages", "audit_events"}
    for name, table in Base.metadata.tables.items():
        if name not in skip:
            table.create(eng)
    with eng.begin() as conn:
        # workflow_stages / instance_stages DDL use DEFERRABLE INITIALLY
        # DEFERRED (PostgreSQL-only) — equivalents for sqlite unit tests.
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
        # audit_events.old/new_value are raw JSONB (PG-only) — JSON TEXT here.
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


def _demo_counts(session: Session) -> dict:
    def n(model, *filters):
        stmt = select(func.count()).select_from(model)
        for f in filters:
            stmt = stmt.where(f)
        return session.execute(stmt).scalar()

    return {
        "universities": n(University),
        "directions": n(ITDirection),
        "programs": n(ITProgram),
        "vendors": n(Vendor),
        "products": n(ITProduct),
        "responsibles": n(Responsible),
        "university_programs": n(UniversityProgram),
        "university_products": n(UniversityProduct),
        "contracts": n(Contract),
        "licenses": n(License),
        "templates": n(WorkflowTemplate),
        "stages": n(WorkflowStage),
        "instances": n(WorkflowInstance),
        "transitions": n(WorkflowStageTransition),
        "meetings": n(Meeting),
        "audit_events": n(AuditEvent),
        "audit_outbox": n(AuditOutbox),
    }


def _run(session: Session, **kwargs):
    stats = run_seed(session, **kwargs)
    session.commit()
    return stats


# 1. Empty DB: seed creates the full dataset.
def test_empty_db_creates_dataset(db: Session):
    stats = _run(db)
    counts = _demo_counts(db)

    assert counts["universities"] == 5
    assert counts["directions"] == 6
    assert counts["programs"] == 9
    assert counts["vendors"] == 5
    assert counts["products"] == 10
    assert counts["responsibles"] == 5
    assert counts["university_programs"] == 9
    assert counts["university_products"] == 10
    assert counts["contracts"] == 4
    assert counts["licenses"] == 4
    assert counts["templates"] == 1
    assert counts["stages"] == 5
    assert counts["instances"] == 5
    assert counts["meetings"] == 5
    assert stats.total_created > 0

    # Products always carry vendor + program + version.
    for prod in db.execute(select(ITProduct)).scalars().all():
        assert prod.vendor_id is not None
        assert prod.program_id is not None
        assert prod.version, prod.name

    # License ЛИЦ-ДЕМО-02 expires in ~20 days (expires_soon demo).
    lic2 = db.execute(
        select(License).where(License.license_number == "ЛИЦ-ДЕМО-02")
    ).scalar_one()
    assert (lic2.expires_at - date.today()).days == 20

    # Instances sit on their target stages.
    expected_stage = {
        "Поволжский технический университет": "Первичный контакт",
        "Московский технологический университет «Вектор»": "Согласование программы",
        "Университет цифровых технологий «Прогресс»": "Подготовка документов",
        "Северо-Западный университет информационных технологий": "Согласование договора",
        "Сибирский инженерный университет": "Согласование программы",
    }
    for uni_name, stage_name in expected_stage.items():
        uni = db.execute(select(University).where(University.name == uni_name)).scalar_one()
        template_id = db.execute(
            select(WorkflowTemplate.id).where(WorkflowTemplate.name == DEMO_TEMPLATE_NAME)
        ).scalar_one()
        inst = db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.university_id == uni.id,
                WorkflowInstance.template_id == template_id,
            )
        ).scalar_one()
        current = db.get(InstanceStage, inst.current_instance_stage_id)
        assert current.name == stage_name, (uni_name, current.name)


# 2-3. Second run: no duplicates, counts stable.
def test_second_run_is_noop(db: Session):
    _run(db)
    before = _demo_counts(db)
    stats2 = _run(db)
    after = _demo_counts(db)

    assert before == after
    assert stats2.total_created == 0
    assert stats2.transitions == 0


# 4. Existing unrelated data is not changed or deleted.
def test_unrelated_data_preserved(db: Session):
    db.add(University(name="Сторонний вуз", city="Томск"))
    db.add(ITDirection(code="OTHER-01", name="Стороннее направление"))
    db.add(Vendor(name="Сторонний вендор"))
    db.commit()

    _run(db)
    _run(db)

    assert db.execute(
        select(func.count()).select_from(University).where(University.name == "Сторонний вуз")
    ).scalar() == 1
    assert db.execute(
        select(func.count()).select_from(ITDirection).where(ITDirection.code == "OTHER-01")
    ).scalar() == 1
    assert db.execute(
        select(func.count()).select_from(Vendor).where(Vendor.name == "Сторонний вендор")
    ).scalar() == 1
    counts = _demo_counts(db)
    assert counts["universities"] == 6  # 5 demo + 1 unrelated


# 5. Pre-existing single demo entity is reused.
def test_existing_demo_direction_reused(db: Session):
    db.add(ITDirection(code="IB-DEMO", name="Информационная безопасность"))
    db.commit()
    _run(db)
    assert db.execute(
        select(func.count()).select_from(ITDirection).where(ITDirection.code == "IB-DEMO")
    ).scalar() == 1
    assert db.execute(select(func.count()).select_from(ITDirection)).scalar() == 6


# 6. Partially seeded DB: only missing objects are created.
def test_partial_seed_completes(db: Session):
    db.add(University(name="Московский технологический университет «Вектор»", city="Москва"))
    db.add(Vendor(name="TechNova"))
    db.commit()
    stats = _run(db)
    counts = _demo_counts(db)
    assert counts["universities"] == 5
    assert counts["vendors"] == 5
    assert counts["products"] == 10
    assert stats.existing["universities"] >= 1
    assert stats.existing["vendors"] >= 1


# 7. Existing demo product with correct data is not updated.
def test_existing_product_not_touched(db: Session):
    _run(db)
    prod = db.execute(
        select(ITProduct).where(ITProduct.name == "SecureGate", ITProduct.version == "5.4")
    ).scalar_one()
    before_updated = prod.updated_at
    db.commit()  # ensure timestamps are persisted before the rerun
    _run(db)
    db.refresh(prod)
    assert prod.version == "5.4"
    assert prod.updated_at == before_updated


# 8. Workflow second run does not transition past the target stage.
def test_workflow_rerun_no_extra_transitions(db: Session):
    _run(db)
    n_transitions = db.execute(select(func.count()).select_from(WorkflowStageTransition)).scalar()
    stats2 = _run(db)
    assert stats2.transitions == 0
    assert db.execute(select(func.count()).select_from(WorkflowStageTransition)).scalar() == n_transitions
    # Per university still exactly one demo instance.
    template_id = db.execute(
        select(WorkflowTemplate.id).where(WorkflowTemplate.name == DEMO_TEMPLATE_NAME)
    ).scalar_one()
    for uni in db.execute(select(University)).scalars().all():
        n = db.execute(
            select(func.count())
            .select_from(WorkflowInstance)
            .where(
                WorkflowInstance.university_id == uni.id,
                WorkflowInstance.template_id == template_id,
            )
        ).scalar()
        assert n == 1, uni.name


# 9. Audit second run creates no extra events.
def test_audit_quiet_on_rerun(db: Session):
    _run(db)
    events = db.execute(select(func.count()).select_from(AuditEvent)).scalar()
    outbox = db.execute(select(func.count()).select_from(AuditOutbox)).scalar()
    _run(db)
    assert db.execute(select(func.count()).select_from(AuditEvent)).scalar() == events
    assert db.execute(select(func.count()).select_from(AuditOutbox)).scalar() == outbox


# 10. Production guard: no flag -> no writes.
def test_production_guard_blocks_writes(db: Session, capsys, monkeypatch):
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SEED_DEMO_DATA=true" in out
    assert db.execute(select(func.count()).select_from(University)).scalar() == 0


def test_dry_run_writes_nothing(db: Session, capsys, monkeypatch):
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    stats = run_seed(db, dry_run=True)
    db.rollback()  # main() would roll back; mirror it here
    assert stats.total_created > 0  # it reports what WOULD be created
    assert db.execute(select(func.count()).select_from(University)).scalar() == 0
    assert db.execute(select(func.count()).select_from(WorkflowInstance)).scalar() == 0
