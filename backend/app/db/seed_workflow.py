"""Legacy workflow seed entry point. It no longer creates templates.

The 14-stage template name and stage list remain for integrations and
reference data; running this module does not write workflow templates.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

TEMPLATE_NAME = "Стандартный маршрут взаимодействия с вузом (14 этапов)"
TEMPLATE_DESCRIPTION = None
LEGACY_TEMPLATE_DESCRIPTION = "Канонический маршрут из 14 этапов (README: текущий workflow взаимодействия с вузом)"

# (name, is_required) in canonical order; order_index = position (1-based).
STAGES_14: list[tuple[str, bool]] = [
    ("Поиск контактов ответственного в вузе", True),
    ("Коммуникация с ним и уточнение актуальности программ по ИТ-направлениям", True),
    ("Организация встречи с представителями вуза", True),
    ("Обмен необходимым пакетом документов для подписания", True),
    ("Опционально: скорректировать документы перед подписанием", False),
    ("Подписание документов", True),
    (
        "Передача обучающих материалов по ИТ-направлению, "
        "лицензии ИТ-продукта и его документации в вуз",
        True,
    ),
    ("Сопровождение внедрения ИТ-продуктов в вузе", True),
    ("Обучение преподавателей", True),
    (
        "Актуализация учебной программы по ИТ-направлению с учётом "
        "обучения преподавателя и добавления ИТ-продукта",
        True,
    ),
    ("Ведение занятий", True),
    ("Актуализация документации по продукту и обучающим материалам", True),
    ("Повышение квалификации преподавателей", True),
    ("Контроль за исполнением каждого этапа", True),
]


def seed_workflow_templates(session: Session) -> dict:
    """Legacy entry point: demo workflow templates are no longer seeded."""
    return {"workflow_templates": 0, "workflow_stages": 0}


def main() -> None:
    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    with Session(engine) as session:
        stats = seed_workflow_templates(session)
    logging.getLogger("rtk.seed").info("SEED WORKFLOW OK: %s", stats)


if __name__ == "__main__":
    main()
