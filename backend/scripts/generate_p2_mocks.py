"""Generate P3 mock JSON for P2 (P2-12-01): workflow-instance + health-score.

Usage (from ``backend/``)::

    python scripts/generate_p2_mocks.py [--out docs/mocks]

* ``health-score.json`` — REAL ``HealthScoreResponse`` from
  ``health_service.calculate_health_score`` on a seeded problem-zone
  university (nontrivial reasons) — guaranteed schema-conformant.
* ``workflow-instance.json`` — P3-oriented demo shape from the task file
  (7 stages, mixed statuses, transitions); structural key checks in tests.

Deterministic UUIDs (uuid5) and dates — output is stable across runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import University
from app.models.interactions import Document
from app.models.workflow import (
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTask,
    WorkflowTemplate,
    WorkflowTemplateStage,
    WorkflowTransition,
)
from app.modules.health_score.health_service import calculate_health_score

MOCK_DAY = date(2026, 9, 15)
MOCK_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _uid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"rtk-mock/{name}")


STAGE_NAMES = [
    "Поиск контактов",
    "Коммуникация/актуальность программ",
    "Встреча",
    "Обмен документами",
    "Корректировка документов",
    "Подписание документов",
    "Передача материалов",
]


def _seed_problem_university(db: Session) -> uuid.UUID:
    """Вуз с живыми проблемами: просрочки, документы, этапы (для reasons)."""
    uni_id = _uid("university/mgu")
    uni = University(id=uni_id, name="МГУ", city="Москва")
    db.add(uni)
    db.flush()

    template = WorkflowTemplate(
        id=_uid("template/std"), code="standard", name="Стандартный цикл",
        created_by_keycloak_sub="mock",
    )
    db.add(template)
    db.flush()
    tpl_ids = []
    for index, name in enumerate(STAGE_NAMES):
        stage = WorkflowTemplateStage(
            id=_uid(f"template-stage/{index}"), template_id=template.id,
            code=f"s{index + 1}", name=name, order_index=index,
        )
        db.add(stage)
        tpl_ids.append(stage.id)
    db.flush()

    instance_id = _uid("instance/mgu")
    instance = WorkflowInstance(
        id=instance_id, template_id=template.id, university_id=uni_id,
        status="active", started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        created_by_keycloak_sub="mock", updated_by_keycloak_sub="mock",
    )
    db.add(instance)
    db.flush()

    # 5 completed вовремя/поздно + current + pending
    completions = [
        ("completed", date(2026, 1, 22), datetime(2026, 1, 20, 14, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 2, 5), datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 3, 1), datetime(2026, 3, 5, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 4, 1), datetime(2026, 3, 30, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 5, 1), datetime(2026, 4, 28, 11, 0, tzinfo=timezone.utc)),
        ("current", date(2026, 9, 20), None),
        ("pending", date(2026, 9, 27), None),
    ]
    stage_ids = []
    for index, (status, due, done) in enumerate(completions):
        due_dt = datetime(due.year, due.month, due.day, tzinfo=timezone.utc)
        sid = _uid(f"instance-stage/{index}")
        stage_ids.append(sid)
        db.add(WorkflowInstanceStage(
            id=sid, instance_id=instance_id, template_stage_id=tpl_ids[index],
            order_index=index, status=status, due_date=due_dt,
            started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
            if status != "pending" else None,
            completed_at=done,
        ))
    # 3 просроченные обычные задачи на current-этапе
    for num in range(3):
        db.add(WorkflowTask(
            id=_uid(f"task/{num}"), instance_id=instance_id,
            instance_stage_id=stage_ids[5], title=f"Задача {num + 1}",
            due_date=MOCK_NOW - timedelta(days=num + 1), status="open",
            priority="normal", created_by_keycloak_sub="mock",
        ))
    db.add(WorkflowTransition(
        id=_uid("transition/1"), instance_id=instance_id,
        from_stage_id=stage_ids[4], to_stage_id=stage_ids[5],
        action="next", actor_keycloak_sub="mock",
        comment="Документы согласованы", revision=5, created_at=MOCK_NOW,
    ))
    # Документы: 3 valid + 1 просроченный
    for num, (doc_type, expired) in enumerate(
        [("contract", False), ("license", False), ("act", False), ("protocol", True)]
    ):
        db.add(Document(
            id=_uid(f"document/{num}"), university_id=uni_id,
            document_type=doc_type, title=f"Документ {num}",
            file_path=f"/mock/{num}", file_name=f"doc{num}.pdf",
            status_raw="signed",
            expires_at=MOCK_DAY - timedelta(days=1) if expired else None,
            uploaded_by_keycloak_sub="mock",
        ))
    db.flush()
    return uni_id


def build_workflow_instance_mock() -> dict:
    """P3-формат из файла задачи (имена, счётчики, переходы)."""
    uni_id = _uid("university/mgu")
    template_id = _uid("template/std")
    instance_id = _uid("instance/mgu")
    stages = []
    due_dates = ["2026-01-22", "2026-02-05", None, None, None, "2026-09-20", "2026-09-27"]
    statuses = ["completed"] * 5 + ["current", "pending"]
    for index, name in enumerate(STAGE_NAMES):
        stages.append({
            "id": str(_uid(f"instance-stage/{index}")),
            "stage_id": str(_uid(f"template-stage/{index}")),
            "stage_name": name,
            "order_index": index + 1,
            "status": statuses[index],
            "due_date": due_dates[index],
            "completed_at": (
                ["2026-01-20T14:00:00+03:00", "2026-02-03T11:00:00+03:00", None,
                 None, None, None, None][index]
            ),
            "started_at": "2026-01-15T10:00:00+03:00" if index < 6 else None,
            "overdue": False,
            "days_overdue": None,
            "assignee_name": "Иванов И.И." if index == 5 else None,
            "comments_count": 2 if index == 0 else (1 if index == 5 else 0),
            "attachments_count": 1 if index == 0 else 0,
            "tasks_count": 3 if index == 5 else 0,
        })
    return {
        "id": str(instance_id),
        "university_id": str(uni_id),
        "university_name": "МГУ",
        "template_id": str(template_id),
        "template_name": "Стандартный цикл",
        "current_stage_id": str(_uid("instance-stage/5")),
        "current_stage_name": "Подписание документов",
        "status": "active",
        "started_at": "2026-01-15T10:00:00+03:00",
        "completed_at": None,
        "progress_percent": 45,
        "overdue_stages_count": 1,
        "stages": stages,
        "transitions": [
            {
                "from_stage": "Корректировка документов",
                "to_stage": "Подписание документов",
                "user_name": "Петров П.П.",
                "comment": "Документы согласованы",
                "transitioned_at": "2026-09-10T09:00:00+03:00",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate P2 mocks for P3")
    parser.add_argument("--out", default="docs/mocks")
    args = parser.parse_args()

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as db:
        uni_id = _seed_problem_university(db)
        db.commit()
        response = calculate_health_score(db, uni_id, MOCK_DAY, MOCK_NOW)
    eng.dispose()

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.out
    )
    os.makedirs(out, exist_ok=True)
    health_path = os.path.join(out, "health-score.json")
    with open(health_path, "w", encoding="utf-8") as fh:
        json.dump(response.model_dump(mode="json"), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    workflow_path = os.path.join(out, "workflow-instance.json")
    with open(workflow_path, "w", encoding="utf-8") as fh:
        json.dump(build_workflow_instance_mock(), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {health_path} (score={response.score})")
    print(f"wrote {workflow_path}")


if __name__ == "__main__":
    main()
