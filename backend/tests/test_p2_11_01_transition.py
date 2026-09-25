"""P2-11-01: B2 transition/comments/history/audit on the canonical pipeline.

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
database; canonical SQL migrations are the sole schema source, applied by
``tests/db_helpers.py``). Covers the frozen B2 contract:

* P2-03-02 ``validate_transition``: forward-only, optional skip, required
  blocks, comment required;
* P2-03-01 ``POST transition``: atomic pointer move + history + audit;
* P2-03-03 history rows: prev/new stage, actor, comment NOT NULL, timestamp;
* P2-03-04 ``WORKFLOW_TRANSITION`` audit event;
* P2-04-01 comments: create, author edit <= 15 min, stranger denied,
  expired window denied, admin override.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata)
from app.core.exceptions import BadTransition, Conflict
from app.models.catalog import University
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowComment,
    WorkflowInstance,
    WorkflowStageTransition,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.audit.models import AuditEvent
from app.models.audit_outbox import AuditOutbox
from app.modules.audit.relay import relay_audit_events
from app.modules.workflow_transitions import service
from app.modules.workflow_transitions.schemas import (
    WorkflowCommentCreate,
    WorkflowCommentUpdate,
)

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


def _graph(db: Session, *, middle_required: bool = False):
    """Template (3 stages) + university + instance with 3 snapshot rows."""
    uni = University(id=uuid4(), name="Вуз B2")
    db.add(uni)
    db.flush()
    template = WorkflowTemplate(id=uuid4(), name="Маршрут B2")
    db.add(template)
    db.flush()
    stages = []
    for order, (name, required) in enumerate(
        [("Контакты", True), ("Встреча", middle_required), ("Договор", True)],
        start=1,
    ):
        stages.append(
            WorkflowStage(
                id=uuid4(), template_id=template.id, name=name,
                order_index=order, is_required=required,
            )
        )
    db.add_all(stages)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), university_id=uni.id, template_id=template.id,
        status="active",
    )
    db.add(instance)
    db.flush()
    rows = [
        InstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=stages[0].id, order_index=1,
            name="Контакты", is_required=True, status="pending",
        ),
        InstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=stages[1].id, order_index=2,
            name="Встреча", is_required=middle_required, status="pending",
        ),
        InstanceStage(
            id=uuid4(), instance_id=instance.id,
            template_stage_id=stages[2].id, order_index=3,
            name="Договор", is_required=True, status="pending",
        ),
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


# ------------------------------------------------------- P2-03-01/02/03/04

def test_transition_skips_optional_records_history_and_audit(db):
    instance, rows, stages = _graph(db)
    moved = service.transition_instance(
        db, instance.id, rows[2].id, "идём дальше", "actor-1"
    )
    assert moved.current_instance_stage_id == rows[2].id
    assert moved.current_stage_id == stages[2].id

    db.expire_all()
    by_order = {r.order_index: r for r in db.execute(
        select(InstanceStage).where(InstanceStage.instance_id == instance.id)
    ).scalars()}
    assert by_order[1].status == "completed"
    assert by_order[1].completed_at is not None
    assert by_order[2].status == "skipped"
    assert by_order[3].status == "pending"

    history = service.list_transitions(db, instance.id)
    assert len(history) == 2  # creation + this move
    last = history[-1]
    assert last.from_stage_id == stages[0].id
    assert last.to_stage_id == stages[2].id
    assert last.actor_keycloak_sub == "actor-1"
    assert last.comment == "идём дальше"
    assert last.created_at is not None

    pending = list(db.execute(select(AuditOutbox).where(
        AuditOutbox.aggregate_id == instance.id,
        AuditOutbox.event_type == "WORKFLOW_TRANSITION",
    )).scalars())
    assert len(pending) == 1
    assert db.execute(select(AuditEvent).where(
        AuditEvent.entity_id == instance.id,
        AuditEvent.action == "WORKFLOW_TRANSITION",
    )).scalars().all() == []
    assert relay_audit_events(db) == 1
    events = db.execute(select(AuditEvent).where(
        AuditEvent.entity_id == instance.id,
        AuditEvent.action == "WORKFLOW_TRANSITION",
    )).scalars().all()
    assert len(events) == 1
    assert events[0].user_id == "actor-1"
    assert events[0].university_id == moved.university_id


def test_transition_blocked_by_required_stage(db):
    instance, rows, _ = _graph(db, middle_required=True)
    with pytest.raises(BadTransition, match="Required stages"):
        service.transition_instance(db, instance.id, rows[2].id, "прыжок", "a")
    db.rollback()
    # Atomicity: nothing changed.
    assert service.list_transitions(db, instance.id).__len__() == 1
    fresh = service.get_instance_or_404(db, instance.id)
    assert fresh.current_instance_stage_id == rows[0].id


def test_transition_backward_and_empty_comment_denied(db):
    instance, rows, _ = _graph(db)
    service.transition_instance(db, instance.id, rows[1].id, "шаг", "a")
    with pytest.raises(BadTransition, match="forward"):
        service.transition_instance(db, instance.id, rows[0].id, "назад", "a")
    with pytest.raises(BadTransition, match="comment"):
        service.transition_instance(db, instance.id, rows[2].id, "   ", "a")
    db.rollback()


# ---------------------------------------------------------------- P2-04-01

def test_comments_create_edit_windows(db):
    instance, rows, stages = _graph(db)
    comment = service.add_comment(
        db, instance.id,
        WorkflowCommentCreate(content="  первый  ", stage_id=stages[0].id),
        "author-1",
    )
    assert comment.content == "первый"
    assert comment.author_keycloak_sub == "author-1"

    edited = service.edit_comment(
        db, comment.id, WorkflowCommentUpdate(content="правка"),
        "author-1", {"manager"},
    )
    assert edited.content == "правка"

    with pytest.raises(BadTransition, match="author or an admin"):
        service.edit_comment(
            db, comment.id, WorkflowCommentUpdate(content="чужой"),
            "stranger", {"manager"},
        )
    db.rollback()

    # Expired author window.
    stale = service.add_comment(
        db, instance.id, WorkflowCommentCreate(content="старый"), "author-1"
    )
    stale.created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db.commit()
    with pytest.raises(Conflict, match="expired"):
        service.edit_comment(
            db, stale.id, WorkflowCommentUpdate(content="поздно"),
            "author-1", {"manager"},
        )
    db.rollback()

    # Admin override after the window.
    done = service.edit_comment(
        db, stale.id, WorkflowCommentUpdate(content="админ"),
        "boss", {"admin"},
    )
    assert done.content == "админ"

    listed = service.list_comments(db, instance.id)
    # Oldest first: the backdated comment sorts before the newer one.
    assert [c.content for c in listed] == ["админ", "правка"]
    assert all(isinstance(c, WorkflowComment) for c in listed)
