from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent, _dump


class AuditService:
    """Append-only log (§13). No update/delete methods by design."""

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        user_id: str | int,
        entity_type: str,
        entity_id: str | int,
        action: str,
        before=None,
        after=None,
        ip: str = "",
        university_id=None,
    ) -> AuditEvent:
        ev = AuditEvent(
            user_id=str(user_id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            before_data=_dump(before),
            after_data=_dump(after),
            ip_address=ip,
            university_id=university_id,
        )
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev

    def recent_for_university(self, university_id, limit: int = 5) -> list[AuditEvent]:
        """Last ``limit`` events of one university (P1-04-05 passport block).

        Filtering (``WHERE university_id = ?``) and ``ORDER BY created_at
        DESC LIMIT`` run in SQL — never load all universities' events into
        Python. ``id DESC`` tiebreaks same-second timestamps deterministically.
        """
        return (
            self.db.query(AuditEvent)
            .filter(AuditEvent.university_id == university_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .all()
        )
