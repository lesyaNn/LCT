"""Best-effort notifications after a Workflow task mutation has committed."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.catalog import University
from app.models.workflow_instances import WorkflowInstance, WorkflowTask
from app.modules.admin_users.keycloak_client import KeycloakAdminClient
from app.modules.notifications import service as notification_service
from app.modules.notifications.workflow_comments import _preview, _recipients

logger = logging.getLogger("rtk")


def notify_task(
    db: Session, kc: KeycloakAdminClient, instance: WorkflowInstance,
    task: WorkflowTask, actor: CurrentUser, *, event_type: str,
    operation_id: uuid.UUID,
) -> None:
    """Publish after the task commit, isolating recipient and delivery failures."""
    try:
        university = db.get(University, instance.university_id)
        stage = next((row for row in instance.instance_stages
                      if row.template_stage_id == task.stage_id), None)
        if university is None or stage is None:
            return
        actor_name = _preview(actor.name or actor.username or "Пользователь")
        if event_type == "workflow_task_added":
            title = "Добавлена новая задача"
            verb = "добавил задачу"
        elif event_type == "workflow_task_completed":
            title = "Задача выполнена"
            verb = "выполнил задачу"
        else:
            raise ValueError(f"Unsupported Workflow task event: {event_type}")
        message = (f"{actor_name} {verb} «{_preview(task.title)}» "
                   f"на этапе «{_preview(stage.name)}» "
                   f"по ВУЗу «{_preview(university.name)}».")
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
        logger.exception("workflow_task_notification_failed", extra={
            "task_id": str(task.id), "event_type": event_type,
            "operation_id": str(operation_id),
        })
