"""Persist real Health Score observations for the graph."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import ITProgram, University
from app.models.health_score_observation import HealthScoreObservation
from app.modules.analytics.integration import Selection
from app.modules.analytics.repository import load_data
from app.modules.analytics.service import build_matrix


def record_observation(
    db: Session, university_id: UUID, score: int | None, level: str, now: datetime, *, daily: bool = False
) -> bool:
    """Save a changed score, or the first observed score of a UTC day.

    Locking the university row serializes the API and worker writers so a
    simultaneous first read cannot create duplicate points.
    """
    if score is None:
        return False
    if db.scalar(select(University.id).where(University.id == university_id).with_for_update()) is None:
        db.rollback()
        return False
    latest = db.scalar(
        select(HealthScoreObservation)
        .where(HealthScoreObservation.university_id == university_id)
        .order_by(HealthScoreObservation.calculated_at.desc(), HealthScoreObservation.id.desc())
        .limit(1)
    )
    last_saved_at = latest.calculated_at if latest is not None else None
    if last_saved_at is not None and last_saved_at.tzinfo is None:
        last_saved_at = last_saved_at.replace(tzinfo=timezone.utc)
    should_record = (
        latest is None
        or latest.score != score
        or latest.level != level
        or (daily and last_saved_at.date() < now.date())
        or last_saved_at < now - timedelta(days=731)
    )
    if should_record:
        db.add(HealthScoreObservation(
            university_id=university_id, score=score, level=level, calculated_at=now
        ))
    db.commit()
    return should_record


def record_daily_observations(now: datetime | None = None) -> int:
    """Calculate and persist one real daily score for every scored university."""
    from app.db.session import SessionLocal

    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        universities = list(db.scalars(select(University.id)))
        programs = list(db.scalars(select(ITProgram.id)))
        if not universities or not programs:
            return 0
        data = load_data(db, Selection(university_ids=universities, program_ids=programs), today=now.date())
        matrix = build_matrix(data, today=now.date())
        return sum(
            record_observation(db, row.id, row.health_score, row.health_level, now, daily=True)
            for row in matrix.rows
        )
    finally:
        db.close()
