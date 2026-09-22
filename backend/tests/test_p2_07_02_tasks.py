"""P2-07-02: компонент T — unit + DB тесты (workflow tasks/stages)."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.models.catalog import University
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowTemplate, WorkflowStage
from app.modules.health_score.tasks_score import calc_T, classify_overdue, score_tasks

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


def _workflow_graph(db: Session, uni_id):
    """Минимальный граф: template → stage → instance → instance_stage."""
    template = WorkflowTemplate(id=uuid4(), name="Шаблон T")
    db.add(template)
    db.flush()
    tpl_stage = WorkflowStage(
        id=uuid4(), template_id=template.id,
        name="Этап 1", order_index=1,
    )
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni_id,
        status="active",
    )
    db.add(instance)
    db.flush()
    inst_stage = InstanceStage(
        id=uuid4(), instance_id=instance.id, template_stage_id=tpl_stage.id,
        order_index=1, name="Этап 1", status="pending",
        due_date=(NOW - timedelta(days=5)).date(),
    )
    db.add(inst_stage)
    db.flush()
    return instance, tpl_stage


def _add_task(db, instance, stage=None, *, days_overdue=0, priority="normal",
              status="open"):
    due = TODAY - timedelta(days=days_overdue) if days_overdue else TODAY + timedelta(days=5)
    db.add(
        WorkflowTask(
            id=uuid4(), instance_id=instance.id,
            stage_id=stage.id if stage is not None else None,
            title="Задача", deadline=due, status=status,
            priority=priority,
        )
    )
    db.flush()


def test_classify_overdue():
    assert classify_overdue(15, "normal") == "critical"
    assert classify_overdue(5, "critical") == "critical"
    assert classify_overdue(5, "normal") == "normal"
    assert classify_overdue(14, "normal") == "normal"


def test_score_tasks_floor_zero():
    assert score_tasks(0, 0) == (100, 0, 0)
    assert score_tasks(1, 1) == (88, 1, 1)
    assert score_tasks(20, 20) == (0, 20, 20)


def test_calc_T_no_instances_is_100(db):
    uni = University(id=uuid4(), name="Вуз T-0")
    db.add(uni)
    db.commit()
    assert calc_T(db, uni.id, NOW) == (100, 0, 0)


def test_calc_T_mixed_penalties(db):
    uni = University(id=uuid4(), name="Вуз T-1")
    db.add(uni)
    db.flush()
    instance, stage = _workflow_graph(db, uni.id)
    _add_task(db, instance, stage, days_overdue=20, priority="normal")  # critical (-8)
    _add_task(db, instance, stage, days_overdue=3, priority="critical")  # critical (-8)
    _add_task(db, instance, stage, days_overdue=3, priority="normal")  # normal (-4)
    _add_task(db, instance, stage, days_overdue=0, priority="normal")  # не просрочена
    db.commit()
    assert calc_T(db, uni.id, NOW) == (80, 2, 1)


def test_calc_T_overdue_stage_without_tasks_is_normal(db):
    uni = University(id=uuid4(), name="Вуз T-2")
    db.add(uni)
    db.flush()
    _workflow_graph(db, uni.id)  # этап pending, due 5 дней назад, задач нет
    db.commit()
    assert calc_T(db, uni.id, NOW) == (96, 0, 1)


def test_calc_T_done_tasks_ignored(db):
    uni = University(id=uuid4(), name="Вуз T-3")
    db.add(uni)
    db.flush()
    instance, stage = _workflow_graph(db, uni.id)
    _add_task(db, instance, stage, days_overdue=30, status="done")
    db.commit()
    # done-задача не считается; у этапа есть задача → +0
    assert calc_T(db, uni.id, NOW) == (100, 0, 0)
