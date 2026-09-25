"""Persist the canonical Health Score result for SQL readers and history."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.catalog import University
from app.models.health_score import HealthScoreCurrent, HealthScoreSnapshot, TRIGGER_DAILY_CRON
from app.modules.health_score.health_service import calculate_health_score
from app.modules.health_score.schemas import HealthScoreResponse


def _insert(db: Session, model, values: dict):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return pg_insert(model).values(**values)
    if dialect == "sqlite":
        return sqlite_insert(model).values(**values)
    raise RuntimeError(f"Unsupported Health Score materialization dialect: {dialect}")


def refresh_health_score(
    db: Session,
    university_id: uuid.UUID,
    trigger_event: str,
    *,
    create_snapshot: bool = False,
    now: datetime | None = None,
) -> HealthScoreResponse:
    """Calculate once and persist current state, optionally a dated history row.

    The caller owns the transaction. A unique daily snapshot is first-write-wins.
    Redis is invalidated after a successful write; SQL is the reader's source.
    """
    response = calculate_health_score(db, university_id, now=now)
    values = {
        "university_id": university_id,
        "score": response.score,
        "status": response.status.value,
        "breakdown": response.breakdown.model_dump(mode="json"),
        "reasons": [r.model_dump(mode="json") for r in response.reasons],
        "input_counters": response.input_counters.model_dump(mode="json"),
        "calculated_at": response.calculated_at,
    }
    stmt = _insert(db, HealthScoreCurrent, values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=[HealthScoreCurrent.university_id],
        set_={key: value for key, value in values.items() if key != "university_id"},
    ))
    if create_snapshot:
        snapshot = {key: values[key] for key in (
            "university_id", "score", "status", "breakdown", "reasons", "calculated_at"
        )}
        snapshot.update(
            id=uuid.uuid4(),
            period_day=response.calculated_at.date(),
            trigger_event=trigger_event,
        )
        db.execute(_insert(db, HealthScoreSnapshot, snapshot).on_conflict_do_nothing(
            index_elements=[
                HealthScoreSnapshot.university_id,
                HealthScoreSnapshot.period_day,
                HealthScoreSnapshot.trigger_event,
            ]
        ))
    from app.modules.health_score.cache import invalidate_health_score

    invalidate_health_score(university_id)
    return response


def backfill_health_score_current(db: Session, *, batch_size: int = 100) -> int:
    """Restart-safe keyset backfill; commits each bounded batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    processed = 0
    after: uuid.UUID | None = None
    while True:
        stmt = select(University.id).order_by(University.id).limit(batch_size)
        if after is not None:
            stmt = stmt.where(University.id > after)
        ids = list(db.scalars(stmt))
        if not ids:
            break
        for university_id in ids:
            refresh_health_score(db, university_id, "backfill")
        db.commit()
        processed += len(ids)
        after = ids[-1]
    return processed


def backfill_health_scores(db: Session, *, batch_size: int = 100) -> int:
    """Compatibility name for the deployment backfill command.

    The explicit ``_current`` name documents the target projection; this
    public alias keeps existing rollout scripts stable.
    """
    return backfill_health_score_current(db, batch_size=batch_size)


def write_daily_snapshots(db: Session, *, day: date | None = None, batch_size: int = 100) -> int:
    """Refresh all universities and insert at most one daily row each UTC day.

    The worker holds a PostgreSQL advisory lock on this session's connection.
    Keyset batches avoid loading university ORM rows into memory.
    """
    day = day or datetime.now(timezone.utc).date()
    now = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    processed = 0
    after: uuid.UUID | None = None
    while True:
        stmt = select(University.id).order_by(University.id).limit(batch_size)
        if after is not None:
            stmt = stmt.where(University.id > after)
        ids = list(db.scalars(stmt))
        if not ids:
            break
        for university_id in ids:
            refresh_health_score(db, university_id, TRIGGER_DAILY_CRON,
                                 create_snapshot=True, now=now)
        db.flush()
        processed += len(ids)
        after = ids[-1]
    return processed


def run_daily_snapshot_once(db: Session, *, day: date | None = None) -> int:
    """Worker-owned UTC daily scheduler with a DB multi-replica lock."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        locked = bool(db.execute(text("SELECT pg_try_advisory_lock(24110901)")).scalar())
        if not locked:
            return 0
    try:
        return write_daily_snapshots(db, day=day)
    finally:
        if dialect == "postgresql":
            db.execute(text("SELECT pg_advisory_unlock(24110901)"))
            db.commit()
