"""P2-09-01: event snapshot writers (transition hook; cron is out of scope).

:func:`write_transition_snapshot` stores one Health Score measurement per
university/day/trigger (``transition``). Best-effort by design: a writer
failure (including the first-snapshot-wins unique conflict) must never
roll back the workflow transition that triggered it.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.health_score import (
    TRIGGER_TRANSITION,
    HealthScoreSnapshot,
)


def write_transition_snapshot(db: Session, university_id: uuid.UUID) -> bool:
    """Calculate the current score and store a ``transition`` snapshot.

    Returns True when a row was stored, False when skipped (conflict or
    any calculation/storage error). Commits in its own transaction;
    rolls back on conflict so the caller's session stays usable.
    """
    from app.modules.health_score.health_service import calculate_health_score

    try:
        response = calculate_health_score(db, university_id)
    except Exception:
        return False
    snapshot = HealthScoreSnapshot(
        university_id=university_id,
        score=response.score,
        status=response.status.value,
        breakdown=response.breakdown.model_dump(mode="json"),
        reasons=[r.model_dump(mode="json") for r in response.reasons],
        calculated_at=response.calculated_at,
        period_day=response.calculated_at.date(),
        trigger_event=TRIGGER_TRANSITION,
    )
    db.add(snapshot)
    try:
        db.commit()
    except IntegrityError:
        # First snapshot of the day wins (uq by uni/day/trigger) — skip.
        db.rollback()
        return False
    except Exception:
        db.rollback()
        return False
    return True


__all__ = ["write_transition_snapshot"]
