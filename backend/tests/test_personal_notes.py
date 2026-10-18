"""Focused API checks for durable, private notes and save conflicts."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.personal_note import NoteFolder, PersonalNote


def test_personal_notes_owner_search_folder_revision_and_trash():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    NoteFolder.metadata.create_all(engine, tables=[NoteFolder.__table__, PersonalNote.__table__])
    current = [CurrentUser(id="alice", roles={"user"})]

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: current[0]
    try:
        with TestClient(app) as client:
            folder = client.post("/api/v1/notes/folders", json={"name": "Работа"})
            assert folder.status_code == 201
            folder_id = folder.json()["id"]
            created = client.post("/api/v1/notes", json={"title": "Встреча", "content": "- [ ] Позвонить", "folder_id": folder_id})
            assert created.status_code == 201
            note_id = created.json()["id"]
            assert created.json()["revision"] == 0
            saved = client.patch(f"/api/v1/notes/{note_id}", json={"revision": 0, "content": "- [x] Позвонить"})
            assert saved.status_code == 200
            assert saved.json()["revision"] == 1
            assert client.patch(f"/api/v1/notes/{note_id}", json={"revision": 0, "title": "Устаревшее"}).status_code == 409
            found = client.get("/api/v1/notes", params={"q": "ПОЗВ"})
            assert found.status_code == 200 and found.json()["total"] == 1
            assert client.get("/api/v1/notes", params={"folder_id": folder_id}).json()["total"] == 1
            links = client.post("/api/v1/notes/resolve-links", json={"hrefs": [f"/notes?note={note_id}", "javascript:alert(1)", "/reports"]})
            assert links.status_code == 200
            assert [item["available"] for item in links.json()] == [True, False, True]

            current[0] = CurrentUser(id="bob", roles={"manager"})
            assert client.get("/api/v1/notes").json()["total"] == 0
            assert client.get(f"/api/v1/notes/{note_id}").status_code == 404
            assert client.patch(f"/api/v1/notes/{note_id}", json={"revision": 1, "title": "Чужое"}).status_code == 404
            assert client.get("/api/v1/notes/folders").json() == []
            assert client.post("/api/v1/notes/resolve-links", json={"hrefs": [f"/notes?note={note_id}"]}).json()[0]["available"] is False
            assert client.post("/api/v1/notes", json={"title": "Запись менеджера"}).status_code == 201
            assert client.get("/api/v1/notes").json()["total"] == 1
            current[0] = CurrentUser(id="charlie", roles={"admin"})
            assert client.get("/api/v1/notes").json()["total"] == 0
            assert client.post("/api/v1/notes", json={"title": "Запись администратора"}).status_code == 201
            current[0] = CurrentUser(id="alice", roles={"user"})
            assert client.delete(f"/api/v1/notes/{note_id}").status_code == 204
            assert client.get(f"/api/v1/notes/{note_id}").status_code == 404
            assert client.get("/api/v1/notes", params={"view": "trash"}).json()["total"] == 1
            assert client.post(f"/api/v1/notes/{note_id}/restore").status_code == 200
            assert client.get(f"/api/v1/notes/{note_id}").json()["content"] == "- [x] Позвонить"
            assert client.delete(f"/api/v1/notes/folders/{folder_id}").status_code == 204
            assert client.get(f"/api/v1/notes/{note_id}").json()["folder_id"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
