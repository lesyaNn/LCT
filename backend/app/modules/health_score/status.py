"""P2-07-07: маппинг итогового Health Score на статус green/yellow/red.

Тривиальная детерминированная функция — single source of truth для всех
потребителей (P2-07-01 агрегация, P2-08-01 endpoint, P3 бейджи, P4 аналитика).

Пороги (заморожены ТЗ, меняются только вместе с контрактом):
* ``green`` — 85–100;
* ``yellow`` — 60–84;
* ``red`` — 0–59.

``HealthScoreStatus`` определён в ``app.schemas.common`` (P1-02-04) и здесь
только реэкспортируется для коротких импортов внутри health_score домена::

    from app.modules.health_score.status import get_health_status
"""

from app.schemas.common import HealthScoreStatus

#: Нижняя граница зелёной зоны (включительно).
GREEN_THRESHOLD = 85
#: Нижняя граница жёлтой зоны (включительно); всё ниже — red.
YELLOW_THRESHOLD = 60

__all__ = [
    "GREEN_THRESHOLD",
    "YELLOW_THRESHOLD",
    "HealthScoreStatus",
    "get_health_status",
]


def get_health_status(score: int) -> HealthScoreStatus:
    """Смаппить итоговый score 0–100 на статус Health Score.

    Args:
        score: Итоговый балл Health Score (ожидается 0–100; значения вне
            диапазона маппятся по тем же порогам: ``>= 85`` → green,
            ``>= 60`` → yellow, иначе red).

    Returns:
        ``HealthScoreStatus.GREEN`` при ``score >= 85``,
        ``HealthScoreStatus.YELLOW`` при ``score >= 60``,
        иначе ``HealthScoreStatus.RED``.

    Examples:
        >>> get_health_status(100)
        <HealthScoreStatus.GREEN: 'green'>
        >>> get_health_status(84)
        <HealthScoreStatus.YELLOW: 'yellow'>
        >>> get_health_status(59)
        <HealthScoreStatus.RED: 'red'>
    """
    if score >= GREEN_THRESHOLD:
        return HealthScoreStatus.GREEN
    if score >= YELLOW_THRESHOLD:
        return HealthScoreStatus.YELLOW
    return HealthScoreStatus.RED
