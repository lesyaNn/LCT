"""Opt-in real Ollama and PostgreSQL checks, never a production database."""

import json
import os
import time

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.modules.assistant.greetings import GREETING_ANSWER
from app.modules.assistant.knowledge import get_knowledge
from app.modules.assistant.provider import Ollama
from app.modules.assistant.repository import Conversations
from app.modules.assistant.schemas import ChatIn
from app.modules.assistant.service import INSUFFICIENT, Assistant

pytestmark = pytest.mark.skipif(os.getenv("ASSISTANT_LIVE_TEST") != "1", reason="explicit local-model opt-in required")


@pytest.fixture(scope="module")
def live():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", ""))
    config = Settings(assistant_enabled=True)
    assistant = Assistant(config, get_knowledge(config), Ollama(config))
    yield engine, config, assistant
    engine.dispose()


def ask(assistant, store, data):
    started = time.monotonic()
    reply = assistant.chat(data, "user", store)
    print(json.dumps({"question": data.message, "answer": reply.answer, "basis": reply.basis,
                      "model": reply.model, "seconds": round(time.monotonic() - started, 2)}, ensure_ascii=False), flush=True)
    assert reply.answer.strip() and reply.answer not in {INSUFFICIENT, GREETING_ANSWER}
    return reply


def test_real_model_explains_the_previous_answer_in_a_persisted_conversation(live):
    engine, config, assistant = live
    with Session(engine) as db:
        store = Conversations(db, "dialogue-live-followup", "user", config)
        first = assistant.chat(ChatIn(message="Как скачать отчёт?"), "user", store)
        second = ask(assistant, store, ChatIn(message="я не понимаю", conversation_id=first.conversation_id, expected_revision=1))
        assert second.model == config.assistant_model
        assert second.answer != first.answer
        assert any(word in second.answer.casefold() for word in ("отч", "раздел", "формат", "шаг"))
        assert "?" in second.answer or "уточн" in second.answer.casefold()
        third = ask(assistant, store, ChatIn(message="А где искать эту кнопку?", conversation_id=first.conversation_id, expected_revision=2))
        assert third.model == config.assistant_model and third.revision == 3
        history = store.history(first.conversation_id, 1, 50)
        assert history.total == 3
        assert history.items[-1].answer == third.answer


def test_real_model_asks_a_question_without_evidence_or_prior_history(live):
    engine, config, assistant = live
    with Session(engine) as db:
        store = Conversations(db, "dialogue-live-first", "user", config)
        reply = ask(assistant, store, ChatIn(message="я не понимаю"))
        assert reply.model == config.assistant_model
        assert reply.basis == "insufficient" and reply.sources == []
        assert "?" in reply.answer or "уточн" in reply.answer.casefold()
