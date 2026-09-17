from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent, _dump


class AuditService:
    """Append-only log (§13). No update/delete methods by design."""

    def __init__(self, db: Session):
        self.db = db

    def log(self, user_id: int, entity_type: str, entity_id: int,
            action: str, before=None, after=None, ip: str = "") -> AuditEvent:
        ev = AuditEvent(user_id=user_id, entity_type=entity_type, entity_id=entity_id,
                        action=action, before_data=_dump(before), after_data=_dump(after),
                        ip_address=ip)
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev
