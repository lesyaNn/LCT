import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace as Row

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.modules.analytics import router
from app.modules.analytics.integration import (
    Selection,
    UnfilteredProvider,
    data_scope,
    restrict_selection,
)
from app.modules.analytics.repository import AnalyticsData
from app.modules.analytics.service import build_matrix, build_overview, cell_status
from tests.p4_dev2_data import TODAY, golden_data, uid

GOLDEN = json.loads((Path(__file__).parent / "fixtures/p4_dev2_golden.json").read_text())


@pytest.mark.parametrize("case", GOLDEN, ids=lambda case: case["name"])
def test_three_fixed_golden_selections(case):
    data = golden_data(case["universities"])
    overview = build_overview(data, today=TODAY)
    assert overview.kpi.model_dump() == case["expected"]
    assert [item.count for item in overview.health_distribution] == case["health_buckets"]
    assert [item.count for item in overview.program_statuses] == case["program_counts"]
    assert len(overview.workflow_distribution) == 14
    assert sum(item.count for item in overview.workflow_distribution) == len(case["universities"])
    assert overview.health_trend[0].avg_score == case["expected"]["average_health_score"]
    matrix = build_matrix(data, today=TODAY)
    assert sorted(item.status for item in matrix.cells) == sorted(case["matrix_statuses"])
    assert len(matrix.rows) == overview.kpi.universities


def test_empty_data_keeps_zero_buckets():
    result = build_overview(AnalyticsData(), today=TODAY)
    assert result.kpi.universities == 0
    assert len(result.health_distribution) == 5
    assert len(result.workflow_distribution) == 14
    assert len(result.program_statuses) == 4
    assert result.health_trend == []


def test_totals_not_top10_and_expired_not_expiring():
    data = golden_data([1])
    data.licenses = [
        Row(
            university_id=uid(1),
            program_id=uid(11),
            product=Row(name=str(i)),
            expires_at=TODAY + timedelta(days=i),
        )
        for i in range(-1, 32)
    ]
    result = build_overview(data, today=TODAY)
    assert result.kpi.expiring_licenses == 31  # today through +30, not yesterday/+31
    assert len(result.expiring_licenses) == 10
    assert result.expiring_licenses[0].days_left == 0


def test_closed_and_skipped_not_overdue_and_tasks_in_union():
    data = golden_data()
    data.stages[1].status = "skipped"
    data.stages[1].due_date = TODAY - timedelta(days=20)
    result = build_overview(data, today=TODAY)
    assert result.kpi.overdue_stages == 2
    assert result.overdue_items[0].type == "task"
    assert result.overdue_items[0].days_overdue == 6
    data.instances[-1].status = "completed"
    result = build_overview(data, today=TODAY)
    assert result.kpi.overdue_stages == 1
    assert all(item.type == "stage" for item in result.overdue_items)


def test_matrix_indicators_are_real_and_not_used_has_no_context():
    data = golden_data([1])
    data.teachers = [Row(id=uid(700), university_id=uid(1), full_name="Преподаватель")]
    data.teacher_programs = [Row(teacher_id=uid(700), program_id=uid(11), can_teach=False)]
    data.certificates = [
        Row(
            teacher_id=uid(700),
            program_id=uid(12),
            is_mandatory=True,
            certificate_name="Другая программа",
            expires_at=TODAY - timedelta(days=1),
        )
    ]
    result = build_matrix(data, today=TODAY)
    cell = next(item for item in result.cells if item.program_id == uid(11))
    assert cell.teacher_readiness == 0  # can_teach=False
    data.teacher_programs[0].can_teach = True
    cell = next(
        item for item in build_matrix(data, today=TODAY).cells if item.program_id == uid(11)
    )
    assert cell.teacher_readiness == 100  # irrelevant certificate does not poison readiness
    assert cell.license_status == "expires_soon"
    assert cell.workflow_progress == 50
    assert cell.next_milestone.endswith("(2 дней)")
    assert cell.workflow_scope == "university"
    data.links = data.links[:1]
    data.existing_pairs = {(uid(1), uid(11))}
    unused = next(
        item for item in build_matrix(data, today=TODAY).cells if item.program_id == uid(12)
    )
    assert unused.status == "not_used"
    assert unused.workflow_progress is None and unused.next_milestone is None


def test_filtered_out_association_is_not_fabricated_as_not_used():
    data = golden_data([1])
    data.links = data.links[:1]
    result = build_matrix(data, today=TODAY)
    assert len(result.cells) == 1


@pytest.mark.parametrize(
    "status,score,late,expected,risk",
    [
        (None, None, 0, "not_used", "none"),
        ("planned", 40, 0, "planned", "high"),
        ("active", 85, 0, "in_progress", "low"),
        ("active", 84, 0, "in_progress", "medium"),
        ("launched", 60, 0, "launched", "medium"),
        ("launched", 59, 0, "risk", "high"),
        ("active", 100, 1, "risk", "high"),
        ("archived", 90, 0, "archived", "low"),
    ],
)
def test_matrix_status_boundaries(status, score, late, expected, risk):
    assert cell_status(status, score, late) == (expected, risk)


def test_missing_filter_provider_never_ignores_a_filter():
    provider = UnfilteredProvider()
    assert provider.normalize({"university_ids": [], "date_from": None}) == {}
    for value in ({"university_ids": [str(uid(1))]}, {"date_from": "2026-01-01"}):
        with pytest.raises(HTTPException) as exc:
            provider.normalize(value)
        assert exc.value.status_code == 503
    with pytest.raises(HTTPException) as exc:
        provider.normalize({"typo": []})
    assert exc.value.status_code == 422


def test_scope_does_not_broaden_and_cache_is_isolated():
    user = CurrentUser(id="a", roles={"user"}, university_ids=(str(uid(1)),))
    assert data_scope(user) == (uid(1),)
    assert restrict_selection(Selection(university_ids=[uid(1), uid(2)]), ()).university_ids == []
    assert (
        restrict_selection(Selection(university_ids=[uid(2)]), data_scope(user)).university_ids
        == []
    )
    with pytest.raises(HTTPException):
        data_scope(CurrentUser(id="a", roles={"user"}))
    provider = UnfilteredProvider()
    key = router.cache_key("overview", {}, user, data_scope(user), provider, TODAY)
    assert key != router.cache_key("overview", {}, user, None, provider, TODAY)
    assert key != router.cache_key("overview", {}, user, (), provider, TODAY)


def test_cache_hit_and_filter_http_contract(monkeypatch):
    admin = CurrentUser(id="admin", roles={"admin"})
    cache = {}
    calls = []
    provider = UnfilteredProvider()
    monkeypatch.setattr(provider, "select", lambda *args: Selection())
    monkeypatch.setattr(router, "load_data", lambda *a, **kw: calls.append(1) or AnalyticsData())
    monkeypatch.setattr(router.cache, "cache_get", cache.get)
    monkeypatch.setattr(
        router.cache, "cache_set", lambda key, value, ttl: cache.update({key: value})
    )
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.update(
        {
            get_current_user: lambda: admin,
            get_db: lambda: None,
            router.get_filter_provider: lambda: provider,
        }
    )
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/analytics/overview").status_code == 200
            assert client.get("/api/v1/analytics/overview").status_code == 200
            assert len(calls) == 1
            assert client.get("/api/v1/analytics/overview?typo=x").status_code == 422
            assert (
                client.get(f"/api/v1/analytics/overview?university_ids={uid(1)}").status_code == 503
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
