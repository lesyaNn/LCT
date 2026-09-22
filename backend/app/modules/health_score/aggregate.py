"""P2-07-01: взвешенная формула Health Score (T*0.25 + D*0.20 + S*0.20 + E*0.20 + L*0.15).

Чистая математика + оркестрация компонентов. Причины (reasons) и финальный
``HealthScoreResponse`` собирает P2-07-08 (``health_service``) — здесь только
веса, ``aggregate_scores`` и ``components_for_university``.

Формула детерминирована: одни входные данные = один результат. Никакого AI/ML.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.modules.health_score.documents_score import calc_D
from app.modules.health_score.educators_score import calc_E
from app.modules.health_score.launch_score import calc_L
from app.modules.health_score.schemas import HealthScoreBreakdown, HealthScoreCounters
from app.modules.health_score.stages_score import calc_S
from app.modules.health_score.tasks_score import calc_T

#: Замороженные веса компонентов (сумма = 1.0; меняются только с контрактом).
WEIGHTS: dict[str, float] = {
    "tasks": 0.25,
    "documents": 0.20,
    "stages": 0.20,
    "teachers": 0.20,
    "launch": 0.15,
}

__all__ = [
    "WEIGHTS",
    "aggregate_scores",
    "components_for_university",
]


def aggregate_scores(
    tasks: int, documents: int, stages: int, teachers: int, launch: int
) -> int:
    """Взвешенная сумма компонентов → итог 0–100 (чистая функция).

    Args:
        tasks: Скор T 0–100.
        documents: Скор D 0–100.
        stages: Скор S 0–100.
        teachers: Скор E 0–100.
        launch: Скор L 0–100.

    Returns:
        ``round(T*0.25 + D*0.20 + S*0.20 + E*0.20 + L*0.15)``, clamp 0–100.
    """
    raw = (
        tasks * WEIGHTS["tasks"]
        + documents * WEIGHTS["documents"]
        + stages * WEIGHTS["stages"]
        + teachers * WEIGHTS["teachers"]
        + launch * WEIGHTS["launch"]
    )
    return max(0, min(100, round(raw)))


def components_for_university(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
    now: datetime | None = None,
) -> tuple[HealthScoreBreakdown, HealthScoreCounters]:
    """Рассчитать все 5 компонентов + breakdown/counters (без reasons/status).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата для D/S/E/L (по умолчанию сегодня).
        now: Опорное время для T (по умолчанию сейчас, UTC).

    Returns:
        ``(breakdown, counters)`` — вход для ``health_service`` (P2-07-08).
    """
    t_score, t_crit, t_norm = calc_T(db, university_id, now)
    d_score, d_valid, d_total = calc_D(db, university_id, today)
    s_score, s_on_time, s_total = calc_S(db, university_id, today)
    e_score, e_ready, e_total = calc_E(db, university_id, today)
    l_score, l_total, l_ready = calc_L(db, university_id, today)
    breakdown = HealthScoreBreakdown(
        tasks=t_score,
        documents=d_score,
        stages=s_score,
        teachers=e_score,
        launch=l_score,
    )
    counters = HealthScoreCounters(
        overdue_critical_tasks=t_crit,
        overdue_normal_tasks=t_norm,
        total_required_documents=d_total,
        valid_documents=d_valid,
        stages_due=s_total,
        stages_on_time=s_on_time,
        teachers_required=e_total,
        teachers_ready=e_ready,
        active_programs=l_total,
        programs_launched_on_time=l_ready,
        programs_at_risk=l_total - l_ready,
    )
    return breakdown, counters
