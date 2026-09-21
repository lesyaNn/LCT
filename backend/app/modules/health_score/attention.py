"""P2-10-01: «Что требует внимания» — детерминированные правила без AI.

5 правил (WOW для демо, тексты — сразу для UI):
1. ``OVERDUE_STAGE`` — этап active-instance (current/pending) с прошедшим due;
2. ``EXPIRING_LICENSE`` — лицензия истекает в 0–30 дн. (31–60 дн. → low);
3. ``EXPIRED_DOCUMENT`` — обязательный документ просрочен;
4. ``EXPIRING_CERTIFICATE`` — mandatory-сертификат истекает в 1–30 дн.;
5. ``LAUNCH_AT_RISK`` — active-программа: запуск просрочен (high) или в 0–14 дн.

Сортировка: severity high → medium → low, затем due_date ASC (без даты — в конце).
Максимум 20 элементов. Коды совпадают с reasons Health Score (P2-07-08).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import ITProduct, ITProgram, License
from app.models.enums import TeacherReadiness
from app.models.interactions import Document, UniversityProgram
from app.models.teachers import (
    Teacher,
    TeacherCertificate,
    TeacherQualification,
)
from app.models.workflow import WorkflowInstance, WorkflowInstanceStage, WorkflowTemplateStage
from app.modules.health_score.documents_score import VALID_DOCUMENT_STATUSES, required_document_types
from app.modules.health_score.schemas import AttentionItem
from app.services.teacher_readiness import compute_teacher_readiness

#: Окно «истекает» (medium) и «под наблюдением» (low) в днях.
EXPIRING_DAYS = 30
WATCH_DAYS = 60
#: Окно риска запуска программы в днях.
LAUNCH_RISK_DAYS = 14
#: Лимит элементов на вуз.
MAX_ITEMS = 20

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

__all__ = [
    "EXPIRING_DAYS",
    "LAUNCH_RISK_DAYS",
    "MAX_ITEMS",
    "WATCH_DAYS",
    "get_attention_items",
]


def _sort_key(item: AttentionItem) -> tuple[int, date, str]:
    return (
        _SEVERITY_ORDER[item.severity],
        item.due_date or date.max,
        item.code,
    )


def get_attention_items(
    db: Session,
    university_id: uuid.UUID,
    today: date | None = None,
) -> list[AttentionItem]:
    """Собрать attention items вуза (batched SELECT, без N+1).

    Args:
        db: Sync SQLAlchemy-сессия.
        university_id: UUID вуза.
        today: Опорная дата (по умолчанию сегодня).

    Returns:
        До 20 пунктов, severity DESC + due ASC.
    """
    from app.config import settings as _settings

    today = today or date.today()
    items: list[AttentionItem] = []

    # --- 1. Просроченные этапы -------------------------------------------
    instance_ids = list(
        db.execute(
            select(WorkflowInstance.id).where(
                WorkflowInstance.university_id == university_id,
                WorkflowInstance.status == "active",
            )
        ).scalars().all()
    )
    if instance_ids:
        stage_rows = list(
            db.execute(
                select(
                    WorkflowInstanceStage.id,
                    WorkflowTemplateStage.name,
                    WorkflowInstanceStage.due_date,
                )
                .join(
                    WorkflowTemplateStage,
                    WorkflowTemplateStage.id == WorkflowInstanceStage.template_stage_id,
                )
                .where(
                    WorkflowInstanceStage.instance_id.in_(instance_ids),
                    WorkflowInstanceStage.status.in_(["current", "pending"]),
                    WorkflowInstanceStage.due_date.is_not(None),
                )
            ).all()
        )
        for stage_id, stage_name, due_date in stage_rows:
            due_day = due_date.date() if hasattr(due_date, "date") else due_date
            days = (today - due_day).days
            if days < 1:
                continue
            items.append(AttentionItem(
                code="OVERDUE_STAGE", severity="high",
                title="Просрочен этап",
                description=f"Этап '{stage_name}' просрочен на {days} дн.",
                entity_type="workflow_stage", entity_id=stage_id, due_date=due_day,
            ))

    # --- 2. Истекающие лицензии ------------------------------------------
    lic_rows = list(
        db.execute(
            select(License.id, License.expires_at, ITProduct.name)
            .join(ITProduct, ITProduct.id == License.product_id)
            .where(License.university_id == university_id)
        ).all()
    )
    for lic_id, expires_at, product_name in lic_rows:
        days_left = (expires_at - today).days
        if days_left < 0:
            continue  # истекшие — уже в Health Score reasons
        if days_left <= EXPIRING_DAYS:
            severity = "medium"
        elif days_left <= WATCH_DAYS:
            severity = "low"
        else:
            continue
        items.append(AttentionItem(
            code="EXPIRING_LICENSE", severity=severity,  # type: ignore[arg-type]
            title="Истекает лицензия",
            description=f"Лицензия '{product_name}' истекает {expires_at} ({days_left} дн.)",
            entity_type="license", entity_id=lic_id, due_date=expires_at,
        ))

    # --- 3. Просроченные обязательные документы ---------------------------
    required_types = required_document_types(
        getattr(_settings, "health_required_doc_types", "")
    )
    doc_rows = list(
        db.execute(
            select(Document.id, Document.title, Document.expires_at)
            .where(
                Document.university_id == university_id,
                Document.document_type.in_(sorted(required_types)),
                Document.status_raw.in_(sorted(VALID_DOCUMENT_STATUSES)),
                Document.expires_at.is_not(None),
                Document.expires_at < today,
            )
        ).all()
    )
    for doc_id, title, expires_at in doc_rows:
        items.append(AttentionItem(
            code="EXPIRED_DOCUMENT", severity="high",
            title="Просрочен документ",
            description=f"Документ '{title}' просрочен {expires_at}",
            entity_type="document", entity_id=doc_id, due_date=expires_at,
        ))

    # --- 4. Истекающие mandatory-сертификаты ------------------------------
    teachers = list(
        db.execute(
            select(Teacher).where(Teacher.university_id == university_id)
        ).scalars().all()
    )
    if teachers:
        teacher_ids = [t.id for t in teachers]
        certs = list(
            db.execute(
                select(TeacherCertificate).where(
                    TeacherCertificate.teacher_id.in_(teacher_ids),
                    TeacherCertificate.is_mandatory.is_(True),
                    TeacherCertificate.expires_at.is_not(None),
                )
            ).scalars().all()
        )
        quals = list(
            db.execute(
                select(TeacherQualification).where(
                    TeacherQualification.teacher_id.in_(teacher_ids)
                )
            ).scalars().all()
        )
        certs_by_teacher: dict[uuid.UUID, list] = {}
        for cert in certs:
            certs_by_teacher.setdefault(cert.teacher_id, []).append(cert)
        quals_by_teacher: dict[uuid.UUID, list] = {}
        for qual in quals:
            quals_by_teacher.setdefault(qual.teacher_id, []).append(qual)
        by_id = {t.id: t for t in teachers}
        for cert in certs:
            assert cert.expires_at is not None
            days_left = (cert.expires_at - today).days
            if days_left < 1 or days_left > EXPIRING_DAYS:
                continue
            readiness = compute_teacher_readiness(
                certificates=certs_by_teacher.get(cert.teacher_id, []),
                qualifications=quals_by_teacher.get(cert.teacher_id, []),
                today=today,
            )
            if readiness.readiness == TeacherReadiness.EXPIRED:
                continue  # уже в Health Score reasons
            teacher = by_id[cert.teacher_id]
            items.append(AttentionItem(
                code="EXPIRING_CERTIFICATE", severity="medium",
                title="Истекает сертификат",
                description=(
                    f"У преподавателя {teacher.full_name} истекает сертификат "
                    f"'{cert.certificate_name}' через {days_left} дн."
                ),
                entity_type="certificate", entity_id=cert.id,
                due_date=cert.expires_at,
            ))

    # --- 5. Программы под риском запуска ----------------------------------
    prog_rows = list(
        db.execute(
            select(UniversityProgram.id, ITProgram.name, UniversityProgram.launch_date)
            .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
            .where(
                UniversityProgram.university_id == university_id,
                UniversityProgram.status == "active",
                UniversityProgram.launch_date.is_not(None),
            )
        ).all()
    )
    for link_id, program_name, launch_date in prog_rows:
        delta = (launch_date - today).days
        if delta < 0:
            items.append(AttentionItem(
                code="LAUNCH_AT_RISK", severity="high",
                title="Запуск программы просрочен",
                description=f"Программа '{program_name}' должна была запуститься {launch_date}",
                entity_type="program", entity_id=link_id, due_date=launch_date,
            ))
        elif delta <= LAUNCH_RISK_DAYS:
            items.append(AttentionItem(
                code="LAUNCH_AT_RISK", severity="medium",
                title="Скоро запуск программы",
                description=f"Программа '{program_name}' запускается {launch_date}",
                entity_type="program", entity_id=link_id, due_date=launch_date,
            ))

    items.sort(key=_sort_key)
    return items[:MAX_ITEMS]
