"""Deterministic operational Health Score for university/program workflows."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any
from app.modules.workflow_instances.overdue import compute_overdue
from app.services.license_status import derive_license_status

# Centralized, reviewable penalties. Progress is deliberately not a factor.
BASE_SCORE = 100
PENALTIES = {
    "workflow_overdue": 25,
    "responsible_missing": 15,
    "overdue_task": 10,
    "expired_license": 20,
    "license_expires_soon": 10,
}
TASK_PENALTY_CAP = 20
UNIVERSITY_SCORE_CAPS = {"critical": 59, "attention": 84}
LEVELS = ((85, "stable"), (60, "attention"), (0, "critical"))

@dataclass(frozen=True)
class HealthFactor:
    type: str
    label: str
    severity: str
    detail: str | None = None

@dataclass(frozen=True)
class OperationalHealth:
    score: int | None
    level: str
    factors: tuple[HealthFactor, ...] = ()
    started: bool = False
    completed: bool = False


def health_level(score: int | None) -> str:
    if score is None:
        return "no_data"
    for threshold, level in LEVELS:
        if score >= threshold:
            return level
    return "critical"


def calculate_workflow_health(*, instance: Any, stage: Any | None, tasks: list[Any], licenses: list[Any], today: date) -> OperationalHealth:
    if instance.status == "completed":
        return OperationalHealth(BASE_SCORE, "stable", started=True, completed=True)
    score = BASE_SCORE
    factors: list[HealthFactor] = []
    if stage is not None:
        late, days = compute_overdue(stage.due_date, stage.completed_at, today)
        if late:
            score -= PENALTIES["workflow_overdue"]
            factors.append(HealthFactor("workflow_overdue", "Просрочен текущий этап", "critical", f"на {days} дн."))
        if stage.responsible_id is None and instance.responsible_id is None:
            score -= PENALTIES["responsible_missing"]
            factors.append(HealthFactor("responsible_missing", "Не назначен ответственный на текущий этап", "warning"))
    overdue_tasks = 0
    for task in tasks:
        late, days = compute_overdue(task.deadline, task.completed_at, today)
        if late and task.status not in {"completed", "cancelled"}:
            overdue_tasks += 1
    if overdue_tasks:
        score -= min(TASK_PENALTY_CAP, overdue_tasks * PENALTIES["overdue_task"])
        factors.append(HealthFactor("overdue_tasks", f"{overdue_tasks} просроченных задач", "critical"))
    # License is relevant only when an actual related license exists.
    statuses = [derive_license_status(getattr(license, "expires_at", None), today) for license in licenses]
    if "expired" in statuses:
        score -= PENALTIES["expired_license"]
        factors.append(HealthFactor("expired_license", "Просрочена лицензия", "critical"))
    elif "expires_soon" in statuses:
        score -= PENALTIES["license_expires_soon"]
        factors.append(HealthFactor("license_expires_soon", "Лицензия истекает в течение 30 дней", "warning"))
    return OperationalHealth(max(0, min(100, score)), health_level(max(0, min(100, score))), tuple(factors), started=True)


def aggregate_health(scores: list[int]) -> int | None:
    """Average only started/completed interactions; NOT_STARTED is excluded."""
    return round(sum(scores) / len(scores)) if scores else None
