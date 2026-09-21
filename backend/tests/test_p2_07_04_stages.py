"""P2-07-04: компонент S — unit + DB тесты (workflow stages)."""

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
    WorkflowTemplate,
    WorkflowTemplateStage,
)
from app.modules.health_score.stages_score import calc_S, score_stages

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def _mem_session() -> Session:
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return Session(eng)


def _graph(db: Session, uni_id, *, instance_status="active"):
    template = WorkflowTemplate(
        id=uuid4(), code="T-S", name="Шаблон S", created_by_keycloak_sub="t"
    )
    db.add(template)
    db.flush()
    tpl_stage = WorkflowTemplateStage(
        id=uuid4(), template_id=template.id, code="s0",
        name="Этап 0", order_index=0,
    )
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni_id,
        status=instance_status, started_at=NOW - timedelta(days=30),
        created_by_keycloak_sub="t", updated_by_keycloak_sub="t",
    )
    db.add(instance)
    db.flush()
    return instance, tpl_stage


def _add_stage(db, instance, template_id, code, order, *, status, due=None, completed=None):
    tpl_stage = WorkflowTemplateStage(
        id=uuid4(), template_id=template_id, code=code,
        name=f"Этап {code}", order_index=order,
    )
    db.add(tpl_stage)
    db.flush()
    db.add(
        WorkflowInstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=tpl_stage.id, order_index=0,
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


def test_calc_S_no_instance_is_100():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз S-0")
    db.add(uni)
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (100, 0, 0)
    db.close()


def test_calc_S_counts_due_or_completed_only():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз S-1")
    db.add(uni)
    db.flush()
    instance, tpl_stage = _graph(db, uni.id)
    template_id = tpl_stage.template_id
    _add_stage(db, instance, template_id, "s1", 1, status="completed",
               due=NOW - timedelta(days=5), completed=NOW - timedelta(days=6))
    _add_stage(db, instance, template_id, "s2", 2, status="current",
               due=NOW - timedelta(days=2))  # due, не completed
    _add_stage(db, instance, template_id, "s3", 3, status="pending",
               due=NOW + timedelta(days=10))  # будущее, вне зачёта
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (50, 1, 2)
    db.close()


def test_calc_S_completed_instance_ignored():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз S-2")
    db.add(uni)
    db.flush()
    _graph(db, uni.id, instance_status="completed")
    db.commit()
    assert calc_S(db, uni.id, TODAY) == (100, 0, 0)
    db.close()
