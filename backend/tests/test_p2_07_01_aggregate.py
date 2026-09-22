"""P2-07-01: формула и оркестрация — unit тесты."""

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.modules.health_score.aggregate import (
    WEIGHTS,
    aggregate_scores,
    components_for_university,
)
from app.modules.health_score.schemas import HealthScoreResponse

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


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    assert set(WEIGHTS) == {"tasks", "documents", "stages", "teachers", "launch"}


def test_aggregate_all_100():
    assert aggregate_scores(100, 100, 100, 100, 100) == 100


def test_aggregate_all_0():
    assert aggregate_scores(0, 0, 0, 0, 0) == 0


def test_aggregate_single_component_100():
    # Только T=100, остальные 0 → 25
    assert aggregate_scores(100, 0, 0, 0, 0) == 25
    assert aggregate_scores(0, 0, 0, 0, 100) == 15


def test_aggregate_rounding_and_example():
    # Пример из контракта: 65/100/70/85/80 → 16.25+20+14+17+12 = 79.25 → 79
    assert aggregate_scores(65, 100, 70, 85, 80) == 79


def test_response_schema_round_trip():
    resp = HealthScoreResponse(
        university_id=uuid4(), score=79, status="yellow",
        breakdown={"tasks": 65, "documents": 100, "stages": 70, "teachers": 85, "launch": 80},
        reasons=[{"code": "OVERDUE_TASKS", "severity": "high", "text": "3 просрочки"}],
        calculated_at="2026-09-20T12:00:00Z",
        input_counters={"overdue_normal_tasks": 3},
    )
    assert resp.score == 79
    assert resp.status == "yellow"
    assert resp.model_dump(mode="json")["breakdown"]["tasks"] == 65


def test_components_for_university_empty_db(db):
    """Пустой вуз (PostgreSQL): все компоненты нейтральны, счётчики нулевые."""
    import app.models  # noqa: F401 (register metadata)
    from app.models.catalog import University
    from uuid import uuid4

    uni = University(id=uuid4(), name="Вуз A-0")
    db.add(uni)
    db.commit()
    breakdown, counters = components_for_university(db, uni.id)
    assert (breakdown.tasks, breakdown.documents, breakdown.stages,
            breakdown.teachers, breakdown.launch) == (100, 100, 100, 100, 100)
    assert aggregate_scores(100, 100, 100, 100, 100) == 100
    assert counters.overdue_critical_tasks == 0
    assert counters.total_required_documents == 0
