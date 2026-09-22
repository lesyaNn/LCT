"""P2-09-01: каноническая модель снапшотов Health Score.

Таблица ``health_score_snapshots`` — история для динамики/трендов
(P3-05-02 график, P4-08-01). Пишется ежедневным cron (``daily_cron``,
идемпотентно через ``ON CONFLICT DO NOTHING`` по
``(university_id, period_day, trigger_event)``) и event-driven триггерами
(``transition``/``document_update`` — позже, в отдельных задачах).

Endpoint ``GET /universities/{id}/health-score/history`` — позже (не в scope
этой задачи): здесь только модель + миграции + Pydantic-схемы для Swagger.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin

#: Триггер ежедневного cron (идемпотентный: один вуз × один день × один триггер).
TRIGGER_DAILY_CRON = "daily_cron"
#: Триггер workflow-перехода (event-driven, позже).
TRIGGER_TRANSITION = "transition"
#: Триггер изменения документа/лицензии (event-driven, позже).
TRIGGER_DOCUMENT_UPDATE = "document_update"


class HealthScoreSnapshot(UUIDPKMixin, Base):
    """Один замер Health Score вуза (P2-09-01).

    ``breakdown``/``reasons`` — копии ответа на момент ``calculated_at``
    (JSONB на PostgreSQL, generic JSON на SQLite для unit-тестов).
    ``period_day`` — ``calculated_at::date`` (идемпотентность cron).
    """

    __tablename__ = "health_score_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "university_id",
            "period_day",
            "trigger_event",
            name="uq_health_snapshots_uni_day_trigger",
        ),
        Index(
            "ix_health_snapshots_university_id",
            "university_id",
        ),
        Index(
            "ix_health_snapshots_univ_calculated",
            "university_id",
            "calculated_at",
        ),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "universities.id",
            name="fk_health_snapshots_university_id_universities",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(GenericJSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_day: Mapped[date] = mapped_column(Date, nullable=False)
    trigger_event: Mapped[str] = mapped_column(
        String(64), nullable=False, default=TRIGGER_DAILY_CRON
    )


__all__ = [
    "TRIGGER_DAILY_CRON",
    "TRIGGER_DOCUMENT_UPDATE",
    "TRIGGER_TRANSITION",
    "HealthScoreSnapshot",
]
