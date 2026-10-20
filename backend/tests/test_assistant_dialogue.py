"""Free-form follow-ups use the model and server-side history, not a phrase FAQ."""

import json
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.modules.assistant.greetings import greeting_reply
from app.modules.assistant.provider import Ollama
from app.modules.assistant.quick_replies import match_quick_reply
from app.modules.assistant.repository import Conversations, Prepared
from app.modules.assistant.schemas import ChatIn, ModelAnswer
from app.modules.assistant.service import Assistant
from tests.test_assistant import build_knowledge


@pytest.mark.parametrize("question", ["я не понимаю", "Объясни иначе", "Запутался, давай по шагам", "А что дальше?", "Можешь проще?"])
def test_followups_use_the_model_and_previous_explanation(tmp_path, question):
    assert match_quick_reply(question) is None and greeting_reply(question) is None
    store = Mock(spec=Conversations)
    store.prepare.return_value = Prepared(uuid4(), 2, (
        ("Как получить отчёт?", "Откройте отчёты и выберите формат PDF."),
        ("А дальше?", "Запустите формирование и дождитесь готовности."),
    ), False)
    store.save.side_effect = lambda _prepared, _question, result: result
    provider = Mock(spec=Ollama)
    provider.chat.return_value = ModelAnswer(
        answer="Начнём с первого шага: откройте раздел Отчёты. Не получается найти раздел или выбрать формат?",
        basis="insufficient",
    )
    result = Assistant(Settings(assistant_enabled=True), build_knowledge(tmp_path), provider).chat(ChatIn(message=question), "user", store)
    messages = provider.chat.call_args.args[0]
    assert json.loads(messages[-1]["content"])["question"] == question
    assert any(message["role"] == "assistant" and "дождитесь готовности" in message["content"] for message in messages)
    if not json.loads(messages[-1]["content"])["documentation"]:
        assert "одним уточняющим вопросом" in messages[0]["content"]
    assert result.model == "qwen3:1.7b" and result.revision == 3
    assert result.answer == provider.chat.return_value.answer
    assert result.sources == [] and result.basis == "insufficient"
    store.save.assert_called_once()


def test_vague_first_question_also_reaches_model_without_evidence(tmp_path):
    store = Mock(spec=Conversations)
    store.prepare.return_value = Prepared(uuid4(), 0, (), True)
    store.save.side_effect = lambda _prepared, _question, result: result
    provider = Mock(spec=Ollama)
    provider.chat.return_value = ModelAnswer(answer="С каким разделом CRM помочь и что вы хотите сделать?", basis="insufficient")
    result = Assistant(Settings(assistant_enabled=True), build_knowledge(tmp_path), provider).chat(ChatIn(message="я не понимаю"), "user", store)
    assert provider.chat.call_count == 1
    assert provider.chat.call_args.kwargs["source_ids"] == []
    assert result.model == "qwen3:1.7b" and result.sources == []
    assert result.answer == provider.chat.return_value.answer


def test_history_is_conversation_context_not_manufactured_document_evidence(tmp_path):
    store = Mock(spec=Conversations)
    store.prepare.return_value = Prepared(uuid4(), 1, (("Мне нужна помощь", "Скачать отчёт PDF через раздел Отчёты."),), False)
    store.save.side_effect = lambda _prepared, _question, result: result
    provider = Mock(spec=Ollama)
    provider.chat.return_value = ModelAnswer(answer="Вы уже открыли Отчёты?", basis="insufficient")
    Assistant(Settings(assistant_enabled=True), build_knowledge(tmp_path), provider).chat(ChatIn(message="я не понимаю"), "user", store)
    docs = json.loads(provider.chat.call_args.args[0][-1]["content"])["documentation"]
    assert docs == []
    assert any(message["role"] == "assistant" and "Отчёты" in message["content"] for message in provider.chat.call_args.args[0])
    assert all("Сбросить пароль" not in document["text"] for document in docs)


def test_empty_evidence_constrains_the_model_schema():
    def respond(request):
        body = json.loads(request.content)
        properties = body["format"]["properties"]
        assert properties["basis"]["enum"] == ["insufficient"]
        assert properties["source_ids"]["maxItems"] == 0
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
            "answer": "Какой шаг вызвал затруднение?", "basis": "insufficient", "source_ids": [],
        })}})
    result = Ollama(Settings(), httpx.MockTransport(respond)).chat([{"role": "user", "content": "я не понимаю"}], source_ids=[])
    assert result.basis == "insufficient" and result.source_ids == []
