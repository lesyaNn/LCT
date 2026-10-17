"""Focused search authorization and query bounds without a database reset."""

import uuid
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.core.security import CurrentUser
from app.modules import search as module
from app.modules.assistant.knowledge import KnowledgeBase


class EmptyDb:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return []


def test_scoped_search_filters_every_data_query(monkeypatch):
    allowed = uuid.uuid4()
    user = CurrentUser(roles={"user"}, university_ids=(str(allowed),))
    db = EmptyDb()
    calls = []

    def university_list(_db, **kwargs):
        calls.append(kwargs)
        return [SimpleNamespace(id=allowed, name="Доступный вуз", city="Москва")], 1

    monkeypatch.setattr(module, "list_universities", university_list)
    found = module.search(db, user, "вуз")
    assert [item.title for item in found.universities] == ["Доступный вуз"]
    assert calls[0]["user"] is user
    assert calls[0]["search"] == "вуз"
    assert calls[0]["page_size"] == module.LIMIT
    assert len(db.statements) == 5
    for statement in db.statements:
        compiled = statement.compile(dialect=postgresql.dialect())
        assert any(allowed in value for value in compiled.params.values() if isinstance(value, (list, tuple, set, frozenset)))
        assert " LIMIT " in str(compiled)


def test_admin_and_empty_or_unprivileged_queries(monkeypatch):
    db = EmptyDb()
    monkeypatch.setattr(module, "list_universities", lambda _db, **kwargs: ([], 0))
    module.search(db, CurrentUser(roles={"admin"}), "ИТМО")
    assert len(db.statements) == 5
    assert all("university_id IN" not in str(statement) for statement in db.statements)

    no_access = EmptyDb()
    assert module.search(no_access, CurrentUser(roles=set()), "ИТМО") == module.SearchResults()
    assert no_access.statements == []
    assert module.search(no_access, CurrentUser(roles={"user"}), " ") == module.SearchResults()
    assert no_access.statements == []


def test_router_query_limit_and_whitespace():
    assert module.global_search(q=" ", db=EmptyDb(), user=CurrentUser(roles={"admin"})) == module.SearchResults()


def test_documentation_content_search_respects_roles_and_skips_record_queries(monkeypatch, tmp_path):
    root = tmp_path / "docs"
    (root / "user-guide").mkdir(parents=True)
    (root / "admin-guide").mkdir(parents=True)
    (root / "user-guide" / "history.md").write_text(
        "---\nsection: user-guide\nslug: history\ntitle: История изменений\n---\n\n"
        "Маршрут действий доступен в истории вуза.", encoding="utf-8",
    )
    (root / "admin-guide" / "users.md").write_text(
        "---\nsection: admin-guide\nslug: users\ntitle: Пользователи\n---\n\n"
        "Сбросить пароль пользователя.", encoding="utf-8",
    )
    knowledge = KnowledgeBase(root, tmp_path / "index.json", "test")
    monkeypatch.setattr(module, "get_knowledge", lambda _settings: knowledge)
    db = EmptyDb()
    regular = CurrentUser(roles={"user"})
    found = module.search(db, regular, "маршр", records_q="")
    assert [(hit.title, hit.href) for hit in found.documentation] == [
        ("История изменений", "/docs?article=user-guide%2Fhistory")
    ]
    assert module.search(db, regular, "пароль", records_q="").documentation == []
    assert module.search(db, CurrentUser(roles={"admin"}), "пароль", records_q="").documentation[0].title == "Пользователи"
    assert db.statements == []


def test_documents_and_contracts_can_match_visible_university_name(monkeypatch):
    db = EmptyDb()
    monkeypatch.setattr(module, "list_universities", lambda _db, **kwargs: ([], 0))
    module.search(db, CurrentUser(roles={"admin"}), "ИТМО")
    assert all("universities.name" in str(statement) for statement in db.statements[:2])


def test_missing_scope_fails_closed_for_all_entities(monkeypatch):
    db = EmptyDb()
    monkeypatch.setattr(module, "list_universities", lambda _db, **kwargs: ([], 0))
    assert module.search(db, CurrentUser(roles={"user"}), "ИТМО") == module.SearchResults()
    assert len(db.statements) == 5
    assert all(" false" in str(statement).lower() for statement in db.statements)


def test_http_query_bounds_and_normalized_response(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.security import get_current_user
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles={"admin"})
    app.dependency_overrides[get_db] = lambda: EmptyDb()
    monkeypatch.setattr(module, "search", lambda _db, _user, q, _records_q: module.SearchResults(
        universities=[module.SearchHit(id=uuid.uuid4(), title=q)]
    ))
    client = TestClient(app)
    assert client.get('/search', params={'q': 'ИТМО'}).json()['universities'][0]['title'] == 'ИТМО'
    assert client.get('/search', params={'q': 'a' * 101}).status_code == 422
