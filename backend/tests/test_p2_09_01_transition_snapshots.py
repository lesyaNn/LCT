"""P2-09-01 (WRITE-path): transition hook stores a health snapshot.

``transition_instance`` writes one ``transition`` snapshot per
university/day (first wins on the unique conflict) and never fails the
transition itself. DB integration tests require PostgreSQL via
``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata on Base)
from app.models.catalog import University
from app.models.health_score import TRIGGER_TRANSITION, HealthScoreSnapshot
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowStageTransition,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.health_score.snapshots import write_transition_snapshot
from app.modules.workflow_transitions import service

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _graph(db: Session):
    uni = University(id=uuid4(), name="Вуз snapshots")
    db.add(uni)
    db.flush()
    template = WorkflowTemplate(id=uuid4(), name="Маршрут snapshots")
    db.add(template)
    db.flush()
    stages = [
        WorkflowStage(
            id=uuid4(), template_id=template.id, name=name,
            order_index=order, is_required=required,
        )
        for order, (name, required) in
        enumerate([("Контакты", True), ("Встреча", False), ("Договор", True)], start=1)
    ]
    db.add_all(stages)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), university_id=uni.id, template_id=template.id, status="active"
    )
    db.add(instance)
    db.flush()
    rows = [
        InstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=st.id, order_index=st.order_index,
            name=st.name, is_required=st.is_required, status="pending",
        )
        for st in stages
    ]
    db.add_all(rows)
    db.flush()
    instance.current_instance_stage_id = rows[0].id
    instance.current_stage_id = stages[0].id
    db.add(
        WorkflowStageTransition(
            id=uuid4(), instance_id=instance.id,
            from_stage_id=None, to_stage_id=stages[0].id,
            actor_keycloak_sub="tester", comment="",
        )
    )
    db.commit()
    return instance, rows, stages


def _snapshots(db: Session, university_id):
    return list(
        db.execute(
            select(HealthScoreSnapshot).where(
                HealthScoreSnapshot.university_id == university_id
            )
        )
        .scalars()
        .all()
    )


def test_transition_writes_snapshot(db: Session):
    instance, rows, _stages = _graph(db)
    assert _snapshots(db, instance.university_id) == []
    service.transition_instance(db, instance.id, rows[2].id, "идём дальше", "actor-1")
    snaps = _snapshots(db, instance.university_id)
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.trigger_event == TRIGGER_TRANSITION
    assert 0 <= snap.score <= 100
    assert snap.status in ("green", "yellow", "red")
    assert snap.period_day == snap.calculated_at.date()
    assert isinstance(snap.breakdown, dict) and isinstance(snap.reasons, list)


def test_second_transition_same_day_keeps_first_snapshot(db: Session):
    instance, rows, _stages = _graph(db)
    service.transition_instance(db, instance.id, rows[1].id, "шаг 1", "actor-1")
    first = _snapshots(db, instance.university_id)
    assert len(first) == 1
    # second transition the same day: no duplicate, no error
    service.transition_instance(db, instance.id, rows[2].id, "шаг 2", "actor-1")
    again = _snapshots(db, instance.university_id)
    assert len(again) == 1
    assert again[0].id == first[0].id


def test_writer_failure_never_breaks_transition(db: Session, monkeypatch):
    import app.modules.health_score.snapshots as snapshots

    instance, rows, _stages = _graph(db)
    monkeypatch.setattr(
        snapshots, "write_transition_snapshot",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("writer down")),
    )
    moved = service.transition_instance(db, instance.id, rows[2].id, "идём", "actor-1")
    assert moved.current_instance_stage_id == rows[2].id


def test_direct_writer_returns_false_on_conflict(db: Session):
    instance, _rows, _stages = _graph(db)
    assert write_transition_snapshot(db, instance.university_id) is True
    assert write_transition_snapshot(db, instance.university_id) is False
    assert len(_snapshots(db, instance.university_id)) == 1
