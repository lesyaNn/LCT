"""P2-08-01: endpoint health-score — HTTP тесты (404/200/кэш)."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.modules.health_score import cache as health_cache

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def client():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)

    def _override():
        with Session(eng) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-sub", roles={"admin"}
    )
    with Session(eng) as session:
        session.add(University(id=uuid4(), name="Вуз HS-1"))
        session.commit()
        uni_id = session.query(University).first().id
    try:
        yield TestClient(app, raise_server_exceptions=False), uni_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        eng.dispose()


def test_404_unknown_university(client):
    http, _ = client
    r = http.get(f"/api/v1/universities/{uuid4()}/health-score")
    assert r.status_code == 404


def test_200_full_shape_and_cache(client):
    http, uni_id = client
    health_cache.invalidate_health_score(uni_id)
    first = http.get(f"/api/v1/universities/{uni_id}/health-score")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["score"] == 100
    assert body["status"] == "green"
    assert set(body["breakdown"]) == {"tasks", "documents", "stages", "teachers", "launch"}
    assert body["reasons"] == []
    assert body["input_counters"]["overdue_critical_tasks"] == 0
    # Второй запрос — из кэша (тот же calculated_at).
    second = http.get(f"/api/v1/universities/{uni_id}/health-score")
    assert second.status_code == 200
    assert second.json()["calculated_at"] == body["calculated_at"]
    health_cache.invalidate_health_score(uni_id)


def test_403_without_permission(client):
    http, uni_id = client
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="nobody", roles=set()
    )
    try:
        r = http.get(f"/api/v1/universities/{uni_id}/health-score")
        assert r.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id="test-sub", roles={"admin"}
        )
