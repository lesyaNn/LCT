"""Append-only transactional audit writer and bounded sanitizer."""

import json
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.permissions import effective_role
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.audit.models import AuditEvent
from app.models.audit_outbox import AuditOutbox


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    WORKFLOW_TRANSITION = "WORKFLOW_TRANSITION"
    ASSIGN_RESPONSIBLE = "ASSIGN_RESPONSIBLE"
    IMPORT = "IMPORT"
    REPORT_GENERATE = "REPORT_GENERATE"
    REPORT_DOWNLOAD = "REPORT_DOWNLOAD"
    ADMIN_CONFIG = "ADMIN_CONFIG"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"


class AuditEntityType(StrEnum):
    UNIVERSITY = "university"
    WORKFLOW_INSTANCE = "workflow_instance"
    WORKFLOW_STAGE = "workflow_stage"
    LICENSE = "license"
    CONTRACT = "contract"
    DOCUMENT = "document"
    MEETING = "meeting"
    RESPONSIBLE = "responsible"
    DIRECTION = "direction"
    PROGRAM = "program"
    VENDOR = "vendor"
    PRODUCT = "product"
    WORKFLOW_COMMENT = "workflow_comment"
    REPORT = "report"
    CONFIG = "config"


_SECRET = re.compile(r"password|passwd|access.?token|refresh.?token|authorization|cookie|client.?secret|secret|private.?key|jwt", re.I)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_INLINE_SECRET = re.compile(
    r"(password|passwd|access.?token|refresh.?token|authorization|cookie|client.?secret|secret|private.?key)"
    r"\s*[:=]\s*\S+",
    re.I,
)
_MAX_BYTES = 8192


def sanitize(value: Any, depth: int = 0) -> Any:
    """Keep audit JSON safe, small and serializable, including nested input."""
    if depth > 8:
        return "***TRUNCATED***"
    if isinstance(value, dict):
        return {
            str(key)[:128]: "***REDACTED***" if _SECRET.search(str(key)) else sanitize(item, depth + 1)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, depth + 1) for item in list(value)[:100]]
    if isinstance(value, bytes):
        return "***REDACTED***"
    if isinstance(value, str):
        value = _JWT.sub("***REDACTED***", value[:2048])
        return _INLINE_SECRET.sub(lambda m: f"{m.group(1)}=***REDACTED***", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2048]


def bounded_snapshot(value: Any) -> Any:
    if value is None:
        return None
    result = sanitize(value)
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > _MAX_BYTES:
        return {"summary": "***TRUNCATED***"}
    return result


@dataclass(frozen=True)
class AuditContext:
    user_id: str
    user_name: str
    role: str
    request_id: uuid.UUID | None = None
    ip: str | None = None
    user_agent: str | None = None

    @classmethod
    def from_request(cls, request: Request, user: CurrentUser) -> "AuditContext":
        raw = getattr(request.state, "request_id", None)
        return cls(
            user_id=user.id,
            user_name=(user.name or user.username or user.id)[:512],
            role=effective_role(user),
            request_id=uuid.UUID(raw) if raw else None,
            ip=request.client.host[:45] if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:512] or None,
        )


class AuditService:
    """Audit inserts join the caller's transaction. Never commits."""

    def __init__(self, db: Session):
        self.db = db

    def log_event(
        self, *, context: AuditContext, action: AuditAction | str,
        entity_type: AuditEntityType | str, entity_id: uuid.UUID,
        university_id: uuid.UUID | None = None,
        old_value: Any = None, new_value: Any = None,
        flush: bool = False,
    ) -> AuditEvent:
        event = AuditEvent(
            user_id=context.user_id, user_name=context.user_name, role=context.role,
            action=str(action), entity_type=str(entity_type), entity_id=entity_id,
            university_id=university_id, old_value=bounded_snapshot(old_value),
            new_value=bounded_snapshot(new_value), request_id=context.request_id,
            ip_address=context.ip, user_agent=context.user_agent,
        )
        self.db.add(event)
        if flush:
            self.db.flush()
        return event

    def enqueue_event(
        self, *, context: AuditContext, action: AuditAction | str,
        entity_type: AuditEntityType | str, entity_id: uuid.UUID,
        university_id: uuid.UUID | None = None, old_value: Any = None,
        new_value: Any = None, dedupe_key: str | None = None,
    ) -> AuditOutbox:
        """Persist sanitized audit intent with the business transaction."""
        outbox_id = uuid.uuid4()
        payload = {
            "user_id": context.user_id, "user_name": context.user_name,
            "role": context.role, "action": str(action),
            "entity_type": str(entity_type), "entity_id": str(entity_id),
            "university_id": str(university_id) if university_id else None,
            "old_value": bounded_snapshot(old_value),
            "new_value": bounded_snapshot(new_value),
            "request_id": str(context.request_id) if context.request_id else None,
            # Request metadata is bounded and JWT-shaped strings are redacted
            # before crossing the durable outbox boundary.
            "ip_address": bounded_snapshot(context.ip),
            "user_agent": bounded_snapshot(context.user_agent),
        }
        row = AuditOutbox(
            id=outbox_id, event_type=str(action), aggregate_type=str(entity_type),
            aggregate_id=entity_id,
            payload=payload,
            dedupe_key=dedupe_key or f"{entity_type}:{entity_id}:{action}:{outbox_id}",
        )
        self.db.add(row)
        return row

    def log(
        self, user_id: str | int, entity_type: str, entity_id: str | int | uuid.UUID,
        action: str, before=None, after=None, ip: str = "", university_id=None,
    ) -> AuditEvent:
        """Compatibility entry point for the unmounted P1 router; no commit."""
        try:
            entity_uuid = uuid.UUID(str(entity_id))
        except ValueError:
            entity_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"audit:{entity_type}:{entity_id}")
        return self.log_event(
            context=AuditContext(str(user_id), str(user_id), "user", ip=ip or None),
            action=action.upper(), entity_type=entity_type, entity_id=entity_uuid,
            university_id=university_id, old_value=before, new_value=after,
        )

    def recent_for_university(self, university_id, limit: int = 5) -> list[AuditEvent]:
        return (
            self.db.query(AuditEvent)
            .filter(AuditEvent.university_id == university_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit).all()
        )

    list_recent_for_university = recent_for_university


def get_audit_db(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Session:
    """Attach one request context to the existing business session."""
    db.info["audit_context"] = AuditContext.from_request(request, user)
    return db


def context_for(db: Session, actor: str = "system") -> AuditContext:
    return db.info.get("audit_context") or AuditContext(actor, actor, "user")


def _comment_snapshot(comment) -> dict[str, Any]:
    return {
        "audit_object_type": "workflow_comment",
        "instance_id": comment.instance_id,
        "stage_id": comment.stage_id,
        "is_internal": comment.is_internal,
    }


def _comment_university_id(session: Session, comment) -> uuid.UUID | None:
    from app.models.workflow_instances import WorkflowInstance

    instance = session.get(WorkflowInstance, comment.instance_id)
    return instance.university_id if instance is not None else None


@event.listens_for(Session, "before_flush")
def _audit_workflow_comments(session: Session, _flush_context, _instances) -> None:
    """Audit comments centrally without coupling workflow services to P5."""
    if "audit_context" not in session.info or session.info.get("_auditing_comments"):
        return
    from app.models.workflow_instances import WorkflowComment

    changes: list[tuple[Any, AuditAction, Any, Any]] = []
    for comment in session.new:
        if isinstance(comment, WorkflowComment):
            if comment.id is None:
                comment.id = uuid.uuid4()
            changes.append((comment, AuditAction.CREATE, None, _comment_snapshot(comment)))
    for comment in session.dirty:
        if not isinstance(comment, WorkflowComment) or not session.is_modified(
            comment, include_collections=False
        ):
            continue
        current = _comment_snapshot(comment)
        old = dict(current)
        state = inspect(comment)
        for field in current:
            # Presentation metadata is part of the snapshot, not a mapped
            # WorkflowComment attribute. Accessing it through state.attrs
            # raised a 500 on the real PATCH path with audit_context enabled.
            if field not in state.attrs:
                continue
            history = state.attrs[field].history
            if history.deleted:
                old[field] = history.deleted[0]
        changes.append((comment, AuditAction.UPDATE, old, current))
    for comment in session.deleted:
        if isinstance(comment, WorkflowComment):
            changes.append((comment, AuditAction.DELETE, _comment_snapshot(comment), None))
    if not changes:
        return
    session.info["_auditing_comments"] = True
    try:
        writer = AuditService(session)
        for comment, action, old, new in changes:
            writer.log_event(
                context=context_for(session),
                action=action,
                entity_type=AuditEntityType.WORKFLOW_COMMENT,
                entity_id=comment.id,
                university_id=_comment_university_id(session, comment),
                old_value=old,
                new_value=new,
            )
    finally:
        session.info.pop("_auditing_comments", None)
