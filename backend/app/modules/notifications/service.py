"""Business-event projection into recipient-specific notifications and channels."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.permissions import user_permissions
from app.core.policies import get_data_scope
from app.core.security import CurrentUser
from app.config import settings
from app.models.catalog import Contract, License, Responsible, University, UniversityResponsible
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask
from app.schemas.validation import email as validate_email
from app.services.license_status import derive_contract_status

EXPIRY_CHECKPOINTS = (30, 14, 7, 1)
STAGE_CHECKPOINTS = (7, 2, 1)


def _school_label(name: str) -> str:
    return name if "«" in name else f"«{name}»"


def publish(
    db: Session, *, recipient_user_id: str | None, event_key: str, type: str,
    priority: str, title: str, message: str, entity_type: str,
    entity_id: uuid.UUID | str, university_id: uuid.UUID | None = None,
) -> bool:
    """Persist one logical notification and its optional email intent atomically."""
    if not recipient_user_id:
        return False
    if priority not in {"INFO", "WARNING", "CRITICAL"}:
        raise ValueError("Invalid notification priority")
    values = dict(
        id=uuid.uuid4(), recipient_user_id=recipient_user_id, event_key=event_key,
        type=type, priority=priority, title=title, message=message,
        entity_type=entity_type, entity_id=str(entity_id), university_id=university_id,
        is_read=False,
    )
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        stmt = pg_insert(Notification).values(**values).on_conflict_do_nothing(
            index_elements=["recipient_user_id", "event_key"]
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(Notification).values(**values).on_conflict_do_nothing(
            index_elements=["recipient_user_id", "event_key"]
        )
    else:
        raise RuntimeError(f"Unsupported notification database: {dialect}")
    notification_id = db.execute(stmt.returning(Notification.id)).scalar_one_or_none()
    if notification_id is None:
        return False
    if settings.email_notifications_enabled:
        # The linked CRM responsible is the local durable address source.
        address = db.scalar(select(Responsible.email).where(
            Responsible.keycloak_sub == recipient_user_id
        ))
        try:
            address = validate_email(address) if address else None
        except ValueError:
            address = None
        if address:
            delivery_values = dict(
                id=uuid.uuid4(), notification_id=notification_id, channel="email",
                recipient=address, status="pending", attempts=0,
            )
            if dialect == "postgresql":
                delivery_stmt = pg_insert(NotificationDelivery).values(**delivery_values)
            else:
                delivery_stmt = sqlite_insert(NotificationDelivery).values(**delivery_values)
            db.execute(delivery_stmt.on_conflict_do_nothing(
                index_elements=["notification_id", "channel"]
            ))
    return True


def recipient_for_responsible(db: Session, responsible_id: uuid.UUID | None) -> str | None:
    if responsible_id is None:
        return None
    return db.scalar(select(Responsible.keycloak_sub).where(Responsible.id == responsible_id))


def primary_recipient(db: Session, university_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(Responsible.keycloak_sub)
        .join(UniversityResponsible, UniversityResponsible.responsible_id == Responsible.id)
        .where(UniversityResponsible.university_id == university_id,
               UniversityResponsible.is_primary.is_(True),
               Responsible.keycloak_sub.is_not(None))
        .limit(1)
    )


def notify_assignment(db: Session, responsible_id: uuid.UUID, university_id: uuid.UUID,
                      *, entity_type: str = "university", entity_id: uuid.UUID | None = None,
                      event_key: str) -> bool:
    university = db.get(University, university_id)
    if university is None:
        return False
    return publish(
        db, recipient_user_id=recipient_for_responsible(db, responsible_id),
        event_key=event_key, type="assignment", priority="INFO",
        title="Вам назначен новый ВУЗ" if entity_type == "university" else "Вам назначена работа",
        message=(f"Вы назначены ответственным за {_school_label(university.name)}."
                 if entity_type == "university" else
                 f"Вы назначены ответственным за работу с {_school_label(university.name)}."),
        entity_type=entity_type, entity_id=entity_id or university_id,
        university_id=university_id,
    )


def notify_stage_change(db: Session, instance: WorkflowInstance, from_stage: InstanceStage,
                        to_stage: InstanceStage, *, rollback: bool, reason: str,
                        event_key: str) -> bool:
    university = db.get(University, instance.university_id)
    recipient = recipient_for_responsible(db, to_stage.responsible_id or instance.responsible_id)
    if university is None:
        return False
    message = (f"Работа с {_school_label(university.name)} возвращена с этапа «{from_stage.name}» "
               f"на этап «{to_stage.name}». Причина: {reason}" if rollback else
               f"{_school_label(university.name)} переведён с этапа «{from_stage.name}» "
               f"на этап «{to_stage.name}».")
    return publish(
        db, recipient_user_id=recipient, event_key=event_key,
        type="workflow_rollback" if rollback else "workflow_stage_changed",
        priority="WARNING" if rollback else "INFO",
        title="Этап возвращён" if rollback else "Изменился этап работы",
        message=message, entity_type="workflow", entity_id=instance.id,
        university_id=instance.university_id,
    )


def notify_import_result(db: Session, job, *, failed: bool = False) -> bool:
    result = job.result if isinstance(job.result, dict) else {}
    errors = int(result.get("errors_total") or 0)
    if not failed and errors <= 0:
        return False
    total = int(result.get("total_rows") or 0)
    success = int(result.get("inserted") or 0) + int(result.get("updated") or 0)
    message = ("Не удалось завершить импорт. Посмотрите результат задачи."
               if failed else f"Обработано: {total} строк. Успешно: {success}. Ошибок: {errors}.")
    return publish(
        db, recipient_user_id=job.actor_sub, event_key=f"import-error:{job.id}",
        type="import_error", priority="WARNING", title="Импорт завершён с ошибками",
        message=message, entity_type="import_job", entity_id=job.id,
    )


def _visible(user: CurrentUser):
    scope = get_data_scope(user)
    clauses = [Notification.recipient_user_id == user.id]
    if not scope.is_all:
        clauses.append(or_(Notification.university_id.is_(None),
                           Notification.university_id.in_(scope.university_ids)))
    if "import.read" not in user_permissions(user):
        clauses.append(Notification.entity_type != "import_job")
    return and_(*clauses)


def list_for_user(db: Session, user: CurrentUser, *, filter: str = "all",
                  limit: int = 20, offset: int = 0) -> tuple[list[Notification], int]:
    condition = _visible(user)
    if filter == "unread":
        condition = and_(condition, Notification.is_read.is_(False))
    elif filter == "attention":
        condition = and_(condition, Notification.priority.in_(["WARNING", "CRITICAL"]))
    total = db.scalar(select(func.count()).select_from(Notification).where(condition)) or 0
    rows = list(db.scalars(select(Notification).where(condition)
                           .order_by(Notification.created_at.desc(), Notification.id.desc())
                           .limit(limit).offset(offset)).all())
    return rows, total


def unread_count(db: Session, user: CurrentUser) -> int:
    return db.scalar(select(func.count()).select_from(Notification)
                     .where(_visible(user), Notification.is_read.is_(False))) or 0


def mark_read(db: Session, user: CurrentUser, notification_id: uuid.UUID) -> bool:
    row = db.scalar(select(Notification).where(Notification.id == notification_id, _visible(user)))
    if row is None:
        return False
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return True


def mark_all_read(db: Session, user: CurrentUser) -> int:
    result = db.execute(update(Notification).where(_visible(user), Notification.is_read.is_(False))
                        .values(is_read=True, read_at=datetime.now(timezone.utc)))
    db.commit()
    return result.rowcount or 0


def scan_due_notifications(db: Session, *, today: date | None = None) -> int:
    """Run from the existing worker; dedupe keys make retries and restarts safe."""
    day = today or datetime.now(timezone.utc).date()
    made = 0
    active = select(WorkflowInstance).where(WorkflowInstance.status == "active")
    for instance in db.scalars(active):
        university = db.get(University, instance.university_id)
        if university is None:
            continue
        stages = db.scalars(select(InstanceStage).where(
            InstanceStage.instance_id == instance.id, InstanceStage.completed_at.is_(None),
            InstanceStage.id == instance.current_instance_stage_id,
            InstanceStage.status.notin_(["completed", "skipped"]),
            InstanceStage.due_date.is_not(None),
        )).all()
        for stage in stages:
            days = (stage.due_date - day).days
            if days not in STAGE_CHECKPOINTS and days >= 0:
                continue
            if days < 0:
                kind, priority, title = "overdue", "CRITICAL", "Требуется внимание"
                message = f"Этап «{stage.name}» для {_school_label(university.name)} просрочен на {-days} дн."
                key = f"stage-overdue:{stage.id}:{stage.due_date}"
            else:
                kind, priority, title = "deadline_approaching", "WARNING", "Приближается срок"
                message = f"До завершения этапа «{stage.name}» для {_school_label(university.name)} осталось {days} дн."
                key = f"stage-due:{stage.id}:{stage.due_date}:{days}"
            made += publish(db, recipient_user_id=recipient_for_responsible(
                db, stage.responsible_id or instance.responsible_id), event_key=key,
                type=kind, priority=priority, title=title, message=message,
                entity_type="workflow", entity_id=instance.id,
                university_id=instance.university_id,
            )
        tasks = db.scalars(select(WorkflowTask).where(
            WorkflowTask.instance_id == instance.id, WorkflowTask.status == "open",
            WorkflowTask.deadline.is_not(None),
        )).all()
        for task in tasks:
            days = (task.deadline - day).days
            if days not in STAGE_CHECKPOINTS and days >= 0:
                continue
            overdue = days < 0
            made += publish(
                db, recipient_user_id=recipient_for_responsible(
                    db, task.responsible_id or instance.responsible_id),
                event_key=(f"task-overdue:{task.id}:{task.deadline}" if overdue else
                           f"task-due:{task.id}:{task.deadline}:{days}"),
                type="overdue" if overdue else "deadline_approaching",
                priority="CRITICAL" if overdue else "WARNING",
                title="Требуется внимание" if overdue else "Приближается срок",
                message=(f"Задача «{task.title}» для {_school_label(university.name)} просрочена на {-days} дн."
                         if overdue else f"До срока задачи «{task.title}» для {_school_label(university.name)} осталось {days} дн."),
                entity_type="workflow", entity_id=instance.id,
                university_id=instance.university_id,
            )
    for model, kind, noun in ((Contract, "contract_expiry", "договора"),
                              (License, "license_expiry", "лицензии")):
        for item in db.scalars(select(model).where(model.expires_at.is_not(None),
                                                  model.expires_at >= day,
                                                  model.expires_at <= day + timedelta(days=30))):
            if model is Contract and derive_contract_status(
                item.status_raw, item.expires_at, today=day
            ) != "active":
                continue
            days = (item.expires_at - day).days
            if days == 0:
                checkpoint = 0
            else:
                checkpoint = next((n for n in sorted(EXPIRY_CHECKPOINTS) if days <= n), None)
            if checkpoint is None:
                continue
            university = db.get(University, item.university_id)
            if university is None:
                continue
            made += publish(
                db, recipient_user_id=primary_recipient(db, item.university_id),
                event_key=f"{kind}:{item.id}:{item.expires_at}:{checkpoint}",
                type=kind, priority="CRITICAL" if days <= 1 else "WARNING",
                title="Срок договора заканчивается" if model is Contract else "Срок лицензии заканчивается",
                message=f"Срок {noun} с {_school_label(university.name)} — {item.expires_at:%d.%m.%Y}. Осталось {days} дн.",
                entity_type="contract" if model is Contract else "license",
                entity_id=item.id, university_id=item.university_id,
            )
    db.commit()
    return made
