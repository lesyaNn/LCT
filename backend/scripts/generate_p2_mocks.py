"""Generate workflow-instance mock JSON for P3.

Usage (from ``backend/``)::

    python scripts/generate_p2_mocks.py [--out docs/mocks]

* ``workflow-instance.json`` — canonical ``InstanceDetail`` shape
  (``GET /api/v1/workflow/instances/{id}``) plus the transition history;
  validated against the real response schemas in tests.

Deterministic UUIDs (uuid5) and dates — output is stable across runs.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid


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
    parser = argparse.ArgumentParser(description="Generate workflow mock for P3")
    parser.add_argument("--out", default="docs/mocks")
    args = parser.parse_args()

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.out
    )
    os.makedirs(out, exist_ok=True)
    workflow_path = os.path.join(out, "workflow-instance.json")
    with open(workflow_path, "w", encoding="utf-8") as fh:
        json.dump(build_workflow_instance_mock(), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote {workflow_path}")


if __name__ == "__main__":
    main()
