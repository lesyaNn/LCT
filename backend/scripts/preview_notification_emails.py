"""Render all notification scenarios locally without a database or SMTP.

Run from backend: python -m scripts.preview_notification_emails --output /tmp/rtk-emails
"""

import argparse
from pathlib import Path

from app.models.notification import Notification
from app.modules.notifications.email import render_message
from app.modules.notifications.email_templates import render_preview_message

EXAMPLES = (
    ("assignment", "university", "Вам назначен новый ВУЗ",
     "Вы назначены ответственным за «Московский политехнический университет»."),
    ("assignment", "workflow", "Вам назначена работа",
     "Вы назначены ответственным за работу с «Московский политехнический университет»."),
    ("user_university_assigned", "university", "Вам назначен новый ВУЗ",
     "Вам предоставлен доступ к ВУЗу «Московский политехнический университет»."),
    ("user_university_assigned", "universities", "Вам назначены новые ВУЗы",
     "Вам предоставлен доступ к 2 ВУЗам:\n• Московский политехнический университет\n• Университет ИТМО"),
    ("workflow_stage_completed", "workflow", "Этап Workflow завершён",
     "Иван Смирнов завершил этап «Знакомство» по ВУЗу «Университет ИТМО». "
     "Новый этап: «Согласование договора»."),
    ("workflow_rollback", "workflow", "Workflow возвращён на предыдущий этап",
     "Иван Смирнов вернул Workflow по ВУЗу «Университет ИТМО» на этап «Согласование». "
     "Причина: необходимо уточнить реквизиты и подготовить новую редакцию документа."),
    ("workflow_comment_added", "workflow", "Новый комментарий в Workflow",
     "Анна Петрова оставил комментарий по ВУЗу «Университет ИТМО»: "
     "«Коллеги, договор согласован. Вложение: Договор_2026.pdf. Следующая встреча — 20.10.2026»."),
    ("deadline_approaching", "workflow", "Приближается срок",
     "До завершения этапа «Согласование договора» для «Университет ИТМО» осталось 3 дн."),
    ("overdue", "workflow", "Требуется внимание",
     "Задача «Получить подписанный договор» для «Университет ИТМО» просрочена на 2 дн."),
    ("contract_expiry", "contract", "Срок договора заканчивается",
     "Срок договора с «Университет ИТМО» — 20.10.2026. Осталось 3 дн."),
    ("license_expiry", "license", "Срок лицензии заканчивается",
     "Срок лицензии с «Университет ИТМО» — 20.10.2026. Осталось 3 дн."),
    ("import_error", "import_job", "Импорт завершён с ошибками",
     "Обработано: 1250 строк. Успешно: 1248. Ошибок: 2."),
    ("import_error", "import_job", "Импорт завершён с ошибками",
     "Не удалось завершить импорт. Посмотрите результат задачи."),
    ("overdue", "workflow", "Требуется внимание",
     "Этап «Согласование договора» для «Университет ИТМО» просрочен на 2 дн."),
    ("deadline_approaching", "workflow", "Приближается срок",
     "До срока задачи «Получить подписанный договор» для «Университет ИТМО» осталось 3 дн."),
    ("workflow_comment_added", "workflow", "Новый комментарий в Workflow",
     "Иван Смирнов оставил комментарий по ВУЗу «Университет ИТМО»: "
     "«Прикрепил согласованную редакцию договора. Можно переходить к подписанию»."),
    ("workflow_completed", "workflow", "Workflow завершён",
     "Иван Смирнов завершил Workflow по ВУЗу «Университет ИТМО». "
     "Процесс: «Подключение образовательной программы»."),
    ("workflow_task_added", "workflow", "Добавлена новая задача",
     "Иван Смирнов добавил задачу «Подготовить договор» "
     "на этапе «Согласование договора» по ВУЗу «Университет ИТМО»."),
    ("workflow_task_completed", "workflow", "Задача выполнена",
     "Иван Смирнов выполнил задачу «Подготовить договор» "
     "на этапе «Согласование договора» по ВУЗу «Университет ИТМО»."),
)


def example_notification(example) -> Notification:
    kind, entity, title, message = example
    return Notification(
        type=kind, entity_type=entity, title=title, message=message,
        entity_id="00000000-0000-0000-0000-000000000001",
        university_id="00000000-0000-0000-0000-000000000002",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/rtk-emails"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    links = []
    for index, example in enumerate(EXAMPLES, start=1):
        subject, body = render_message(example_notification(example))
        name = f"{index:02d}-{example[0]}"
        (args.output / f"{name}.html").write_text(render_preview_message(subject, body), encoding="utf-8")
        (args.output / f"{name}.txt").write_text(body, encoding="utf-8")
        links.append(f'<li><a href="{name}.html">{subject}</a> · <a href="{name}.txt">Текст</a></li>')
    (args.output / "index.html").write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Письма CRM</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<body style="font:16px/1.8 Arial,sans-serif;padding:24px"><h1>Письма CRM</h1><ul>'
        + "".join(links) + "</ul></body></html>", encoding="utf-8",
    )
    print(f"Rendered {len(EXAMPLES)} HTML/text pairs: {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
