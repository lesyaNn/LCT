"""Pure aggregations over the loaded selection."""

from collections import Counter, defaultdict
from datetime import date

from app.db.seed_workflow import STAGES_14
from app.modules.analytics.repository import AnalyticsData
from app.modules.analytics.schemas import Matrix, Overview
from app.modules.workflow_instances.overdue import compute_overdue
from app.services.license_status import derive_license_status
from app.modules.health_score.operational import aggregate_health, calculate_workflow_health, health_level

LEGEND = {
    "not_used": "Программа не ведётся в вузе",
    "planned": "Запланирована к запуску",
    "in_progress": "В процессе внедрения",
    "launched": "Запущена и ведётся",
    "risk": "Под риском (просрочки/проблемы)",
    "archived": "Программа в архиве",
}
PROGRAM_STATUSES = ("planned", "active", "launched", "archived")


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
                result.append({"type": kind, "university_id": instance.university_id,
                    "university": universities[instance.university_id],
                    kind: item.name if kind == "stage" else item.title,
                    "days_overdue": days, "id": str(item.id)})
    return sorted(result, key=lambda row: (-row["days_overdue"], row["id"]))


def build_overview(data: AnalyticsData, *, today: date) -> Overview:
    universities = {item.id: item.name for item in data.universities}
    instances = {item.id: item for item in data.instances if item.status == "active"}
    stages = defaultdict(set)
    for stage in data.stages:
        instance = instances.get(stage.instance_id)
        if instance and stage.status == "current":
            stages[stage.name].add(instance.university_id)
    names = [name for name, _ in STAGES_14]
    names += sorted(set(stages) - set(names))
    programs = Counter(item.status for item in data.links)
    licenses = []
    for item in data.licenses:
        if derive_license_status(item.expires_at, today) == "expires_soon":
            licenses.append({"university": universities[item.university_id],
                "product": item.product.name, "expires_at": item.expires_at,
                "days_left": (item.expires_at - today).days})
    licenses.sort(key=lambda row: (row["expires_at"], row["university"], row["product"]))
    overdue = overdue_items(data, today)
    launch_months = [(today.year * 12 + today.month - 1 - offset) for offset in range(11, -1, -1)]
    launches = Counter((link.launch_date.year * 12 + link.launch_date.month - 1, link.status)
        for link in data.links if getattr(link, "launch_date", None) is not None)
    return Overview.model_validate({
        "kpi": {"universities": len(data.universities),
            "overdue_stages": sum(item["type"] == "stage" for item in overdue),
            "expiring_licenses": len(licenses),
            "active_programs": programs["active"], "launched_programs": programs["launched"]},
        "workflow_distribution": [{"stage": name, "count": len(stages[name])} for name in names],
        "program_statuses": [{"status": s, "count": programs[s]} for s in PROGRAM_STATUSES],
        "expiring_licenses": licenses[:10],
        "overdue_items": overdue[:10],
        "health_trend": [],
        "launch_dynamics": [{"month": f"{m // 12:04d}-{m % 12 + 1:02d}",
            "actual": launches[(m, "launched")], "planned": launches[(m, "planned")]} for m in launch_months],
    })


def cell_status(program_status, overdue):
    if program_status is None:
        return "not_used", "none"
    risk = "high" if overdue else "low"
    status = "in_progress" if program_status == "active" else program_status
    if program_status in {"active", "launched"} and risk == "high":
        status = "risk"
    return status, risk


def build_matrix(data: AnalyticsData, *, today: date) -> Matrix:
    links = {(item.university_id, item.program_id): item for item in data.links}
    licenses = grouped(data.licenses, lambda item: (item.university_id, item.program_id))
    instances = {(item.university_id, item.program_id): item for item in data.instances if item.program_id is not None and item.status != "archived"}
    stages = grouped(data.stages, lambda item: item.instance_id)
    tasks = grouped(data.tasks, lambda item: item.instance_id)
    cells = []
    row_health = {}
    for university in sorted(data.universities, key=lambda item: (item.name, str(item.id))):
        scores = []
        started = 0
        total = sum(1 for link in data.existing_pairs if link[0] == university.id)
        for program in sorted(data.programs, key=lambda item: (item.name, str(item.id))):
            pair = university.id, program.id
            link = links.get(pair)
            instance = instances.get(pair)
            if link is None:
                cells.append({"university_id": university.id, "program_id": program.id,
                    "status": "not_used", "health_state": "NOT_LINKED", "health_score": None,
                    "health_level": "no_data", "health_factors": [], "risk_level": "none",
                    "license_status": None, "workflow_progress": None, "overdue_count": 0, "next_milestone": None})
                continue
            total = max(total, 1)
            if instance is None:
                cells.append({"university_id": university.id, "program_id": program.id,
                    "status": "planned", "health_state": "NOT_STARTED", "health_score": None,
                    "health_level": "no_data", "health_factors": [], "risk_level": "none",
                    "license_status": None, "workflow_progress": None, "overdue_count": 0, "next_milestone": None})
                continue
            started += 1
            current = next((stage for stage in stages[instance.id] if stage.status == "current"), None)
            health = calculate_workflow_health(instance=instance, stage=current, tasks=tasks[instance.id], licenses=licenses[pair], today=today)
            scores.append(health.score or 0)
            state = "COMPLETED" if health.completed else {"stable": "HEALTHY", "attention": "ATTENTION", "critical": "CRITICAL"}[health.level]
            old_status = "launched" if link.status == "launched" else "in_progress" if link.status == "active" else link.status
            late_count = sum(compute_overdue(t.deadline, t.completed_at, today)[0] for t in tasks[instance.id])
            cells.append({"university_id": university.id, "program_id": program.id, "status": old_status,
                "health_state": state, "health_score": health.score, "health_level": health.level,
                "workflow_instance_id": instance.id,
                "health_factors": [factor.label for factor in health.factors], "risk_level": "high" if health.level == "critical" else "low" if health.level == "attention" else "none",
                "license_status": next((status for status in ("expired", "expires_soon", "active") if status in [derive_license_status(getattr(item, "expires_at", None), today) for item in licenses[pair]]), None),
                "workflow_progress": None, "overdue_count": late_count,
                "next_milestone": current.name if current else None})
        score = aggregate_health(scores)
        row_health[university.id] = (score, health_level(score), started, total)
    return Matrix.model_validate({"rows": [{"id": i.id, "name": i.name, "city": i.city,
        "health_score": row_health[i.id][0], "health_level": row_health[i.id][1],
        "started_programs": row_health[i.id][2], "total_programs": row_health[i.id][3]}
        for i in sorted(data.universities, key=lambda i: (i.name, str(i.id)))],
        "columns": [{"id": i.id, "name": i.name, "direction": i.direction.name}
        for i in sorted(data.programs, key=lambda i: (i.name, str(i.id)))], "cells": cells, "legend": {
            "HEALTHY": "Стабильно", "ATTENTION": "Требует внимания", "CRITICAL": "Критично",
            "NOT_STARTED": "Workflow не запущен", "COMPLETED": "Завершён", "NOT_LINKED": "Нет связи"}})
