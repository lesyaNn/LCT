"""P2-07-06: компонент L — готовность запуска программ (только P1).

Источник — ``university_programs`` (P1-01-03): ``status`` + ``launch_date``.
Учитываются только ``planned/active/launched``; ``archived`` и прочие —
вне скоупа MVP (не штрафуют и не раздувают среднее).

Шкала программы (детерминированная, без AI):
* ``launched`` + ``launch_date <= today`` → ``100`` (запущена вовремя);
* ``launched`` + дата в будущем/пустая → ``70`` (странные данные, не критично);
* ``active`` + даты нет → ``70`` (готова, дата не назначена);
* ``active`` + ``launch_date < today`` → ``0`` (дата прошла, не запущена);
* ``active`` + ``0 <= days_to_launch <= 30`` → ``40`` (под риском);
* ``active`` + ``days_to_launch > 30`` → ``70`` (готова, дата впереди);
* ``planned`` → ``70`` (запланирована);
* прочее → ``0``.

``L = round(mean(скоры))``; ``ready`` — скоры ``>= 70``. Нет программ → ``100``.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interactions import UniversityProgram

#: Статусы university_programs, входящие в компонент L.
LAUNCH_RELEVANT_STATUSES: frozenset[str] = frozenset({"planned", "active", "launched"})

#: Порог «готовности» отдельной программы.
LAUNCH_READY_SCORE = 70

#: Окно риска запуска в днях (active + дата в ближайшие 30 дней → 40).
LAUNCH_RISK_WINDOW_DAYS = 30

__all__ = [
    "LAUNCH_READY_SCORE",
    "LAUNCH_RELEVANT_STATUSES",
    "LAUNCH_RISK_WINDOW_DAYS",
    "LaunchScore",
    "calc_L",
    "score_launch",
    "score_single_program",
]


def score_single_program(
    status: str,
    launch_date: date | None,
    today: date | None = None,
) -> int:
    """Скор одной программы по статусу и дате (чистая функция).

    Args:
        status: ``university_programs.status`` (сырая строка).
        launch_date: Плановая/фактическая дата запуска (может быть ``None``).
        today: Опорная дата (по умолчанию сегодня).

    Returns:
        Один из скоров ``100/70/40/0``.
    """
    today = today or date.today()
    normalized = (status or "").lower()
    if normalized == "launched":
        if launch_date is not None and launch_date > today:
            return 70
        return 100
    if normalized == "active":
        if launch_date is None:
            return 70
        days_to_launch = (launch_date - today).days
        if days_to_launch < 0:
            return 0
        if days_to_launch <= LAUNCH_RISK_WINDOW_DAYS:
            return 40
        return 70
    if normalized == "planned":
        return 70
    return 0


def score_launch(
    programs: list[tuple[str, date | None]],
    today: date | None = None,
) -> tuple[int, int, int]:
    """Посчитать L по списку ``(status, launch_date)`` (чистая функция).

    Args:
        programs: Уже отфильтрованные программы вуза.
        today: Опорная дата.

    Returns:
        ``(avg_score, total_programs, ready_count)``; пустой вход → ``(100, 0, 0)``.
    """
    today = today or date.today()
    total = len(programs)
    if total == 0:
        return 100, 0, 0
    scores = [score_single_program(status, launch, today) for status, launch in programs]
    avg_score = round(sum(scores) / total)
    ready = sum(1 for value in scores if value >= LAUNCH_READY_SCORE)
    return avg_score, total, ready


def calc_L(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
) -> tuple[int, int, int]:
    """Рассчитать компонент L для вуза (один SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата (по умолчанию сегодня).

    Returns:
        ``(avg_score, total_programs, ready_count)`` — avg 0–100.
    """
    today = today or date.today()
    rows = list(
        db.execute(
            select(UniversityProgram.status, UniversityProgram.launch_date).where(
                UniversityProgram.university_id == university_id,
                UniversityProgram.status.in_(sorted(LAUNCH_RELEVANT_STATUSES)),
            )
        ).all()
    )
    return score_launch([(status, launch) for status, launch in rows], today)


class LaunchScore(BaseModel):
    """Компонент L для Swagger/OpenAPI (используется в breakdown Health Score)."""

    score: int = Field(
        ge=0, le=100, description="Средняя готовность запуска программ, 0–100",
        examples=[70],
    )
    total_count: int = Field(
        ge=0, description="Всего активных программ (planned/active/launched)",
        examples=[3],
    )
    ready_count: int = Field(
        ge=0, description="Программ со скором >= 70",
        examples=[2],
    )

    model_config = {"from_attributes": True}
