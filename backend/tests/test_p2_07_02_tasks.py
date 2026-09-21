"""P2-07-02: компонент T — unit + DB тесты (workflow tasks/stages)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import University
from app.models.workflow import (
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTask,
    WorkflowTemplate,
    WorkflowTemplateStage,
)
from app.modules.health_score.tasks_score import calc_T, classify_overdue, score_tasks

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _mem_session() -> Session:
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return Session(eng)


def _workflow_graph(db: Session, uni_id):
    """Минимальный граф: template → stage → instance → instance_stage."""
    template = WorkflowTemplate(
        id=uuid4(), code="T-T", name="Шаблон T", created_by_keycloak_sub="t"
    )
    db.add(template)
    db.flush()
    tpl_stage = WorkflowTemplateStage(
        id=uuid4(), template_id=template.id, code="s1",
        name="Этап 1", order_index=0,
    )
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni_id,
        status="active", started_at=NOW - timedelta(days=30),
        created_by_keycloak_sub="t", updated_by_keycloak_sub="t",
    )
    db.add(instance)
    db.flush()
    inst_stage = WorkflowInstanceStage(
        id=uuid4(), instance_id=instance.id, template_stage_id=tpl_stage.id,
        order_index=0, status="current",
        due_date=NOW - timedelta(days=5),
    )
    db.add(inst_stage)
    db.flush()
    return instance, inst_stage


def _add_task(db, instance, stage=None, *, days_overdue=0, priority="normal",
              status="open"):
    due = NOW - timedelta(days=days_overdue) if days_overdue else NOW + timedelta(days=5)
    db.add(
        WorkflowTask(
            id=uuid4(), instance_id=instance.id,
            instance_stage_id=stage.id if stage is not None else None,
            title="Задача", due_date=due, status=status,
            priority=priority, created_by_keycloak_sub="t",
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


def test_calc_T_no_instances_is_100():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз T-0")
    db.add(uni)
    db.commit()
    assert calc_T(db, uni.id, NOW) == (100, 0, 0)
    db.close()


def test_calc_T_mixed_penalties():
    db = _mem_session()
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
    db.close()


def test_calc_T_overdue_stage_without_tasks_is_normal():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз T-2")
    db.add(uni)
    db.flush()
    _workflow_graph(db, uni.id)  # этап current, due 5 дней назад, задач нет
    db.commit()
    assert calc_T(db, uni.id, NOW) == (96, 0, 1)
    db.close()


def test_calc_T_done_tasks_ignored():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз T-3")
    db.add(uni)
    db.flush()
    instance, stage = _workflow_graph(db, uni.id)
    _add_task(db, instance, stage, days_overdue=30, status="done")
    db.commit()
    # done-задача не считается; у этапа есть задача → +0
    assert calc_T(db, uni.id, NOW) == (100, 0, 0)
    db.close()
