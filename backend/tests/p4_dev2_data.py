"""Small immutable-in-time golden fixture; does not modify P1's demo seed.

P2 scores are fixed inputs to aggregation unit tests, not a new score formula.
P4-12 cross-export verification remains gated on Dev-1's real provider/exporters.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as Row
from uuid import UUID

from app.db.seed_workflow import STAGES_14
from app.modules.analytics.repository import AnalyticsData

TODAY = date(2026, 9, 23)


def uid(number):
    return UUID(int=number)


def golden_data(uni_ids=(1, 2, 3)):
    universities = [Row(id=uid(i), name=f"Вуз {i}", city="Москва") for i in uni_ids]
    programs = [
        Row(id=uid(11), name="Информатика", direction=Row(name="ИТ")),
        Row(id=uid(12), name="Безопасность", direction=Row(name="ИТ")),
    ]
    raw_links = [(1, 11, "launched"), (1, 12, "planned"), (2, 11, "active"), (3, 12, "active")]
    links = [
        Row(id=uid(100 + n), university_id=uid(u), program_id=uid(p), status=status)
        for n, (u, p, status) in enumerate(raw_links)
        if u in uni_ids
    ]
    licenses = [
        Row(
            id=uid(200 + n),
            university_id=uid(u),
            program_id=uid(p),
            expires_at=TODAY + timedelta(days=(n + 1) * 10),
            product=Row(name=f"Продукт {n}"),
        )
        for n, (u, p, _) in enumerate(raw_links)
        if u in uni_ids
    ]
    instances = [Row(id=uid(300 + i), university_id=uid(i), status="active") for i in uni_ids]
    stages = []
    for i in uni_ids:
        stages.extend(
            [
                Row(
                    id=uid(400 + i),
                    instance_id=uid(300 + i),
                    status="completed",
                    name=STAGES_14[0][0],
                    due_date=TODAY - timedelta(days=5),
                    completed_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
                ),
                Row(
                    id=uid(500 + i),
                    instance_id=uid(300 + i),
                    status="current",
                    name=STAGES_14[1][0],
                    due_date=TODAY + timedelta(days=2 if i == 1 else -i),
                    completed_at=None,
                ),
            ]
        )
    tasks = (
        [
            Row(
                id=uid(601),
                instance_id=uid(303),
                status="open",
                title="Подписать",
                deadline=TODAY - timedelta(days=6),
                completed_at=None,
            )
        ]
        if 3 in uni_ids
        else []
    )
    return AnalyticsData(
        universities=universities,
        programs=programs,
        links=links,
        existing_pairs={(item.university_id, item.program_id) for item in links},
        licenses=licenses,
        instances=instances,
        stages=stages,
        tasks=tasks,
        scores={
            uid(i): Row(
                score={1: 90, 2: 70, 3: 40}[i], status={1: "green", 2: "yellow", 3: "red"}[i]
            )
            for i in uni_ids
        },
        trend=[
            {
                "date": TODAY,
                "avg_score": round(
                    sum({1: 90, 2: 70, 3: 40}[i] for i in uni_ids) / len(uni_ids), 2
                ),
            }
        ],
    )
