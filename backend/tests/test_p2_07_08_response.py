"""P2-07-08: сборка ответа — unit тесты (reasons + response)."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import University
from app.modules.health_score.health_service import build_reasons, calculate_health_score
from app.modules.health_score.schemas import HealthScoreCounters

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _mem_db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def test_build_reasons_empty_when_healthy():
    assert build_reasons(HealthScoreCounters()) == []


def test_build_reasons_codes():
    reasons = build_reasons(HealthScoreCounters(
        overdue_critical_tasks=1, overdue_normal_tasks=2,
        total_required_documents=4, valid_documents=2,
        stages_due=5, stages_on_time=3,
        teachers_required=4, teachers_ready=1,
        active_programs=3, programs_launched_on_time=1, programs_at_risk=2,
    ))
    codes = [r.code for r in reasons]
    assert codes == [
        "OVERDUE_CRITICAL_TASKS", "OVERDUE_TASKS", "INVALID_DOCUMENTS",
        "OVERDUE_STAGES", "EXPIRED_CERTIFICATES", "LAUNCH_DELAYED",
    ]
    assert reasons[0].severity == "high"
    assert reasons[1].severity == "medium"


def test_calculate_empty_university_is_green_100():
    eng = _mem_db()
    with Session(eng) as db:
        uni = University(id=uuid4(), name="Вуз H-0")
        db.add(uni)
        db.commit()
        resp = calculate_health_score(db, uni.id, NOW.date(), NOW)
    assert resp.score == 100
    assert resp.status == "green"
    assert resp.reasons == []
    assert resp.calculated_at == NOW
    assert resp.breakdown.tasks == 100
    eng.dispose()


def test_calculate_deterministic_same_input():
    eng = _mem_db()
    with Session(eng) as db:
        uni = University(id=uuid4(), name="Вуз H-1")
        db.add(uni)
        db.commit()
        first = calculate_health_score(db, uni.id, NOW.date(), NOW).model_dump(mode="json")
        second = calculate_health_score(db, uni.id, NOW.date(), NOW).model_dump(mode="json")
    assert first == second
    eng.dispose()
