"""P2-12-01: моки для P3 — валидация файлов (схемы + структура)."""

import json
import os

from app.modules.health_score.schemas import HealthScoreResponse
from app.modules.workflow_instances.schemas import InstanceDetail
from app.modules.workflow_transitions.schemas import WorkflowStageTransitionRead

MOCKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "mocks"
)


def _load(name: str) -> dict:
    path = os.path.join(MOCKS_DIR, name)
    assert os.path.exists(path), f"mock missing: {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_health_score_mock_matches_schema():
    data = _load("health-score.json")
    resp = HealthScoreResponse.model_validate(data)
    assert resp.score == 88
    assert resp.status == "green"
    assert set(resp.breakdown.model_dump()) == {
        "tasks", "documents", "stages", "teachers", "launch"}
    assert len(resp.reasons) >= 2  # ненулевые reasons для P3
    assert resp.input_counters.overdue_normal_tasks == 3


def test_workflow_instance_mock_structure():
    data = _load("workflow-instance.json")
    # Мок повторяет контракт GET /api/v1/workflow/instances/{id} (+ history).
    detail = InstanceDetail.model_validate(data)
    assert detail.status == "active"
    assert len(detail.stages) == 7
    assert [s.order_index for s in detail.stages] == [1, 2, 3, 4, 5, 6, 7]
    statuses = {stage.status for stage in detail.stages}
    assert statuses == {"completed", "pending"}
    current = next(s for s in detail.stages if s.id == detail.current_instance_stage_id)
    assert current.name == "Подписание документов"
    assert current.status == "pending"
    assert detail.current_stage_id == current.template_stage_id
    transitions = [WorkflowStageTransitionRead.model_validate(t) for t in data["transitions"]]
    assert transitions[0].to_stage_id == current.template_stage_id
    assert transitions[0].comment != ""
