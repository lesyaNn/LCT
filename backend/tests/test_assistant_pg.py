"""Real PostgreSQL persistence, ownership and concurrent-turn regression tests."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import BusinessException
from app.models.assistant import AssistantConversation, AssistantTurn
from app.modules.assistant.repository import Conversations
from app.modules.assistant.schemas import ChatIn
from app.modules.assistant.service import Assistant
from app.schemas.errors import ErrorCode
from tests.test_assistant import build_knowledge, fake_provider


@pytest.fixture()
def knowledge(tmp_path):
    return build_knowledge(tmp_path)


@pytest.fixture()
def pg():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    try:
        yield engine
    finally:
        engine.dispose()


def make_chat(db, knowledge, subject="alice", role="user"):
    config = Settings(assistant_enabled=True)
    repository = Conversations(db, subject, role, config)
    assistant = Assistant(config, knowledge, fake_provider())
    return assistant, repository


def test_json_history_is_durable_paginated_and_deleted_with_children(pg, knowledge):
    with Session(pg) as db:
        assistant, repository = make_chat(db, knowledge)
        first = assistant.chat(ChatIn(message="Как вернуть этап?"), "user", repository)
        second = assistant.chat(
            ChatIn(message="А причина обязательна?", conversation_id=first.conversation_id),
            "user",
            repository,
        )
        assert second.revision == 2
    with Session(pg) as db:
        repository = Conversations(db, "alice", "user", Settings())
        assert repository.list(1, 20).total == 1
        history = repository.history(first.conversation_id, 2, 1)
        assert history.total == 2 and history.items[0].revision == 2
        assert history.items[0].question == "А причина обязательна?"
        assert history.items[0].sources
        repository.remove(first.conversation_id)
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0
        assert repository.list(1, 20).total == 0


@pytest.mark.parametrize("subject,role", [("bob", "user"), ("bob", "admin"), ("alice", "manager")])
def test_other_subject_or_changed_role_cannot_access_history(pg, knowledge, subject, role):
    with Session(pg) as db:
        assistant, repository = make_chat(db, knowledge)
        first = assistant.chat(ChatIn(message="Вернуть этап"), "user", repository)
        stranger = Conversations(db, subject, role, Settings())
        assert stranger.list(1, 20).total == 0
        for operation in (
            lambda: stranger.history(first.conversation_id, 1, 20),
            lambda: stranger.prepare(
                ChatIn(message="Продолжить", conversation_id=first.conversation_id)
            ),
            lambda: stranger.remove(first.conversation_id),
        ):
            with pytest.raises(BusinessException) as raised:
                operation()
            assert raised.value.code == ErrorCode.NOT_FOUND
            db.rollback()


def test_concurrent_replies_cannot_overwrite_or_duplicate_turns(pg, knowledge):
    with Session(pg) as db:
        assistant, repository = make_chat(db, knowledge)
        initial = assistant.chat(ChatIn(message="Вернуть этап"), "user", repository)
    with Session(pg) as left, Session(pg) as right:
        a = Conversations(left, "alice", "user", Settings())
        b = Conversations(right, "alice", "user", Settings())
        data = ChatIn(message="Следующий вопрос", conversation_id=initial.conversation_id)
        first = a.prepare(data)
        second = b.prepare(data)
        result = initial.model_copy(update={"revision": 2, "created_at": datetime.now(UTC)})
        from uuid import uuid4

        result.turn_id = uuid4()
        a.save(first, data.message, result)
        with pytest.raises(BusinessException) as raised:
            b.save(second, data.message, result.model_copy(update={"turn_id": uuid4()}))
        assert raised.value.code == ErrorCode.CONFLICT
        assert left.scalar(select(func.count()).select_from(AssistantTurn)) == 2


def test_failed_model_leaves_no_partial_conversation(pg, knowledge):
    with Session(pg) as db:
        config = Settings(assistant_enabled=True)
        provider = Mock()
        provider.chat.side_effect = BusinessException(ErrorCode.ASSISTANT_TIMEOUT)
        assistant = Assistant(config, knowledge, provider)
        with pytest.raises(BusinessException):
            assistant.chat(
                ChatIn(message="Вернуть этап"), "user", Conversations(db, "alice", "user", config)
            )
        assert db.scalar(select(func.count()).select_from(AssistantConversation)) == 0
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0


def test_expired_conversations_are_hidden_but_can_be_deleted(pg, knowledge):
    with Session(pg) as db:
        assistant, repository = make_chat(db, knowledge)
        first = assistant.chat(ChatIn(message="Вернуть этап"), "user", repository)
        row = db.get(AssistantConversation, first.conversation_id)
        row.updated_at = datetime.now(UTC) - timedelta(days=31)
        db.commit()
        assert repository.list(1, 20).total == 0
        with pytest.raises(BusinessException) as raised:
            repository.history(first.conversation_id, 1, 20)
        assert raised.value.code == ErrorCode.NOT_FOUND
        db.rollback()
        repository.remove(first.conversation_id)
