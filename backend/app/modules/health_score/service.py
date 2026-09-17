"""Transparent formula (§12): 100 minus penalties. No ML."""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.health_score.models import HealthScoreHistory
from app.modules.workflow.models import Task

PENALTIES = {
    "overdue_task": 10,
    "missing_docs": 15,
    "stage_delay": 10,
    "teacher_training": 10,
    "missing_license": 15,
    "launch_delay": 15,
}


class HealthScoreService:
    def __init__(self, db: Session):
        self.db = db

    def calculate(self, university_id: int, signals: dict | None = None) -> HealthScoreHistory:
        signals = signals or {}
        now = datetime.now(timezone.utc)
        overdue = self.db.query(Task).filter(
            Task.university_id == university_id,
            Task.status != "done",
            Task.deadline.is_not(None),
            Task.deadline < now,
        ).count()
        details: dict[str, int | str] = {}
        score = 100
        if overdue:
            penalty = min(overdue * PENALTIES["overdue_task"], 40)
            score -= penalty
            details["overdue_tasks"] = f"-{penalty} ({overdue} шт.)"
        for key in ["missing_docs", "stage_delay", "teacher_training", "missing_license", "launch_delay"]:
            if signals.get(key):
                score -= PENALTIES[key]
                details[key] = f"-{PENALTIES[key]}"
        score = max(0, min(100, score))
        row = HealthScoreHistory(university_id=university_id, score=score,
                                 details_json=json.dumps(details, ensure_ascii=False))
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def history(self, university_id: int) -> list[HealthScoreHistory]:
        return (self.db.query(HealthScoreHistory)
                .filter_by(university_id=university_id)
                .order_by(HealthScoreHistory.calculated_at).limit(100).all())
