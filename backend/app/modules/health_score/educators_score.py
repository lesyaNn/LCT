"""P2-07-05: компонент E — доля готовых преподавателей (только P1).

Требуемые преподаватели (детерминированно, без workflow):
* преподаватель вуза (``teachers.university_id``);
* привязан через ``teacher_programs`` к активной программе вуза
  (``university_programs.status IN (active, launched)``);
* имеет хотя бы один mandatory-сертификат (``is_mandatory=true``);
* уникальные по ``teacher_id``.

Готовность — общая логика P1-05-03
(:func:`app.services.teacher_readiness.compute_teacher_readiness`):
``ready ⟺ readiness == READY``. Нет требуемых → ``100``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import TeacherReadiness
from app.models.interactions import UniversityProgram
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.services.teacher_readiness import compute_teacher_readiness

#: Статусы university_programs, считающиеся активными для компонента E.
ACTIVE_PROGRAM_STATUSES: frozenset[str] = frozenset({"active", "launched"})

__all__ = [
    "ACTIVE_PROGRAM_STATUSES",
    "EducatorsScore",
    "calc_E",
    "score_educators",
]


def score_educators(
    readiness_flags: list[bool],
) -> tuple[int, int, int]:
    """Посчитать E по готовым флагам (чистая функция для тестов/агрегатора).

    Args:
        readiness_flags: По одному флагу на требуемого преподавателя
            (``True`` — READY).

    Returns:
        ``(score, ready_count, total_count)``; пустой вход → ``(100, 0, 0)``.
    """
    total = len(readiness_flags)
    if total == 0:
        return 100, 0, 0
    ready = sum(1 for flag in readiness_flags if flag)
    return round(100 * ready / total), ready, total


def calc_E(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
) -> tuple[int, int, int]:
    """Рассчитать компонент E для вуза (3 batched SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата для readiness (по умолчанию сегодня).

    Returns:
        ``(score, ready_count, total_count)`` — score 0–100.
    """
    today = today or date.today()

    active_program_ids = set(
        db.execute(
            select(UniversityProgram.program_id).where(
                UniversityProgram.university_id == university_id,
                UniversityProgram.status.in_(sorted(ACTIVE_PROGRAM_STATUSES)),
            )
        ).scalars().all()
    )
    if not active_program_ids:
        return 100, 0, 0

    # Преподаватели вуза на активных программах с mandatory-сертификатом.
    required_teacher_ids = list(
        db.execute(
            select(Teacher.id)
            .join(TeacherProgram, TeacherProgram.teacher_id == Teacher.id)
            .join(
                TeacherCertificate,
                TeacherCertificate.teacher_id == Teacher.id,
            )
            .where(
                Teacher.university_id == university_id,
                TeacherProgram.program_id.in_(active_program_ids),
                TeacherCertificate.is_mandatory.is_(True),
            )
            .distinct()
        ).scalars().all()
    )
    if not required_teacher_ids:
        return 100, 0, 0

    cert_rows = db.execute(
        select(TeacherCertificate).where(
            TeacherCertificate.teacher_id.in_(required_teacher_ids)
        )
    ).scalars().all()
    qual_rows = db.execute(
        select(TeacherQualification).where(
            TeacherQualification.teacher_id.in_(required_teacher_ids)
        )
    ).scalars().all()
    certs_by_teacher: dict[uuid.UUID, list] = defaultdict(list)
    for cert in cert_rows:
        certs_by_teacher[cert.teacher_id].append(cert)
    quals_by_teacher: dict[uuid.UUID, list] = defaultdict(list)
    for qual in qual_rows:
        quals_by_teacher[qual.teacher_id].append(qual)

    flags: list[bool] = []
    for teacher_id in required_teacher_ids:
        result = compute_teacher_readiness(
            certificates=certs_by_teacher.get(teacher_id, []),
            qualifications=quals_by_teacher.get(teacher_id, []),
            today=today,
        )
        flags.append(result.readiness == TeacherReadiness.READY)
    return score_educators(flags)


class EducatorsScore(BaseModel):
    """Компонент E для Swagger/OpenAPI (используется в breakdown Health Score)."""

    score: int = Field(
        ge=0, le=100, description="Доля READY-преподавателей активных программ, 0–100",
        examples=[80],
    )
    ready_count: int = Field(
        ge=0, description="Преподавателей со статусом ready",
        examples=[4],
    )
    total_count: int = Field(
        ge=0, description="Всего требуемых преподавателей (активные программы + mandatory-сертификат)",
        examples=[5],
    )

    model_config = {"from_attributes": True}
