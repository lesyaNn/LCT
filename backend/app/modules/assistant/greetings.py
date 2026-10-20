"""Exact social greetings do not need retrieval or model generation."""

import hashlib
import re

from app.modules.assistant.quick_replies import normalized_question

GREETING_ANSWER = (
    "Здравствуйте! Я помощник CRM ИТ Школы Ростелекома. "
    "Подскажу, как работать с вузами, Workflow, документами и отчётами. "
    "Выберите быстрый вопрос или напишите свой."
)
GREETING_VERSION = hashlib.sha256(GREETING_ANSWER.encode()).hexdigest()

_GREETINGS = frozenset(
    {
        "привет",
        "здравствуйте",
        "здравствуй",
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "привет как дела",
        "привет как ты",
        "здравствуйте как дела",
        "как дела",
        "как ты",
    }
)


def greeting_reply(message: str) -> str | None:
    # Match the whole message: a CRM question after a greeting must not be lost.
    question = " ".join(re.sub(r"[,!?.:;]+", " ", normalized_question(message)).split())
    return GREETING_ANSWER if question in _GREETINGS else None
