"""P2-07-03: компонент D — доля обязательных документов в валидном состоянии.

Только P1-источник (``documents`` из P1-01-03): workflow/tasks/license-таблицы
здесь НЕ используются. Обязательные типы — ``contract/license/act/protocol``,
настраиваются через ``Settings.health_required_doc_types`` (env
``HEALTH_REQUIRED_DOC_TYPES``, CSV).

Правило валидности (детерминированное, без AI):
* ``status_raw IN (signed, active)`` — черновики/архив не валидны;
* ``expires_at IS NULL OR expires_at >= today`` — просрочка не валидна.

Пустое множество требований → ``100`` (нечего проверять — не штрафуем).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Iterable

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interactions import Document

#: Обязательные типы документов по умолчанию (ТЗ, раздел P2-07-03).
DEFAULT_REQUIRED_DOCUMENT_TYPES: frozenset[str] = frozenset(
    {"contract", "license", "act", "protocol"}
)

#: Статусы, считающиеся валидными (подписан/действует).
VALID_DOCUMENT_STATUSES: frozenset[str] = frozenset({"signed", "active"})

__all__ = [
    "DEFAULT_REQUIRED_DOCUMENT_TYPES",
    "VALID_DOCUMENT_STATUSES",
    "DocumentsScore",
    "calc_D",
    "is_document_valid",
    "required_document_types",
    "score_documents",
]


def required_document_types(settings_value: str | None = None) -> frozenset[str]:
    """Разобрать CSV-настройку обязательных типов (env → множество).

    Args:
        settings_value: Сырое значение ``Settings.health_required_doc_types``.
            ``None``/пустая строка → дефолт ТЗ.

    Returns:
        Множество типов в нижнем регистре без пробелов.
    """
    if not settings_value or not settings_value.strip():
        return DEFAULT_REQUIRED_DOCUMENT_TYPES
    return frozenset(
        part.strip().lower() for part in settings_value.split(",") if part.strip()
    )


def is_document_valid(
    status_raw: str | None,
    expires_at: date | None,
    today: date | None = None,
) -> bool:
    """Проверить один документ на валидность (чистая функция).

    Args:
        status_raw: Сырой статус из ``documents.status_raw``.
        expires_at: Дата истечения (``None`` — бессрочный, валиден).
        today: Опорная дата (по умолчанию ``date.today()``).

    Returns:
        ``True`` если статус валидный и срок не истёк.
    """
    today = today or date.today()
    if (status_raw or "").lower() not in VALID_DOCUMENT_STATUSES:
        return False
    return expires_at is None or expires_at >= today


def score_documents(
    items: Iterable[object],
    today: date | None = None,
) -> tuple[int, int, int]:
    """Посчитать D по уже загруженным документам (чистая функция, без БД).

    Принимает ORM-объекты ``Document`` или dict'ы
    (``document_type``/``status``/``status_raw`` + ``expires_at``) — удобно для
    unit-тестов и для переиспользования в паспорте без лишних запросов.

    Args:
        items: Обязательные документы вуза (уже отфильтрованы по типу).
        today: Опорная дата.

    Returns:
        ``(score, valid_count, total_count)``; пустой вход → ``(100, 0, 0)``.
    """
    today = today or date.today()
    total = 0
    valid = 0
    for item in items:
        if isinstance(item, dict):
            status = item.get("status_raw", item.get("status"))
            expires = item.get("expires_at")
        else:
            status = getattr(item, "status_raw", getattr(item, "status", None))
            expires = getattr(item, "expires_at", None)
        total += 1
        if is_document_valid(status, expires, today):
            valid += 1
    if total == 0:
        return 100, 0, 0
    return round(100 * valid / total), valid, total


def calc_D(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
    required_types: frozenset[str] | None = None,
) -> tuple[int, int, int]:
    """Рассчитать компонент D для вуза (один SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата (по умолчанию сегодня).
        required_types: Переопределение обязательных типов (по умолчанию —
            из ``Settings.health_required_doc_types`` либо дефолт ТЗ).

    Returns:
        ``(score, valid_count, total_count)`` — score 0–100.
    """
    from app.config import settings as _settings

    today = today or date.today()
    if required_types is None:
        required_types = required_document_types(
            getattr(_settings, "health_required_doc_types", "")
        )
    rows = list(
        db.execute(
            select(Document.status_raw, Document.expires_at).where(
                Document.university_id == university_id,
                Document.document_type.in_(sorted(required_types)),
            )
        ).all()
    )
    total = len(rows)
    if total == 0:
        return 100, 0, 0
    valid = sum(1 for status_raw, expires_at in rows if is_document_valid(status_raw, expires_at, today))
    return round(100 * valid / total), valid, total


class DocumentsScore(BaseModel):
    """Компонент D для Swagger/OpenAPI (используется в breakdown Health Score).

    Возвращается агрегатором P2-07-01 как ``breakdown.documents`` вместе со
    счётчиками ``valid_documents/total_required_documents``.
    """

    score: int = Field(
        ge=0, le=100, description="Доля валидных обязательных документов, 0–100",
        examples=[75],
    )
    valid_count: int = Field(
        ge=0, description="Валидных обязательных документов",
        examples=[3],
    )
    total_count: int = Field(
        ge=0, description="Всего обязательных документов (типы contract/license/act/protocol)",
        examples=[4],
    )

    model_config = {"from_attributes": True}
