"""Pure aggregations (without students/teachers/health score)."""

from collections import Counter, defaultdict
from datetime import date

from app.db.seed_workflow import STAGES_14
from app.modules.analytics.repository import AnalyticsData
from app.modules.analytics.schemas import Matrix, Overview
from app.modules.workflow_instances.overdue import compute_overdue
from app.services.license_status import derive_license_status

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
    active = {item.id: item for item in data.instances if item.status == "active"}
    stages = grouped([item for item in data.stages if item.instance_id in active],
        lambda item: active[item.instance_id].university_id)
    overdue = Counter(item["university_id"] for item in overdue_items(data, today))
    contexts = {}
    for university in data.universities:
        runtime = stages[university.id]
        eligible = [item for item in runtime if item.status != "skipped"]
        progress = (round(sum(item.status == "completed" for item in eligible) / len(eligible) * 100, 2) if eligible else None)
        current = sorted([item for item in runtime if item.status == "current"],
            key=lambda item: (item.due_date or date.max, str(item.id)))
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
            if link is None and pair in data.existing_pairs:
                continue
            late = overdue[university.id] if link else 0
            status, risk = cell_status(link.status if link else None, late)
            license_status = None
            if link and licenses[pair]:
                license_status = min((derive_license_status(i.expires_at, today) for i in licenses[pair]),
                    key=("expired", "expires_soon", "active").index)
            progress, milestone = contexts[university.id] if link else (None, None)
            cells.append({"university_id": university.id, "program_id": program.id,
                "status": status, "risk_level": risk, "license_status": license_status,
                "workflow_progress": progress, "overdue_count": late, "next_milestone": milestone})
    return Matrix.model_validate({"rows": [{"id": i.id, "name": i.name, "city": i.city}
        for i in sorted(data.universities, key=lambda i: (i.name, str(i.id)))],
        "columns": [{"id": i.id, "name": i.name, "direction": i.direction.name}
        for i in sorted(data.programs, key=lambda i: (i.name, str(i.id)))],
        "cells": cells, "legend": LEGEND})
