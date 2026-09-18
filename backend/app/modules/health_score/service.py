"""Transparent formula (§12): 100 minus penalties. No ML."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.health_score.models import HealthScoreHistory

PENALTIES = {
    "overdue_task": 10,
    "missing_docs": 15,
    "stage_delay": 10,
    "teacher_training": 10,
    "missing_license": 15,
    "launch_delay": 15,
}

#: Signal keys consumed by :func:`compute_score` (subset of PENALTIES
#: excluding the overdue-task count, which is passed separately).
SIGNAL_KEYS = (
    "missing_docs",
    "stage_delay",
    "teacher_training",
    "missing_license",
    "launch_delay",
)


def compute_score(
    overdue_tasks: int = 0, signals: dict | None = None
) -> tuple[int, dict[str, str]]:
    """Pure Health Score formula (single source of truth, §12).

    No DB access, no writes — shared by ``HealthScoreService.calculate``
    (which persists the result) and read-only consumers such as the
    university passport ``?include=health_score`` block (which must NOT
    persist a row just for reading).
    """
    signals = signals or {}
    score = 100
    details: dict[str, str] = {}
    if overdue_tasks:
        penalty = min(overdue_tasks * PENALTIES["overdue_task"], 40)
        score -= penalty
        details["overdue_tasks"] = f"-{penalty} ({overdue_tasks} шт.)"
    for key in SIGNAL_KEYS:
        if signals.get(key):
            score -= PENALTIES[key]
            details[key] = f"-{PENALTIES[key]}"
    return max(0, min(100, score)), details


class HealthScoreService:
    def __init__(self, db: Session):
        self.db = db

    def calculate(self, university_id: int, signals: dict | None = None) -> HealthScoreHistory:
        # Local import: the legacy workflow tables are excluded from the
        # canonical SQL schema (int FKs, one pointing at a nonexistent
        # ``programs`` table), so they must never be registered on
        # Base.metadata as a side effect of importing this service.
        from app.modules.workflow.models import Task

        signals = signals or {}
        now = datetime.now(timezone.utc)
        overdue = (
            self.db.query(Task)
            .filter(
                Task.university_id == university_id,
                Task.status != "done",
                Task.deadline.is_not(None),
                Task.deadline < now,
            )
            .count()
        )
        score, details = compute_score(overdue_tasks=overdue, signals=signals)
        row = HealthScoreHistory(
            university_id=university_id,
            score=score,
            details_json=json.dumps(details, ensure_ascii=False),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def history(self, university_id: int) -> list[HealthScoreHistory]:
        return (
            self.db.query(HealthScoreHistory)
            .filter_by(university_id=university_id)
            .order_by(HealthScoreHistory.calculated_at)
            .limit(100)
            .all()
        )
