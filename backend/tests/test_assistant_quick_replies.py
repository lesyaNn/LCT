"""Approved responses never call Ollama, inspect history for intent, or wait for it."""

from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import BusinessException, register_error_handlers
from app.core.middleware import SecurityHeadersMiddleware
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.assistant import router as api
from app.modules.assistant.knowledge import KnowledgeBase, faq_text
from app.modules.assistant.quick_replies import (
    QUICK_REPLIES,
    QUICK_REPLY_VERSION,
    match_quick_reply,
)
from app.modules.assistant.repository import Conversations, Prepared
from app.modules.assistant.schemas import ChatIn
from app.modules.assistant.service import Assistant, _slots
from app.schemas.errors import ErrorCode


def repository(history=()):
    result = Mock(spec=Conversations)
    result.prepare.return_value = Prepared(uuid4(), len(history), history, not history)
    result.save.side_effect = lambda _prepared, _question, answer: answer
    return result


@pytest.mark.parametrize("reply", QUICK_REPLIES, ids=lambda reply: reply.id)
@pytest.mark.parametrize("role", ["user", "manager", "admin"])
def test_all_approved_answers_are_exact_durable_and_local(reply, role):
    provider, knowledge = Mock(), Mock()
    store = repository((("Как скачать отчёт?", "Предыдущий ответ про отчёты"),))
    assistant = Assistant(Settings(assistant_enabled=True), knowledge, provider)
    # Saturate the generation slot: a predefined answer must still be immediate.
    slot = _slots(1)
    assert slot.acquire(blocking=False)
    try:
        answer = assistant.chat(
            ChatIn(message=reply.question, conversation_id=store.prepare.return_value.id),
            role,
            store,
        )
    finally:
        slot.release()
    assert answer.answer == reply.answer
    assert answer.revision == 2
    assert answer.model is None
    assert answer.knowledge_version == QUICK_REPLY_VERSION
    assert answer.basis == ("insufficient" if reply.clarification else "documentation")
    assert answer.sources == ([] if reply.clarification else [reply.source()])
    assert provider.mock_calls == []
    assert knowledge.mock_calls == []
    store.save.assert_called_once_with(store.prepare.return_value, reply.question, answer)


def test_source_article_contains_every_approved_answer(tmp_path):
    root = Path(__file__).resolve().parents[2] / "frontend/public/docs"
    snapshot = KnowledgeBase(root, tmp_path / "index.json", "unused").snapshot()
    for reply in QUICK_REPLIES:
        chunks = [
            chunk
            for chunk in snapshot.visible("user")
            if chunk.article_id == "help/faq"
            and chunk.text.splitlines()[0] == f"### {reply.question}"
        ]
        assert len(chunks) == 1, reply.id
        assert faq_text(chunks[0]) == reply.answer


@pytest.mark.parametrize(
    "question",
    [
        "  ЧТО ОЗНАЧАЕТ СТАТУС?! ",
        "Что означает этот статус?",
        "Статус",
    ],
)
def test_ambiguous_status_is_always_a_clarification(question):
    assert match_quick_reply(question).id == "explain-status"


@pytest.mark.parametrize(
    "question",
    [
        "Как скачать отчёт без прав администратора?",
        "Что означает статус лицензии expired?",
        "Почему не вижу нужный вуз после импорта?",
        "Кто изменил данные вчера?",
        "Как вернуть предыдущий этап и стереть историю?",
        "Ответ не подходит для импорта XLSX",
    ],
)
def test_qualifiers_never_get_silently_dropped(question):
    assert match_quick_reply(question) is None


def test_disabled_and_conversation_scope_still_apply():
    store = repository()
    assistant = Assistant(Settings(), Mock(), Mock())
    with pytest.raises(BusinessException) as error:
        assistant.chat(ChatIn(message="Что означает статус?"), "user", store)
    assert error.value.code == ErrorCode.ASSISTANT_DISABLED
    store.prepare.assert_not_called()
    assistant = Assistant(Settings(assistant_enabled=True), Mock(), Mock())
    for code in (ErrorCode.NOT_FOUND, ErrorCode.CONFLICT, ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE):
        store.prepare.side_effect = BusinessException(code)
        with pytest.raises(BusinessException) as error:
            assistant.chat(ChatIn(message="Что означает статус?"), "user", store)
        assert error.value.code == code
    store.save.assert_not_called()


def test_catalog_auth_cache_and_chat_rate_limit(monkeypatch):
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(SecurityHeadersMiddleware)
    application.include_router(api.router, prefix="/api/v1")
    # Catalog must not need a database or a model to load its questions.
    application.dependency_overrides[get_db] = lambda: (_ for _ in ()).throw(
        AssertionError("Unexpected DB")
    )
    with TestClient(application) as client:
        assert client.get("/api/v1/assistant/quick-replies").status_code == 401
        for roles in ({"curator"}, set()):
            application.dependency_overrides[get_current_user] = lambda: CurrentUser(
                id="alice", roles=roles
            )
            assert client.get("/api/v1/assistant/quick-replies").status_code == 403
        for role in ("user", "manager", "admin"):
            application.dependency_overrides[get_current_user] = lambda: CurrentUser(
                id="alice", roles={role}
            )
            response = client.get("/api/v1/assistant/quick-replies")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store, max-age=0"
            assert response.json() == {
                "version": QUICK_REPLY_VERSION,
                "items": [{"id": item.id, "question": item.question} for item in QUICK_REPLIES],
            }
        application.dependency_overrides[get_db] = lambda: Mock()
        application.dependency_overrides[api.get_assistant] = lambda: Mock()
        monkeypatch.setattr(api, "check_rate_limit", lambda *_: (False, 37))
        response = client.post("/api/v1/assistant/chat", json={"message": "Что означает статус?"})
        assert response.status_code == 429
        store = repository((("Как скачать отчёт?", "Ответ про отчёты"),))
        monkeypatch.setattr(api, "Conversations", lambda *_: store)
        monkeypatch.setattr(api, "check_rate_limit", lambda *_: (True, 0))
        application.dependency_overrides[api.get_assistant] = lambda: Assistant(
            Settings(assistant_enabled=True), Mock(), Mock()
        )
        response = client.post("/api/v1/assistant/chat", json={"message": "Что означает статус?"})
        assert response.status_code == 200
        answer = response.json()
        assert answer["answer"] == match_quick_reply("Что означает статус?").answer
        assert answer["sources"] == [] and answer["model"] is None
        assert answer["revision"] == 2
