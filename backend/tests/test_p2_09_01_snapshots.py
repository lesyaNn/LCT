"""P2-09-01: snapshots — модель, уникальность, SQL-DDL паритет (PostgreSQL)."""

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import University
from app.models.health_score import HealthScoreSnapshot
from app.modules.health_score.snapshot_schemas import HealthScoreSnapshotOut

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


def test_table_registered_on_canonical_metadata():
    assert "health_score_snapshots" in Base.metadata.tables
    table = Base.metadata.tables["health_score_snapshots"]
    assert "uq_health_snapshots_uni_day_trigger" in {c.name for c in table.constraints}
    index_names = {i.name for i in table.indexes}
    assert "ix_health_snapshots_university_id" in index_names
    assert "ix_health_snapshots_univ_calculated" in index_names


def test_insert_and_unique_uni_day_trigger(db):
    uni = University(id=uuid4(), name="Вуз S-1")
    db.add(uni)
    db.commit()
    now = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
    first = HealthScoreSnapshot(
        id=uuid4(), university_id=uni.id, score=78, status="yellow",
        breakdown={"tasks": 90}, reasons=[],
        calculated_at=now, period_day=date(2026, 9, 20),
        trigger_event="daily_cron",
    )
    db.add(first)
    db.commit()

    # Тот же (uni, day, trigger) → IntegrityError (cron делает ON CONFLICT DO NOTHING).
    db.add(
        HealthScoreSnapshot(
            id=uuid4(), university_id=uni.id, score=80, status="yellow",
            breakdown={}, reasons=[],
            calculated_at=now, period_day=date(2026, 9, 20),
            trigger_event="daily_cron",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Другой триггер в тот же день — ок (event-снапшоты не конфликтуют с дневными).
    db.add(
        HealthScoreSnapshot(
            id=uuid4(), university_id=uni.id, score=81, status="yellow",
            breakdown={}, reasons=[],
            calculated_at=now, period_day=date(2026, 9, 20),
            trigger_event="transition",
        )
    )
    db.commit()
    assert db.query(HealthScoreSnapshot).count() == 2


def test_cascade_on_university_delete(db):
    uni = University(id=uuid4(), name="Вуз S-2")
    db.add(uni)
    db.commit()
    now = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
    db.add(
        HealthScoreSnapshot(
            id=uuid4(), university_id=uni.id, score=90, status="green",
            breakdown={}, reasons=[],
            calculated_at=now, period_day=date(2026, 9, 20),
            trigger_event="daily_cron",
        )
    )
    db.commit()
    db.delete(uni)
    db.commit()
    assert db.query(HealthScoreSnapshot).count() == 0


def test_swagger_schema_serializes():
    snap = HealthScoreSnapshotOut(
        id=uuid4(), university_id=uuid4(), score=78, status="yellow",
        breakdown={"tasks": 90}, reasons=[],
        calculated_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        period_day=date(2026, 9, 20), trigger_event="daily_cron",
    )
    dumped = snap.model_dump(mode="json")
    assert dumped["score"] == 78
    assert dumped["status"] == "yellow"
    # OpenAPI-метаданные для Swagger присутствуют.
    fields = HealthScoreSnapshotOut.model_fields
    assert fields["status"].description is not None
    assert fields["period_day"].description is not None
