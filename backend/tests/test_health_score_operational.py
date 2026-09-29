from datetime import date, timedelta
from types import SimpleNamespace

from app.modules.health_score.operational import calculate_workflow_health


def test_overdue_current_stage_reduces_score_and_exposes_factor():
    instance = SimpleNamespace(status="active", responsible_id=object())
    stage = SimpleNamespace(
        due_date=date.today() - timedelta(days=3),
        completed_at=None,
        responsible_id=object(),
    )

    result = calculate_workflow_health(
        instance=instance, stage=stage, tasks=[], licenses=[], today=date.today()
    )

    assert result.score == 75
    assert result.score < 100
    assert any(factor.type == "workflow_overdue" for factor in result.factors)
    assert result.level == "attention"
