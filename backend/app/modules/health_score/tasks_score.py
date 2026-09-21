"""P2-07-02: компонент T — просроченные задачи (-8/-4, минимум 0).

Источник — канонический P2-пайплайн (``app.models.workflow``):
``workflow_instances → tasks`` + просроченные этапы без задач.

Классификация просрочки:
* **critical** (``-8``): ``days_overdue > 14`` ИЛИ ``priority == critical``;
* **normal** (``-4``): остальные просрочки, включая просроченные этапы
  (``pending/current/overdue`` с прошедшим ``due_date``), к которым не
  привязана ни одна задача.

Нет задач и просроченных этапов → ``100``. Скор не ниже ``0``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import WorkflowInstance, WorkflowInstanceStage, WorkflowTask

#: Просрочка дольше этого (в днях) считается критической.
CRITICAL_OVERDUE_DAYS = 14
#: Штраф за одну критическую просрочку.
PENALTY_CRITICAL = 8
#: Штраф за одну обычную просрочку.
PENALTY_NORMAL = 4

#: Приоритет задачи, сразу переводящий просрочку в критическую.
CRITICAL_PRIORITY = "critical"

#: Статусы этапов, считающихся «открытыми» для просрочки.
OPEN_STAGE_STATUSES: frozenset[str] = frozenset({"pending", "current", "overdue"})

__all__ = [
    "CRITICAL_OVERDUE_DAYS",
    "CRITICAL_PRIORITY",
    "OPEN_STAGE_STATUSES",
    "PENALTY_CRITICAL",
    "PENALTY_NORMAL",
    "TasksScore",
    "calc_T",
    "classify_overdue",
    "score_tasks",
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify_overdue(
    days_overdue: int, priority: str | None
) -> Literal["critical", "normal"]:
    """Классифицировать одну просрочку (чистая функция).

    Args:
        days_overdue: Полных дней просрочки (>= 1 для просрочки).
        priority: ``tasks.priority`` (``critical`` → сразу critical).

    Returns:
        ``"critical"`` если ``days_overdue > 14`` или приоритет critical,
        иначе ``"normal"``.
    """
    if days_overdue > CRITICAL_OVERDUE_DAYS or (priority or "").lower() == CRITICAL_PRIORITY:
        return "critical"
    return "normal"


def score_tasks(critical: int, normal: int) -> tuple[int, int, int]:
    """Посчитать T по счётчикам (чистая функция).

    Args:
        critical: Критических просрочек.
        normal: Обычных просрочек.

    Returns:
        ``(score, critical, normal)``; ``score = max(0, 100 - 8c - 4n)``.
    """
    score = 100 - critical * PENALTY_CRITICAL - normal * PENALTY_NORMAL
    return max(0, score), critical, normal


def calc_T(
    db: Session,
    university_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[int, int, int]:
    """Рассчитать компонент T для вуза (3 batched SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        now: Опорное время (по умолчанию ``datetime.now(timezone.utc)``).

    Returns:
        ``(score, critical_count, normal_count)`` — score 0–100.
    """
    now = now or datetime.now(timezone.utc)
    instance_ids = list(
        db.execute(
            select(WorkflowInstance.id).where(
                WorkflowInstance.university_id == university_id
            )
        ).scalars().all()
    )
    if not instance_ids:
        return 100, 0, 0

    task_rows = list(
        db.execute(
            select(
                WorkflowTask.status,
                WorkflowTask.due_date,
                WorkflowTask.priority,
                WorkflowTask.instance_stage_id,
            ).where(WorkflowTask.instance_id.in_(instance_ids))
        ).all()
    )
    critical = 0
    normal = 0
    stages_with_tasks: set[uuid.UUID] = set()
    for status, due_date, priority, stage_id in task_rows:
        if stage_id is not None:
            stages_with_tasks.add(stage_id)
        if (status or "") != "open" or due_date is None:
            continue
        days_overdue = (_as_utc(now) - _as_utc(due_date)).days
        if days_overdue < 1:
            continue
        if classify_overdue(days_overdue, priority) == "critical":
            critical += 1
        else:
            normal += 1

    stage_rows = list(
        db.execute(
            select(WorkflowInstanceStage.id).where(
                WorkflowInstanceStage.instance_id.in_(instance_ids),
                WorkflowInstanceStage.status.in_(sorted(OPEN_STAGE_STATUSES)),
                WorkflowInstanceStage.due_date.is_not(None),
                WorkflowInstanceStage.due_date < now,
            )
        ).scalars().all()
    )
    normal += sum(1 for stage_id in stage_rows if stage_id not in stages_with_tasks)
    return score_tasks(critical, normal)


class TasksScore(BaseModel):
    """Компонент T для Swagger/OpenAPI (используется в breakdown Health Score)."""

    score: int = Field(
        ge=0, le=100, description="100 минус штрафы за просрочки (-8 critical, -4 normal)",
        examples=[76],
    )
    critical_count: int = Field(
        ge=0, description="Критических просрочек (days>14 или priority=critical)",
        examples=[1],
    )
    normal_count: int = Field(
        ge=0, description="Обычных просрочек (включая этапы без задач)",
        examples=[4],
    )

    model_config = {"from_attributes": True}
