"""Approved FAQ responses. Exact phrases only; no fuzzy intent guessing."""

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass

from app.modules.assistant.schemas import Source


@dataclass(frozen=True)
class QuickReply:
    id: str
    question: str
    answer: str
    clarification: bool = False
    aliases: tuple[str, ...] = ()

    def source(self) -> Source:
        return Source(
            id=f"quick:{self.id}",
            title="Частые вопросы",
            url="/docs?article=help%2Ffaq",
            excerpt=self.answer,
        )


QUICK_REPLIES = (
    QuickReply(
        "download-report",
        "Как скачать отчёт?",
        "Откройте Отчёты, выберите фильтры, столбцы и формат. Запустите формирование. Когда задача будет готова, нажмите Скачать.",
        aliases=("Как выгрузить отчёт?", "Где взять отчёт?"),
    ),
    QuickReply(
        "explain-status",
        "Что означает статус?",
        "Уточните, где вы видите статус: в Workflow, лицензии, договоре или отчёте. Напишите его название.",
        clarification=True,
        aliases=("Что значит статус?", "Что за статус?", "Что означает этот статус?", "Статус"),
    ),
    QuickReply(
        "find-contact",
        "Где найти контакты вуза?",
        "Откройте паспорт вуза и вкладку Ответственные. Там указаны контактные лица, телефоны и email.",
    ),
    QuickReply(
        "find-university",
        "Не вижу нужный вуз",
        "Сбросьте фильтры и введите часть названия. Если вуз не появился, попросите администратора проверить назначенный вам доступ.",
    ),
    QuickReply(
        "copy-contact",
        "Как скопировать контакт?",
        "Нажмите значок копирования рядом с телефоном или email. Кнопка возле имени копирует весь контакт вместе с должностью.",
    ),
    QuickReply(
        "license-expiry",
        "Где посмотреть срок лицензии?",
        "В паспорте вуза откройте Лицензии. В таблице указаны дата окончания и статус. Фильтр поможет найти скоро истекающие и просроченные лицензии.",
    ),
    QuickReply(
        "download-file",
        "Как скачать прикреплённый файл?",
        "Откройте Документы в паспорте вуза или Вложения в Workflow и нажмите на имя файла.",
        aliases=("Как скачать файл?",),
    ),
    QuickReply(
        "previous-stage",
        "Как вернуть предыдущий этап?",
        "В открытом Workflow нажмите Вернуть на предыдущий этап и укажите причину. Если кнопки нет, уточните возможность возврата у ответственного или администратора.",
        aliases=("Как вернуть Workflow на предыдущий этап?", "Можно ли вернуться назад?"),
    ),
    QuickReply(
        "change-history",
        "Кто изменил данные?",
        "Посмотрите Историю в паспорте вуза или Историю Workflow. Общий журнал находится в разделе Аудит, если он доступен вашей роли.",
        aliases=("Где посмотреть, кто изменил данные?",),
    ),
    QuickReply(
        "answer-not-helpful",
        "Ответ не подходит",
        "Уточните, какой раздел или действие вы имели в виду. Например: статус лицензии, этап Workflow или скачивание отчёта.",
        clarification=True,
        aliases=("Это не то", "Нет, это не то", "Не то"),
    ),
)


def normalized_question(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").split()
    ).strip(" .!?")


_BY_QUESTION = {
    normalized_question(question): reply
    for reply in QUICK_REPLIES
    for question in (reply.question, *reply.aliases)
}
QUICK_REPLY_VERSION = hashlib.sha256(
    json.dumps(
        [asdict(reply) for reply in QUICK_REPLIES], ensure_ascii=False, sort_keys=True
    ).encode()
).hexdigest()


def match_quick_reply(question: str) -> QuickReply | None:
    return _BY_QUESTION.get(normalized_question(question))
