"""Real HTTP CRUD and conflict policy on a dedicated migrated PostgreSQL test DB."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app


def test_documented_university_crud_and_conflict(seeded_db):
    engine = seeded_db.get_bind()
    old = app.dependency_overrides.copy()

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="service-api-test", roles={"admin"}
    )
    try:
        with TestClient(app) as client:
            catalog = client.get("/api/v1/service-api")
            assert catalog.status_code == 200
            created = client.post(
                "/api/v1/universities", json={"name": "API CRUD test", "city": "Москва"}
            )
            assert created.status_code == 201, created.text
            path = "/api/v1/universities/" + created.json()["id"]
            assert client.get(path).json()["name"] == "API CRUD test"
            patched = client.patch(path, json={"city": "Казань"})
            assert patched.status_code == 200, patched.text
            assert patched.json()["city"] == "Казань"
            assert patched.json()["name"] == "API CRUD test"
            meeting = client.post(
                path + "/meetings",
                json={
                    "subject": "API contract test",
                    "meeting_at": "2026-10-20T10:00:00+03:00",
                },
            )
            assert meeting.status_code == 201, meeting.text
            conflict = client.delete(path)
            assert conflict.status_code == 409, conflict.text
            assert client.get(path).status_code == 200
            assert client.delete("/api/v1/meetings/" + meeting.json()["id"]).status_code == 204
            removed = client.delete(path)
            assert removed.status_code == 204, removed.text
            assert removed.content == b""
            assert client.get(path).status_code == 404
            assert client.delete(path).status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old)
