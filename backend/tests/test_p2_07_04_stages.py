"""P2-07-04: компонент S — unit + DB тесты (workflow stages)."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.models.catalog import University
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate, WorkflowStage
from app.modules.health_score.stages_score import calc_S, score_stages

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    """PostgreSQL integration DB (canonical SQL migrations; skips w/o PG)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _graph(db: Session, uni_id, *, instance_status="active"):
    template = WorkflowTemplate(id=uuid4(), name="Шаблон S")
    db.add(template)
    db.flush()
    tpl_stage = WorkflowStage(
        id=uuid4(), template_id=template.id,
        name="Этап 0", order_index=1,
    )
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni_id,
        status=instance_status,
    )
    db.add(instance)
    db.flush()
    return instance, tpl_stage


def _add_stage(db, instance, template_id, name, order, *, status, due=None, completed=None):
    tpl_stage = WorkflowStage(
        id=uuid4(), template_id=template_id,
        name=f"Этап {name}", order_index=order,
    )
    db.add(tpl_stage)
    db.flush()
    db.add(
        InstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=tpl_stage.id, order_index=order,
            name=f"Этап {name}",
            status=status, due_date=due, completed_at=completed,
        )
    )
    db.flush()


def test_score_stages_empty_is_100():
    assert score_stages([], TODAY) == (100, 0, 0)


def test_score_stages_on_time_rules():
    stages = [
        ("completed", NOW - timedelta(days=5), NOW - timedelta(days=6)),  # вовремя
        ("completed", NOW - timedelta(days=5), NOW - timedelta(days=1)),  # поздно
        ("completed", None, NOW),  # нет дедлайна = вовремя
        ("current", NOW - timedelta(days=5), None),  # не completed
    ]
    assert score_stages(stages, TODAY) == (50, 2, 4)


def test_calc_S_no_instance_is_100(db):
    uni = University(id=uuid4(), name="Вуз S-0")
    db.add(uni)
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (100, 0, 0)


def test_calc_S_counts_due_or_completed_only(db):
    uni = University(id=uuid4(), name="Вуз S-1")
    db.add(uni)
    db.flush()
    instance, tpl_stage = _graph(db, uni.id)
    template_id = tpl_stage.template_id
    _add_stage(db, instance, template_id, "s1", 2, status="completed",
               due=(NOW - timedelta(days=5)).date(),
               completed=NOW - timedelta(days=6))
    _add_stage(db, instance, template_id, "s2", 3, status="pending",
               due=(NOW - timedelta(days=2)).date())  # due, не completed
    _add_stage(db, instance, template_id, "s3", 4, status="pending",
               due=(NOW + timedelta(days=10)).date())  # будущее, вне зачёта
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (50, 1, 2)


def test_calc_S_completed_instance_ignored(db):
    uni = University(id=uuid4(), name="Вуз S-2")
    db.add(uni)
    db.flush()
    _graph(db, uni.id, instance_status="completed")
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (100, 0, 0)
