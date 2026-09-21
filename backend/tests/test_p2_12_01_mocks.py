"""P2-12-01: моки для P3 — валидация файлов (схемы + структура)."""

import json
import os

from app.modules.health_score.schemas import HealthScoreResponse

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
    for key in ("id", "university_id", "university_name", "template_name",
                "current_stage_name", "status", "stages", "transitions"):
        assert key in data, key
    assert len(data["stages"]) == 7
    statuses = {stage["status"] for stage in data["stages"]}
    assert {"completed", "current", "pending"} <= statuses
    assert data["stages"][5]["stage_name"] == "Подписание документов"
    assert data["transitions"][0]["to_stage"] == "Подписание документов"
