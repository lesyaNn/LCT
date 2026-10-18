"""Personal-note API contracts plus PostgreSQL ownership/concurrency checks."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.note import Note
from app.modules.notes import service
from app.modules.notes.mentions import entity_mentions, resolve_record
from app.modules.notes.router import router
from app.modules.notes.schemas import NoteCreate, NoteUpdate
from app.modules.search import search
from app.schemas.errors import ErrorCode


@pytest.fixture(scope="module")
def pg():
    from tests.db_helpers import require_pg_engine
    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    yield engine
    engine.dispose()


@pytest.fixture()
def db(pg):
    with Session(pg) as session:
        yield session
        session.rollback()
        session.execute(delete(Note))
        session.commit()


def test_markdown_validation_and_reference_snippet():
    from pydantic import ValidationError
    assert service.snippet('## План\n\n**Текст** [Вуз](/notes/reference?kind=university)') == 'План Текст Вуз'
    for payload in ({"revision": -1}, {"revision": 0, "title": "x" * 301},
                    {"revision": 0, "content": "x" * 200001}, {"revision": 0, "owner_sub": "other"}):
        with pytest.raises(ValidationError):
            NoteUpdate(**payload)


def test_ordinary_user_directory_does_not_expose_other_identities():
    actor = CurrentUser(id=str(uuid.uuid4()), name="Анна", roles={"user"})
    assert entity_mentions(None, actor, "user", "Анна")[0].id == actor.id
    assert entity_mentions(None, actor, "user", "", str(uuid.uuid4())) == []
    assert entity_mentions(None, actor, "user", "Иван") == []


def test_reference_resolution_applies_scope_and_exact_id():
    class Db:
        def execute(self, stmt):
            self.statement = stmt
            return []
    from sqlalchemy.dialects import postgresql
    allowed, target = uuid.uuid4(), uuid.uuid4()
    actor = CurrentUser(id="alice", roles={"user"}, university_ids=(str(allowed),))
    for kind in ("university", "workflow", "document", "contract", "product", "responsible"):
        db = Db()
        assert resolve_record(db, actor, kind, target, allowed) == []
        compiled = db.statement.compile(dialect=postgresql.dialect())
        assert target in compiled.params.values()
        assert any(allowed in value for value in compiled.params.values() if isinstance(value, (list, tuple, set, frozenset)))


def test_crud_is_private_even_from_another_admin_and_creation_is_idempotent(db):
    data = NoteCreate(title="План", content="# Встреча\n\n- [ ] Задача")
    note = service.create(db, "alice", data)
    assert service.create(db, "alice", data).id == note.id
    for operation in (
        lambda: service.owned(db, "bob", note.id),
        lambda: service.create(db, "bob", data),
        lambda: service.save(db, "bob", note.id, NoteUpdate(title="Чужое", revision=0)),
        lambda: service.remove(db, "bob", note.id, 0),
    ):
        with pytest.raises(BusinessException) as error:
            operation()
        assert error.value.code == ErrorCode.NOT_FOUND
    assert service.list_notes(db, "bob", "", "updated_at", "desc", 0, 50).total == 0
    service.remove(db, "alice", note.id, 0)
    with pytest.raises(BusinessException):
        service.owned(db, "alice", note.id)


def test_stale_updates_and_deletes_cannot_overwrite_or_remove_newer_text(db, pg):
    note_id = service.create(db, "alice", NoteCreate(title="Начало")).id
    with Session(pg) as other:
        service.owned(other, "alice", note_id)  # Load before the competing commit.
        saved = service.save(db, "alice", note_id, NoteUpdate(title="Первый", content="Новый текст", revision=0))
        assert saved.revision == 1
        for operation in (
            lambda: service.save(other, "alice", note_id, NoteUpdate(title="Второй", revision=0)),
            lambda: service.remove(other, "alice", note_id, 0),
        ):
            with pytest.raises(BusinessException) as error:
                operation()
            assert error.value.code == ErrorCode.CONFLICT
    assert service.owned(db, "alice", note_id).content == "Новый текст"


def test_title_content_search_sort_pagination_and_literal_wildcards(db):
    first = service.create(db, "alice", NoteCreate(title="Первый", content="Встреча с вузом 100%"))
    first.created_at = datetime.now(UTC) - timedelta(days=2)
    first.updated_at = datetime.now(UTC) + timedelta(hours=1)
    db.commit()
    second = service.create(db, "alice", NoteCreate(title="Второй", content="Встреча"))
    assert service.list_notes(db, "alice", "первый", "updated_at", "desc", 0, 50).total == 1
    assert service.list_notes(db, "alice", "Встреча", "updated_at", "desc", 0, 50).total == 2
    assert service.list_notes(db, "alice", "100%", "updated_at", "desc", 0, 50).total == 1
    for field, order, expected in (("created_at", "asc", first.id), ("created_at", "desc", second.id),
                                   ("updated_at", "desc", first.id), ("updated_at", "asc", second.id)):
        page = service.list_notes(db, "alice", "", field, order, 0, 1)
        assert page.total == 2 and page.items[0].id == expected
        assert service.list_notes(db, "alice", "", field, order, 1, 1).items[0].id != expected


def test_global_search_uses_original_query_and_owner(db):
    service.create(db, "alice", NoteCreate(title="Мой план", content="Заметки для встречи с партнёрами"))
    service.create(db, "bob", NoteCreate(title="Секретный план", content="Заметки для встречи"))
    # Static aliases intentionally leave records_q empty. Notes still search q.
    result = search(db, CurrentUser(id="alice"), "встречи", records_q="")
    assert [hit.title for hit in result.notes] == ["Мой план"]
    assert result.notes[0].updated_at and "встречи" in result.notes[0].subtitle


def test_http_contract_validation_and_missing_foreign_id(db):
    actor = CurrentUser(id="alice", roles={"admin"})
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        created = client.post('/notes', json={"title": "Рабочая заметка", "content": "Текст"})
        assert created.status_code == 201
        note = created.json()
        actor.id = "bob"
        for response in (client.get(f'/notes/{note["id"]}'),
                         client.patch(f'/notes/{note["id"]}', json={"title": "Взлом", "revision": 0}),
                         client.delete(f'/notes/{note["id"]}?revision=0')):
            assert response.status_code == 404
        actor.id = "alice"
        assert client.patch(f'/notes/{note["id"]}', json={"title": "Изменено", "revision": 0}).json()['revision'] == 1
        assert client.patch(f'/notes/{note["id"]}', json={"title": "Старое", "revision": 0}).status_code == 409
        assert client.get('/notes?sort_by=content').status_code == 422
        assert client.get('/notes?limit=101').status_code == 422
        assert client.delete(f'/notes/{note["id"]}').status_code == 422
        assert client.delete(f'/notes/{note["id"]}?revision=1').status_code == 204
