"""Database-independent checks for the Dev-2 audit transaction contract."""

from unittest.mock import Mock
from uuid import uuid4

from app.modules.audit.service import AuditAction, AuditContext, AuditService


def test_audit_writer_never_owns_business_commit():
    db = Mock()

    event = AuditService(db).log_event(
        context=AuditContext("actor", "Actor", "admin"),
        action=AuditAction.UPDATE,
        entity_type="university",
        entity_id=uuid4(),
        old_value={"password": "must-not-be-kept"},
        new_value={"status": "active"},
    )

    db.add.assert_called_once_with(event)
    db.flush.assert_not_called()
    db.commit.assert_not_called()
    assert event.old_value == {"password": "***REDACTED***"}
