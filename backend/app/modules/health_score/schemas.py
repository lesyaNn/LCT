"""P2-07-01/07-08: общие DTO Health Score (замороженный контракт для Swagger).

Single source of truth для ответа ``GET .../health-score`` (P2-08-01),
batch (P2-08-02), ranking (P2-08-03), истории снапшотов (P2-09-01) и моков
для P3 (P2-12-01). Коды reasons совпадают с attention items (P2-10).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import HealthScoreStatus

Severity = Literal["high", "medium", "low"]


class HealthScoreBreakdown(BaseModel):
    """Покомпонентные скоры 0–100 (веса — в ``aggregate.WEIGHTS``)."""

    tasks: int = Field(ge=0, le=100, description="T: задачи без просрочек", examples=[76])
    documents: int = Field(ge=0, le=100, description="D: доля валидных документов", examples=[100])
    stages: int = Field(ge=0, le=100, description="S: этапы вовремя", examples=[70])
    teachers: int = Field(ge=0, le=100, description="E: готовность преподавателей", examples=[85])
    launch: int = Field(ge=0, le=100, description="L: готовность запуска программ", examples=[80])

    model_config = {"from_attributes": True}


class HealthScoreReason(BaseModel):
    """Одна причина снижения скора (понятный UI текст)."""

    code: str = Field(
        description="Код: OVERDUE_TASKS, INVALID_DOCUMENTS, OVERDUE_STAGES, EXPIRED_CERTIFICATES, LAUNCH_DELAYED",
        examples=["OVERDUE_TASKS"],
    )
    severity: Severity = Field(description="high — просрочено, medium — под риском", examples=["high"])
    text: str = Field(description="Человекочитаемый текст для UI", examples=["3 просроченные задачи"])

    model_config = {"from_attributes": True}


class HealthScoreCounters(BaseModel):
    """Отладочные счётчики — прозрачность формулы (какие входы дали скор)."""

    overdue_critical_tasks: int = Field(default=0, ge=0, examples=[0])
    overdue_normal_tasks: int = Field(default=0, ge=0, examples=[3])
    total_required_documents: int = Field(default=0, ge=0, examples=[4])
    valid_documents: int = Field(default=0, ge=0, examples=[4])
    stages_due: int = Field(default=0, ge=0, examples=[5])
    stages_on_time: int = Field(default=0, ge=0, examples=[4])
    teachers_required: int = Field(default=0, ge=0, examples=[4])
    teachers_ready: int = Field(default=0, ge=0, examples=[3])
    active_programs: int = Field(default=0, ge=0, examples=[2])
    programs_launched_on_time: int = Field(default=0, ge=0, examples=[1])
    programs_at_risk: int = Field(default=0, ge=0, examples=[1])

    model_config = {"from_attributes": True}


class HealthScoreResponse(BaseModel):
    """Полный ответ Health Score вуза (P2-07-08, endpoint P2-08-01)."""

    university_id: uuid.UUID = Field(description="UUID вуза", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    score: int = Field(ge=0, le=100, description="Взвешенный итог 0–100", examples=[78])
    status: HealthScoreStatus = Field(description="green 85–100, yellow 60–84, red 0–59", examples=["yellow"])
    breakdown: HealthScoreBreakdown = Field(description="Покомпонентные скоры")
    reasons: list[HealthScoreReason] = Field(default_factory=list, description="Причины снижения (пусто при score=100)")
    calculated_at: datetime = Field(description="Момент расчёта (UTC, tz-aware)", examples=["2026-09-20T12:00:00Z"])
    input_counters: HealthScoreCounters = Field(
        default_factory=HealthScoreCounters, description="Счётчики входов формулы"
    )

    model_config = {"from_attributes": True}


class HealthScoreShort(BaseModel):
    """Компактная версия для batch (P2-08-02) — без reasons/counters."""

    university_id: uuid.UUID = Field(description="UUID вуза")
    score: int = Field(ge=0, le=100, description="Взвешенный итог 0–100", examples=[78])
    status: HealthScoreStatus = Field(description="green/yellow/red", examples=["yellow"])
    breakdown: HealthScoreBreakdown = Field(description="Покомпонентные скоры")

    model_config = {"from_attributes": True}

    @classmethod
    def from_full(cls, full: HealthScoreResponse) -> "HealthScoreShort":
        """Сжать полный ответ до batch-вида."""
        return cls(
            university_id=full.university_id,
            score=full.score,
            status=full.status,
            breakdown=full.breakdown,
        )


class HealthScoreRankItem(HealthScoreShort):
    """Строка рейтинга (P2-08-03): короткий скор + место + название вуза."""

    rank: int = Field(ge=1, description="Место в рейтинге (1-based)", examples=[1])
    university_name: str = Field(description="Название вуза", examples=["МГУ"])

    model_config = {"from_attributes": True}


class AttentionItem(BaseModel):
    """Один пункт «что требует внимания» (P2-10-01/02)."""

    code: str = Field(
        description="OVERDUE_STAGE, EXPIRING_LICENSE, EXPIRED_DOCUMENT, EXPIRING_CERTIFICATE, LAUNCH_AT_RISK",
        examples=["OVERDUE_STAGE"],
    )
    severity: Severity = Field(description="high — просрочено, medium — <30 дн, low — <60 дн", examples=["high"])
    title: str = Field(description="Короткий заголовок для UI", examples=["Просрочен этап"])
    description: str = Field(
        description="Детали с именами и датами", examples=["Этап 'Подписание' просрочен на 5 дн."]
    )
    entity_type: str = Field(
        description="workflow_stage | license | document | certificate | program",
        examples=["workflow_stage"],
    )
    entity_id: uuid.UUID = Field(description="UUID связанной сущности")
    due_date: date | None = Field(default=None, description="Контрольная дата (если есть)")

    model_config = {"from_attributes": True}


class AttentionItemsResponse(BaseModel):
    """Ответ endpoint attention-items (P2-10-02)."""

    items: list[AttentionItem] = Field(default_factory=list, description="До 20 пунктов, severity DESC, due ASC")

    model_config = {"from_attributes": True}


__all__ = [
    "AttentionItem",
    "AttentionItemsResponse",
    "HealthScoreBreakdown",
    "HealthScoreCounters",
    "HealthScoreRankItem",
    "HealthScoreReason",
    "HealthScoreResponse",
    "HealthScoreShort",
    "Severity",
]
