"""P2-07-04: компонент S — доля этапов, выполненных вовремя.

Источник — канонический B1-пайплайн: ``workflow_instances`` вуза со статусом
``active`` и их runtime-снапшоты ``instance_stages``.

Правила (детерминированные, без AI):
* нет активного instance → ``(100, 0, 0)`` (нейтрально, не штрафуем);
* в зачёт идут этапы ``due_date <= today`` ИЛИ уже ``completed``;
* ``completed`` без ``due_date`` → вовремя;
* ``completed`` с датами → вовремя если ``completed_at.date() <= due_date``;
* зачётных этапов нет → ``(100, 0, 0)``.

``score = round(100 * on_time / total)``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow_instances import InstanceStage, WorkflowInstance

#: Статус instance, считающийся активным для компонента S.
ACTIVE_INSTANCE_STATUS = "active"
#: Статус этапа «выполнен».
COMPLETED_STAGE_STATUS = "completed"

__all__ = [
    "ACTIVE_INSTANCE_STATUS",
    "COMPLETED_STAGE_STATUS",
    "StagesScore",
    "calc_S",
    "score_stages",
]


def _stage_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        current = value
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc).date()
    return value


def score_stages(
    stages: list[tuple[str, datetime | date | None, datetime | date | None]],
    today: date | None = None,
) -> tuple[int, int, int]:
    """Посчитать S по списку ``(status, due_date, completed_at)`` (чистая функция).

    Фильтрация «due или completed» — на вызывающей стороне (SQL); здесь только
    подсчёт вовремя выполненных.

    Args:
        stages: Этапы в зачёте.
        today: Опорная дата (для сигнатуры; вовремя определяется по датам
            завершения, не по today).

    Returns:
        ``(score, on_time_count, total_count)``; пустой вход → ``(100, 0, 0)``.
    """
    _ = today
    total = len(stages)
    if total == 0:
        return 100, 0, 0
    on_time = 0
    for status, due_date, completed_at in stages:
        if (status or "") != COMPLETED_STAGE_STATUS:
            continue
        due = _stage_date(due_date)
        done = _stage_date(completed_at)
        if due is None:
            on_time += 1  # нет дедлайна = вовремя
        elif done is not None and done <= due:
            on_time += 1
    return round(100 * on_time / total), on_time, total


def calc_S(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
) -> tuple[int, int, int]:
    """Рассчитать компонент S для вуза (2 batched SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата (по умолчанию сегодня).

    Returns:
        ``(score, on_time_count, total_count)`` — score 0–100.
    """
    today = today or date.today()
    instance_ids = list(
        db.execute(
            select(WorkflowInstance.id).where(
                WorkflowInstance.university_id == university_id,
                WorkflowInstance.status == ACTIVE_INSTANCE_STATUS,
            )
        ).scalars().all()
    )
    if not instance_ids:
        return 100, 0, 0
    rows = list(
        db.execute(
            select(
                InstanceStage.status,
                InstanceStage.due_date,
                InstanceStage.completed_at,
            ).where(
                InstanceStage.instance_id.in_(instance_ids),
            )
        ).all()
    )
    due_or_completed = [
        (status, due_date, completed_at)
        for status, due_date, completed_at in rows
        if (status or "") == COMPLETED_STAGE_STATUS
        or (due_date is not None and _stage_date(due_date) <= today)
    ]
    return score_stages(due_or_completed, today)


class StagesScore(BaseModel):
    """Компонент S для Swagger/OpenAPI (используется в breakdown Health Score)."""

    score: int = Field(
        ge=0, le=100, description="Доля этапов, выполненных вовремя, 0–100",
        examples=[80],
    )
    on_time_count: int = Field(
        ge=0, description="Этапов выполнено вовремя",
        examples=[4],
    )
    total_count: int = Field(
        ge=0, description="Всего этапов в зачёте (due или completed)",
        examples=[5],
    )

    model_config = {"from_attributes": True}
