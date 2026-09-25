"""Pure aggregations shared by overview/chart values and golden tests."""

from collections import Counter, defaultdict
from datetime import date

from app.db.seed_workflow import STAGES_14
from app.modules.analytics.repository import AnalyticsData
from app.modules.analytics.schemas import Matrix, Overview
from app.modules.workflow_instances.overdue import compute_overdue
from app.services.license_status import derive_license_status
from app.services.teacher_readiness import compute_teacher_readiness

LEGEND = {
    "not_used": "Программа не ведётся в вузе",
    "planned": "Запланирована к запуску",
    "in_progress": "В процессе внедрения",
    "launched": "Запущена и ведётся",
    "risk": "Под риском (просрочки/проблемы)",
    "archived": "Программа в архиве",
}
PROGRAM_STATUSES = ("planned", "active", "launched", "archived")
BUCKETS = (
    ("0-20", 0, 20),
    ("21-40", 21, 40),
    ("41-60", 41, 60),
    ("61-80", 61, 80),
    ("81-100", 81, 100),
)


def grouped(items, key):
    result = defaultdict(list)
    for item in items:
        result[key(item)].append(item)
    return result


def overdue_items(data: AnalyticsData, today: date) -> list[dict]:
    instances = {item.id: item for item in data.instances if item.status == "active"}
    universities = {item.id: item.name for item in data.universities}
    result = []
    for kind, items in (("stage", data.stages), ("task", data.tasks)):
        for item in items:
            instance = instances.get(item.instance_id)
            if instance is None or item.completed_at is not None:
                continue
            if item.status not in ({"pending", "current"} if kind == "stage" else {"open"}):
                continue
            due = item.due_date if kind == "stage" else item.deadline
            late, days = compute_overdue(due, None, today)
            if late:
                result.append(
                    {
                        "type": kind,
                        "university_id": instance.university_id,
                        "university": universities[instance.university_id],
                        kind: item.name if kind == "stage" else item.title,
                        "days_overdue": days,
                        "id": str(item.id),
                    }
                )
    return sorted(result, key=lambda row: (-row["days_overdue"], row["id"]))


def build_overview(data: AnalyticsData, *, today: date) -> Overview:
    values = [item.score for item in data.scores.values()]
    colors = Counter(getattr(item.status, "value", item.status) for item in data.scores.values())
    universities = {item.id: item.name for item in data.universities}
    instances = {item.id: item for item in data.instances if item.status == "active"}
    stages = defaultdict(set)
    for stage in data.stages:
        instance = instances.get(stage.instance_id)
        if instance and stage.status == "current":
            stages[stage.name].add(instance.university_id)
    names = [name for name, _ in STAGES_14]
    names += sorted(set(stages) - set(names))  # Keep real custom/retired snapshot labels.
    programs = Counter(item.status for item in data.links)
    licenses = []
    for item in data.licenses:
        if derive_license_status(item.expires_at, today) == "expires_soon":
            licenses.append(
                {
                    "university": universities[item.university_id],
                    "product": item.product.name,
                    "expires_at": item.expires_at,
                    "days_left": (item.expires_at - today).days,
                }
            )
    licenses.sort(key=lambda row: (row["expires_at"], row["university"], row["product"]))
    certs = grouped(data.certificates, lambda item: item.teacher_id)
    quals = grouped(data.qualifications, lambda item: item.teacher_id)
    warnings = []
    issues = 0
    for teacher in data.teachers:
        readiness = compute_teacher_readiness(certs[teacher.id], quals[teacher.id], today)
        issues += readiness.readiness.value != "ready"
        for item in certs[teacher.id] + quals[teacher.id]:
            if not getattr(item, "is_mandatory", True) or item.expires_at is None:
                continue
            days = (item.expires_at - today).days
            if days <= 30:
                warnings.append(
                    {
                        "university": universities[teacher.university_id],
                        "teacher": teacher.full_name,
                        "certificate": getattr(item, "certificate_name", None)
                        or item.qualification_name,
                        "expires_at": item.expires_at,
                        "days_left": days,
                    }
                )
    warnings.sort(key=lambda row: (row["expires_at"], row["teacher"], row["certificate"]))
    overdue = overdue_items(data, today)
    return Overview.model_validate(
        {
            "kpi": {
                "universities": len(data.universities),
                "average_health_score": round(sum(values) / len(values), 2) if values else 0,
                "red_universities": colors["red"],
                "yellow_universities": colors["yellow"],
                "green_universities": colors["green"],
                "overdue_stages": sum(item["type"] == "stage" for item in overdue),
                # KPI totals are NOT truncated to the top-10 detail lists.
                "expiring_licenses": len(licenses),
                "teacher_readiness_issues": issues,
                "active_programs": programs["active"],
                "launched_programs": programs["launched"],
            },
            "health_distribution": [
                {"range": label, "count": sum(lo <= n <= hi for n in values)}
                for label, lo, hi in BUCKETS
            ],
            "workflow_distribution": [
                {"stage": name, "count": len(stages[name])} for name in names
            ],
            "program_statuses": [
                {"status": status, "count": programs[status]} for status in PROGRAM_STATUSES
            ],
            "expiring_licenses": licenses[:10],
            "teacher_readiness": warnings[:10],
            "overdue_items": overdue[:10],
            "health_trend": data.trend,
        }
    )


def cell_status(program_status, score, overdue):
    if program_status is None:
        return "not_used", "none"
    risk = (
        "high"
        if overdue or (score is not None and score < 60)
        else "unknown"
        if score is None
        else "medium"
        if score < 85
        else "low"
    )
    status = "in_progress" if program_status == "active" else program_status
    if program_status in {"active", "launched"} and risk == "high":
        status = "risk"
    return status, risk


def build_matrix(data: AnalyticsData, *, today: date) -> Matrix:
    links = {(item.university_id, item.program_id): item for item in data.links}
    teachers = {item.id: item for item in data.teachers}
    assignments = grouped(
        data.teacher_programs,
        lambda item: (teachers[item.teacher_id].university_id, item.program_id),
    )
    certs = grouped(data.certificates, lambda item: item.teacher_id)
    quals = grouped(data.qualifications, lambda item: item.teacher_id)
    licenses = grouped(data.licenses, lambda item: (item.university_id, item.program_id))
    # WorkflowInstance has NO program_id in P2's canonical schema. Expose the
    # university context honestly, instead of fabricating a per-program join.
    active = {item.id: item for item in data.instances if item.status == "active"}
    stages = grouped(
        [item for item in data.stages if item.instance_id in active],
        lambda item: active[item.instance_id].university_id,
    )
    overdue = Counter(item["university_id"] for item in overdue_items(data, today))
    contexts = {}
    for university in data.universities:
        runtime = stages[university.id]
        eligible = [item for item in runtime if item.status != "skipped"]
        progress = (
            round(sum(item.status == "completed" for item in eligible) / len(eligible) * 100, 2)
            if eligible
            else None
        )
        current = sorted(
            [item for item in runtime if item.status == "current"],
            key=lambda item: (item.due_date or date.max, str(item.id)),
        )
        milestone = None
        if current:
            item = current[0]
            milestone = item.name
            if item.due_date:
                milestone += f" ({(item.due_date - today).days} дней)"
        contexts[university.id] = progress, milestone
    cells = []
    for university in sorted(data.universities, key=lambda item: (item.name, str(item.id))):
        for program in sorted(data.programs, key=lambda item: (item.name, str(item.id))):
            pair = university.id, program.id
            link = links.get(pair)
            # A real association excluded by Dev-1's filter is NOT not_used.
            if link is None and pair in data.existing_pairs:
                continue
            score = data.scores.get(university.id)
            score = score.score if score and link else None
            late = overdue[university.id] if link else 0
            status, risk = cell_status(link.status if link else None, score, late)
            readiness = None
            assignment = assignments[pair]
            if link and assignment:
                ready = 0
                for item in assignment:
                    relevant = [
                        cert
                        for cert in certs[item.teacher_id]
                        if cert.program_id in (None, program.id)
                    ]
                    ready += (
                        item.can_teach
                        and compute_teacher_readiness(
                            relevant, quals[item.teacher_id], today
                        ).readiness.value
                        == "ready"
                    )
                readiness = round(ready / len(assignment) * 100, 2)
            license_status = None
            if link and licenses[pair]:
                license_status = min(
                    (derive_license_status(item.expires_at, today) for item in licenses[pair]),
                    key=("expired", "expires_soon", "active").index,
                )
            progress, milestone = contexts[university.id] if link else (None, None)
            cells.append(
                {
                    "university_id": university.id,
                    "program_id": program.id,
                    "status": status,
                    "health_score": score,
                    "risk_level": risk,
                    "teacher_readiness": readiness,
                    "license_status": license_status,
                    "workflow_progress": progress,
                    "overdue_count": late,
                    "next_milestone": milestone,
                }
            )
    return Matrix.model_validate(
        {
            "rows": [
                {"id": item.id, "name": item.name, "city": item.city}
                for item in sorted(data.universities, key=lambda item: (item.name, str(item.id)))
            ],
            "columns": [
                {"id": item.id, "name": item.name, "direction": item.direction.name}
                for item in sorted(data.programs, key=lambda item: (item.name, str(item.id)))
            ],
            "cells": cells,
            "legend": LEGEND,
        }
    )
