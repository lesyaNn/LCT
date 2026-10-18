"""Best-effort status notifications after a Workflow operation has committed."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.catalog import University
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.admin_users.keycloak_client import KeycloakAdminClient
from app.modules.notifications import service as notification_service
from app.modules.notifications.workflow_comments import _preview, _recipients

logger = logging.getLogger("rtk")


def notify_status(
    db: Session, kc: KeycloakAdminClient, instance: WorkflowInstance,
    actor: CurrentUser, *, event_type: str, operation_id: uuid.UUID,
    from_stage_name: str | None = None, to_stage_name: str | None = None,
    reason: str | None = None,
) -> None:
    """Publish only after the business transaction commits; errors are isolated."""
    try:
        university = db.get(University, instance.university_id)
        if university is None:
            return
        name = actor.name or actor.username or "Пользователь"
        school = f"«{university.name}»"
        if event_type == "workflow_stage_completed":
            title = "Этап Workflow завершён"
            message = (f"{name} завершил этап «{from_stage_name}» по ВУЗу {school}. "
                       f"Новый этап: «{to_stage_name}».")
        elif event_type == "workflow_rollback":
            title = "Workflow возвращён на предыдущий этап"
            message = f"{name} вернул Workflow по ВУЗу {school} на этап «{to_stage_name}»."
            if reason:
                message += f" Причина: {_preview(reason)}"
        elif event_type == "workflow_completed":
            if instance.status != "completed" or instance.completed_at is None:
                return
            title = "Workflow завершён"
            message = f"{name} завершил Workflow по ВУЗу {school}."
            template = db.get(WorkflowTemplate, instance.template_id)
            if template is not None:
                message += f" Процесс: «{template.name}»."
        else:
            raise ValueError(f"Unsupported Workflow notification event: {event_type}")

        for recipient in _recipients(kc, instance.university_id, actor.id):
            notification_service.publish(
                db, recipient_user_id=recipient["id"],
                recipient_email=recipient.get("email"),
                event_key=f"{event_type}:{operation_id}",
                type=event_type, priority="INFO", title=title, message=message,
                entity_type="workflow", entity_id=instance.id,
                university_id=instance.university_id,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("workflow_status_notification_failed", extra={
            "instance_id": str(instance.id), "event_type": event_type,
            "operation_id": str(operation_id),
        })
