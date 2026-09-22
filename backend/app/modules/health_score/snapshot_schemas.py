"""P2-09-01: Pydantic-схемы снапшотов Health Score (Swagger-документация).

Endpoint ``GET /universities/{id}/health-score/history`` отдаёт эти схемы:
контракт истории виден в OpenAPI и переиспользуется cron/event-писателями
без расхождений.

Связь с моделью: ``app.models.health_score.HealthScoreSnapshot`` (таблица
``health_score_snapshots``, миграция ``000015`` / Alembic ``b2c909010901``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SnapshotTrigger = Literal["daily_cron", "transition", "document_update"]


class HealthScoreSnapshotOut(BaseModel):
    """Снапшот Health Score вуза (элемент истории для графика динамики).

    Возвращается ``GET /universities/{id}/health-score/history``.
    ``breakdown``/``reasons`` — копии ответа на момент ``calculated_at``.
    """

    id: uuid.UUID = Field(description="UUID снапшота", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    university_id: uuid.UUID = Field(description="UUID вуза", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    score: int = Field(ge=0, le=100, description="Health Score 0–100 на момент снапшота", examples=[78])
    status: Literal["green", "yellow", "red"] = Field(
        description="Статус: green (85–100), yellow (60–84), red (0–59)",
        examples=["yellow"],
    )
    breakdown: dict[str, Any] = Field(
        default_factory=dict,
        description="Копия breakdown (tasks/documents/stages/teachers/launch)",
        examples=[{"tasks": 90, "documents": 75, "stages": 80, "teachers": 67, "launch": 70}],
    )
    reasons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Копия reasons (code/severity/text)",
        examples=[[{"code": "INVALID_DOCUMENTS", "severity": "high", "text": "1 из 4 документов недействительны"}]],
    )
    calculated_at: datetime = Field(
        description="Момент расчёта (UTC, tz-aware)", examples=["2026-09-20T00:00:00Z"]
    )
    period_day: date = Field(
        description="Календарный день снапшота (calculated_at::date, идемпотентность cron)",
        examples=["2026-09-20"],
    )
    trigger_event: str = Field(
        description="Триггер: daily_cron | transition | document_update",
        examples=["daily_cron"],
    )

    model_config = {"from_attributes": True}


class HealthScoreHistoryQuery(BaseModel):
    """Query-параметры ``GET .../health-score/history`` (Swagger)."""

    days: int = Field(
        default=30, ge=1, le=365, description="Глубина истории в днях", examples=[30]
    )
    trigger_event: SnapshotTrigger | None = Field(
        default=None,
        description="Фильтр по триггеру (по умолчанию — все)",
        examples=["daily_cron"],
    )

    model_config = {"from_attributes": True}


__all__ = [
    "HealthScoreHistoryQuery",
    "HealthScoreSnapshotOut",
    "SnapshotTrigger",
]
