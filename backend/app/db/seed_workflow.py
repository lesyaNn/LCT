"""P2-01-04 seed: the standard 14-stage university-interaction route.

* Source of the stage names/order: ``README.md`` ("Текущий workflow
  взаимодействия с вузом (14 шагов)") — the only stage list fixed in the
  repository. Names are quoted verbatim (trailing punctuation dropped).
* Runs strictly AFTER ``scripts/migrate.py up`` (``migrate -> seed``);
  never creates schema, only rows in ``000011`` tables.
* Idempotent: the template is get-or-created by its UNIQUE name, stages by
  ``(template_id, order_index)``; re-runs update drifted names in place and
  never duplicate. ``run 1 -> 1 template / 14 stages``,
  ``run 2 -> still 1 template / 14 stages``.
* Stage 5 is explicitly optional in the ТЗ ("Опционально: ...") and is
  seeded with ``is_required=False``; every other stage is required.
* No deadlines are invented: the ТЗ fixes no durations, so ``sla_days``
  stays NULL for all 14 stages.

Usage::

    DATABASE_URL=postgresql+psycopg://... python -m app.db.seed_workflow
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

TEMPLATE_NAME = "Стандартный маршрут взаимодействия с вузом"
TEMPLATE_DESCRIPTION = (
    "Канонический маршрут из 14 этапов (README: текущий workflow взаимодействия с вузом)"
)

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
    """Upsert the standard template + its 14 stages. Returns counts."""
    template = session.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()
    if template is None:
        template = WorkflowTemplate(name=TEMPLATE_NAME, description=TEMPLATE_DESCRIPTION)
        session.add(template)
        session.flush()
    elif template.description != TEMPLATE_DESCRIPTION:
        template.description = TEMPLATE_DESCRIPTION

    for position, (name, is_required) in enumerate(STAGES_14, start=1):
        stage = session.execute(
            select(WorkflowStage).where(
                WorkflowStage.template_id == template.id,
                WorkflowStage.order_index == position,
            )
        ).scalar_one_or_none()
        if stage is None:
            session.add(
                WorkflowStage(
                    template_id=template.id,
                    name=name,
                    order_index=position,
                    is_required=is_required,
                )
            )
        else:
            if stage.name != name:
                stage.name = name
            if stage.is_required is not is_required:
                stage.is_required = is_required
    session.commit()

    n_templates = (
        session.execute(select(WorkflowTemplate.id).where(WorkflowTemplate.name == TEMPLATE_NAME))
        .scalars()
        .all()
        .__len__()
    )
    n_stages = (
        session.execute(select(WorkflowStage.id).where(WorkflowStage.template_id == template.id))
        .scalars()
        .all()
        .__len__()
    )
    return {"workflow_templates": n_templates, "workflow_stages": n_stages}


def main() -> None:
    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    with Session(engine) as session:
        stats = seed_workflow_templates(session)
    logging.getLogger("rtk.seed").info("SEED WORKFLOW OK: %s", stats)


if __name__ == "__main__":
    main()
