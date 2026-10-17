"""Best-effort notifications for manually created Workflow comments."""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.catalog import University
from app.models.workflow_instances import WorkflowComment, WorkflowInstance
from app.modules.admin_users.keycloak_client import KeycloakAdminClient
from app.modules.notifications import service as notification_service

logger = logging.getLogger("rtk")
MAX_USERS = 10_000


def _pages(fetch):
    for first in range(0, MAX_USERS, 100):
        rows = fetch(first, 100)
        yield from rows
        if len(rows) < 100:
            return
    raise RuntimeError("Keycloak user listing exceeds limit")


def _has_explicit_access(record: dict, university_id: uuid.UUID) -> bool:
    """Use assigned IDs even for admins; their global read grant is not an assignment."""
    raw = (record.get("attributes") or {}).get("university_ids") or []
    values = raw if isinstance(raw, list) else [raw]
    for value in values:
        try:
            if uuid.UUID(str(value)) == university_id:
                return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


def _recipients(kc: KeycloakAdminClient, university_id: uuid.UUID, author_id: str):
    members = {
        record["id"]
        for role in ("admin", "manager", "user")
        for record in _pages(lambda first, size: kc.role_users(role, first=first, maximum=size))
    }
    for record in _pages(lambda first, size: kc.users(first=first, maximum=size)):
        user_id = record.get("id")
        if (user_id in members and user_id != author_id
                and record.get("enabled", True)
                and _has_explicit_access(record, university_id)):
            yield record


def _preview(content: str) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact if len(compact) <= 180 else compact[:179].rstrip() + "…"


def notify_comment(
    db: Session, kc: KeycloakAdminClient, instance: WorkflowInstance,
    comment: WorkflowComment, author: CurrentUser,
) -> None:
    """Called only after the manual comment transaction has committed."""
    try:
        university = db.get(University, instance.university_id)
        if university is None:
            return
        name = author.name or author.username or "Пользователь"
        message = (f"{name} оставил комментарий по ВУЗу "
                   f"«{university.name}»: «{_preview(comment.content)}»")
        for recipient in _recipients(kc, instance.university_id, author.id):
            notification_service.publish(
                db, recipient_user_id=recipient["id"],
                recipient_email=recipient.get("email"),
                event_key=f"workflow_comment_added:{comment.id}",
                type="workflow_comment_added", priority="INFO",
                title="Новый комментарий в Workflow", message=message,
                entity_type="workflow", entity_id=instance.id,
                university_id=instance.university_id,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("workflow_comment_notification_failed", extra={"comment_id": str(comment.id)})
