"""P2-07-07: пороги green/yellow/red."""

from app.modules.health_score.status import (
    GREEN_THRESHOLD,
    YELLOW_THRESHOLD,
    get_health_status,
)
from app.schemas.common import HealthScoreStatus


def test_thresholds_frozen():
    assert GREEN_THRESHOLD == 85
    assert YELLOW_THRESHOLD == 60


def test_green_zone():
    assert get_health_status(100) == HealthScoreStatus.GREEN
    assert get_health_status(85) == HealthScoreStatus.GREEN


def test_yellow_zone():
    assert get_health_status(84) == HealthScoreStatus.YELLOW
    assert get_health_status(60) == HealthScoreStatus.YELLOW


def test_red_zone():
    assert get_health_status(59) == HealthScoreStatus.RED
    assert get_health_status(0) == HealthScoreStatus.RED
