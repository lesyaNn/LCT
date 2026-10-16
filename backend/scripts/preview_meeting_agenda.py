"""Render a synthetic brief without a running API/database (development only).

Run from backend: python -m scripts.preview_meeting_agenda
Stress: python -m scripts.preview_meeting_agenda --stress --output ../tmp/pdfs/stress.pdf
"""

import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from app.modules.meeting_agenda.pdf import generate_agenda_pdf
from app.modules.meeting_agenda.schemas import MeetingAgenda


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("../output/pdf/meeting-agenda-demo.pdf")
    )
    parser.add_argument("--stress", action="store_true")
    args = parser.parse_args()
    now = datetime(2026, 10, 16, 10, 30, tzinfo=UTC)
    instance_id = uuid4()
    suffix = " Очень длинная запись для проверки вёрстки." * 250 if args.stress else ""
    count = 100 if args.stress else 3
    program_names = [
        "Разработка корпоративных приложений",
        "Информационная безопасность",
        "Сетевое администрирование",
    ]
    product_names = [
        "Платформа учебных лабораторий",
        "Среда виртуализации",
        "Система управления базами данных",
    ]
    questions = [
        "Кто согласует продление лицензий на следующий семестр?",
        "Нужно уточнить сроки запуска новой программы и состав учебной группы.",
        "Согласовать встречу с руководителем ИТ-направления и куратором программы.",
    ]
    agenda = MeetingAgenda(
        university_id=uuid4(),
        university_name="Московский технический университет" + suffix,
        city="Москва",
        instance_id=instance_id,
        stage_id=uuid4(),
        stage_name="Организация встречи" + suffix,
        stage_order=3,
        generated_at=now,
        as_of=now.date(),
        expires_through=date(2026, 11, 15),
        warning_days=30,
        programs={
            "items": [
                {
                    "program_id": uuid4(),
                    "name": program_names[i % 3] + suffix,
                    "direction": "ИТ и цифровые технологии",
                    "status": "active",
                    "launch_date": date(2026, 9, 1),
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
        expiring_licenses={
            "items": [
                {
                    "license_id": uuid4(),
                    "license_number": f"ЛЦТ-{i + 1:03}",
                    "product": product_names[i % 3] + suffix,
                    "expires_at": date(2026, 10, 22),
                    "days_left": 6,
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
        open_questions={
            "items": [
                {
                    "comment_id": uuid4(),
                    "instance_id": instance_id,
                    "stage_id": None,
                    "content": questions[i % 3] + suffix,
                    "created_at": now,
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
    )
    generate_agenda_pdf(agenda)  # cold font registration separated from warm timings
    started = time.perf_counter()
    content = generate_agenda_pdf(agenda)
    elapsed = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(
        f"Synthetic PDF: {args.output.resolve()} ({len(content)} bytes); warm generation {elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
