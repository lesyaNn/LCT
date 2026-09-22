"""Generate P3 mock JSON for P2 (P2-12-01): workflow-instance + health-score.

Usage (from ``backend/``)::

    python scripts/generate_p2_mocks.py [--out docs/mocks]

* ``health-score.json`` — REAL ``HealthScoreResponse`` from
  ``health_service.calculate_health_score`` on a seeded problem-zone
  university (nontrivial reasons) — guaranteed schema-conformant.
* ``workflow-instance.json`` — canonical ``InstanceDetail`` shape
  (``GET /api/v1/workflow/instances/{id}``) plus the transition history;
  validated against the real response schemas in tests.

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
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowStageTransition,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowTemplate, WorkflowStage
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
        id=_uid("template/std"), name="Стандартный цикл",
    )
    db.add(template)
    db.flush()
    tpl_ids = []
    for index, name in enumerate(STAGE_NAMES, start=1):
        stage = WorkflowStage(
            id=_uid(f"template-stage/{index}"), template_id=template.id,
            name=name, order_index=index,
        )
        db.add(stage)
        tpl_ids.append(stage.id)
    db.flush()

    instance_id = _uid("instance/mgu")
    instance = WorkflowInstance(
        id=instance_id, template_id=template.id, university_id=uni_id,
        status="active",
    )
    db.add(instance)
    db.flush()

    # 5 completed вовремя/поздно + текущий pending + будущий pending
    completions = [
        ("completed", date(2026, 1, 22), datetime(2026, 1, 20, 14, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 2, 5), datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 3, 1), datetime(2026, 3, 5, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 4, 1), datetime(2026, 3, 30, 11, 0, tzinfo=timezone.utc)),
        ("completed", date(2026, 5, 1), datetime(2026, 4, 28, 11, 0, tzinfo=timezone.utc)),
        ("pending", date(2026, 9, 20), None),
        ("pending", date(2026, 9, 27), None),
    ]
    stage_ids = []
    for index, (status, due, done) in enumerate(completions, start=1):
        sid = _uid(f"instance-stage/{index}")
        stage_ids.append(sid)
        db.add(InstanceStage(
            id=sid, instance_id=instance_id, template_stage_id=tpl_ids[index - 1],
            order_index=index, name=STAGE_NAMES[index - 1],
            status=status, due_date=due, completed_at=done,
        ))
    db.flush()
    # Указатели — после снапшотов (FK требует существующих строк).
    instance.current_stage_id = tpl_ids[5]
    instance.current_instance_stage_id = _uid("instance-stage/6")
    db.flush()
    # 3 просроченные задачи у текущего этапа
    for num in range(3):
        db.add(WorkflowTask(
            id=_uid(f"task/{num}"), instance_id=instance_id,
            stage_id=tpl_ids[5], title=f"Задача {num + 1}",
            deadline=(MOCK_NOW - timedelta(days=num + 1)).date(), status="open",
            priority="normal",
        ))
    db.add(WorkflowStageTransition(
        id=_uid("transition/1"), instance_id=instance_id,
        from_stage_id=tpl_ids[4], to_stage_id=tpl_ids[5],
        actor_keycloak_sub="mock",
        comment="Пилот успешен, переходим к подписанию",
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
    """Канонический InstanceDetail + история переходов (контракт GET)."""
    uni_id = _uid("university/mgu")
    template_id = _uid("template/std")
    instance_id = _uid("instance/mgu")
    current_tpl = _uid("template-stage/6")
    current_row = _uid("instance-stage/6")
    stages = []
    due_dates = ["2026-01-22", "2026-02-05", "2026-03-01", "2026-04-01",
                 "2026-05-01", "2026-09-20", "2026-09-27"]
    done_dates = ["2026-01-20T14:00:00+03:00", "2026-02-03T11:00:00+03:00",
                  "2026-03-05T11:00:00+03:00", "2026-03-30T11:00:00+03:00",
                  "2026-04-28T11:00:00+03:00", None, None]
    statuses = ["completed"] * 5 + ["pending", "pending"]
    for index, name in enumerate(STAGE_NAMES, start=1):
        stages.append({
            "id": str(_uid(f"instance-stage/{index}")),
            "template_stage_id": str(_uid(f"template-stage/{index}")),
            "order_index": index,
            "name": name,
            "description": None,
            "is_required": index != 5,
            "status": statuses[index - 1],
            "due_date": due_dates[index - 1],
            "completed_at": done_dates[index - 1],
            "is_overdue": False,
            "days_overdue": 0,
            "created_at": "2026-01-15T10:00:00+03:00",
            "updated_at": done_dates[index - 1] or "2026-01-15T10:00:00+03:00",
        })
    return {
        "id": str(instance_id),
        "university_id": str(uni_id),
        "template_id": str(template_id),
        "current_stage_id": str(current_tpl),
        "current_instance_stage_id": str(current_row),
        "responsible_id": None,
        "status": "active",
        "due_date": "2026-09-27",
        "completed_at": None,
        "is_overdue": False,
        "days_overdue": 0,
        "created_at": "2026-01-15T10:00:00+03:00",
        "updated_at": "2026-09-10T09:00:00+03:00",
        "stages": stages,
        "transitions": [
            {
                "id": str(_uid("transition/1")),
                "instance_id": str(instance_id),
                "from_stage_id": str(_uid("template-stage/5")),
                "to_stage_id": str(current_tpl),
                "actor_keycloak_sub": "mock",
                "comment": "Пилот успешен, переходим к подписанию",
                "created_at": "2026-09-10T09:00:00+03:00",
                "updated_at": "2026-09-10T09:00:00+03:00",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate P2 mocks for P3")
    parser.add_argument("--out", default="docs/mocks")
    parser.add_argument(
        "--db-url", default=os.getenv("TEST_DATABASE_URL", ""),
        help="PostgreSQL URL (SQL migrations are the sole schema source; "
        "no SQLite DDL path). Falls back to TEST_DATABASE_URL.",
    )
    args = parser.parse_args()
    if not args.db_url.startswith("postgresql"):
        raise SystemExit(
            "generate_p2_mocks needs --db-url=postgresql+psycopg://... "
            "(canonical SQL schema; SQLite cannot express DEFERRABLE)."
        )

    eng = create_engine(args.db_url)
    # Scratch database: canonical schema (no-op if migrated), seed, calc.
    # Test databases are schema-reset by tests/db_helpers.py afterwards.
    Base.metadata.create_all(eng, checkfirst=True)
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
