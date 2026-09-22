"""P2-07-08: сборка итогового ответа Health Score.

``calculate_health_score`` — единая точка входа для endpoint'ов (P2-08-01/02/03),
снапшотов (P2-09-01) и моков (P2-12-01):

1. компоненты через ``aggregate.components_for_university`` (P2-07-01);
2. взвешенная сумма → ``score`` (clamp 0–100);
3. статус через ``get_health_status`` (P2-07-07);
4. reasons по счётчикам (коды совпадают с P2-10 attention items);
5. ``calculated_at = now(UTC)``.

Детерминирована: один вход = один результат (кроме ``calculated_at``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.modules.health_score.aggregate import aggregate_scores, components_for_university
from app.modules.health_score.schemas import (
    HealthScoreCounters,
    HealthScoreReason,
    HealthScoreResponse,
)
from app.modules.health_score.status import get_health_status

__all__ = ["build_reasons", "calculate_health_score"]


def build_reasons(counters: HealthScoreCounters) -> list[HealthScoreReason]:
    """Сгенерировать reasons по счётчикам (чистая функция).

    Args:
        counters: Счётчики входов формулы.

    Returns:
        Список причин; пуст, когда проблем нет.
    """
    reasons: list[HealthScoreReason] = []
    if counters.overdue_critical_tasks > 0:
        reasons.append(HealthScoreReason(
            code="OVERDUE_CRITICAL_TASKS", severity="high",
            text=f"{counters.overdue_critical_tasks} критически просроченных задач",
        ))
    if counters.overdue_normal_tasks > 0:
        reasons.append(HealthScoreReason(
            code="OVERDUE_TASKS", severity="medium",
            text=f"{counters.overdue_normal_tasks} просроченных задач",
        ))
    if counters.total_required_documents > 0 and counters.valid_documents < counters.total_required_documents:
        broken = counters.total_required_documents - counters.valid_documents
        reasons.append(HealthScoreReason(
            code="INVALID_DOCUMENTS", severity="high",
            text=f"{broken} из {counters.total_required_documents} обязательных документов недействительны",
        ))
    if counters.stages_due > 0 and counters.stages_on_time < counters.stages_due:
        late = counters.stages_due - counters.stages_on_time
        reasons.append(HealthScoreReason(
            code="OVERDUE_STAGES", severity="high",
            text=f"{late} из {counters.stages_due} этапов выполнены с просрочкой",
        ))
    if counters.teachers_required > 0 and counters.teachers_ready < counters.teachers_required:
        bad = counters.teachers_required - counters.teachers_ready
        reasons.append(HealthScoreReason(
            code="EXPIRED_CERTIFICATES", severity="high",
            text=f"{bad} из {counters.teachers_required} преподавателей имеют проблемы с сертификатами",
        ))
    if counters.active_programs > 0 and counters.programs_launched_on_time < counters.active_programs:
        bad = counters.active_programs - counters.programs_launched_on_time
        reasons.append(HealthScoreReason(
            code="LAUNCH_DELAYED", severity="medium",
            text=f"{bad} из {counters.active_programs} программ не запущены вовремя",
        ))
    return reasons


def calculate_health_score(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
    now: datetime | None = None,
) -> HealthScoreResponse:
    """Рассчитать полный Health Score вуза (single source of truth, §12 ТЗ).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата компонентов (по умолчанию сегодня).
        now: Опорное время (по умолчанию сейчас, UTC).

    Returns:
        Полный ``HealthScoreResponse`` (score/status/breakdown/reasons/counters).
    """
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    breakdown, counters = components_for_university(db, university_id, today, now)
    score = aggregate_scores(
        breakdown.tasks, breakdown.documents, breakdown.stages,
        breakdown.teachers, breakdown.launch,
    )
    return HealthScoreResponse(
        university_id=university_id,
        score=score,
        status=get_health_status(score),
        breakdown=breakdown,
        reasons=build_reasons(counters),
        calculated_at=now,
        input_counters=counters,
    )
