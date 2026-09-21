"""P2-08-02: batch endpoint — HTTP тесты (порядок, пропуск, лимиты)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.modules.health_score import cache as health_cache


@pytest.fixture()
def client(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/hsb.db")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)

    def _override():
        with Session(eng) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-sub", roles={"admin"}
    )
    ids = [uuid4(), uuid4()]
    with Session(eng) as session:
        session.add_all([
            University(id=ids[0], name="Вуз B-1"),
            University(id=ids[1], name="Вуз B-2"),
        ])
        session.commit()
    try:
        yield TestClient(app, raise_server_exceptions=False), ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        eng.dispose()


def test_batch_order_and_skip_missing(client):
    http, (first, second) = client
    missing = uuid4()
    r = http.get(f"/api/v1/universities/health-score?ids={second},{missing},{first}")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["university_id"] for i in items] == [str(second), str(first)]
    assert all(set(i["breakdown"]) == {"tasks", "documents", "stages", "teachers", "launch"} for i in items)
    assert all("reasons" not in i for i in items)  # короткий вид
    for uid in (first, second):
        health_cache.invalidate_health_score(uid)


def test_batch_422_empty_invalid_too_many(client):
    http, (first, _) = client
    assert http.get("/api/v1/universities/health-score?ids=").status_code == 422
    assert http.get("/api/v1/universities/health-score?ids=not-a-uuid").status_code == 422
    many = ",".join(str(uuid4()) for _ in range(51))
    assert http.get(f"/api/v1/universities/health-score?ids={many}").status_code == 422
