"""Create ONLY the standard workflow template (14 stages), nothing else.

Deliberately separate from ``python -m app.db.seed``: the general seed also
creates universities, catalog, licenses, contracts, documents, meetings and
responsibles. This script touches exactly two tables — ``workflow_templates``
and ``workflow_stages`` — so the route can be set up (or repaired) on its own
without touching any other data.

Source of the stage list: ``README.md`` ("Текущий workflow взаимодействия с
вузом (14 шагов)"), the only stage order fixed in the repository. Stage 5 is
seeded optional (``is_required=False``) because the ТЗ marks it
"Опционально: ...". No ``sla_days`` are invented: the ТЗ fixes no durations.

The stage list itself lives in :mod:`app.db.seed_workflow` and is reused from
there, so this script is a command-line entry point, not a second definition of
the route.

Idempotent: run 1 -> 1 template / 14 stages, run N -> the same, with drifted
names corrected in place.

Usage::

    # from backend/
    DATABASE_URL=postgresql+psycopg://... python scripts/create_workflow_template.py

    # inside the compose stack
    docker compose exec -T backend python scripts/create_workflow_template.py

Requires ``scripts/migrate.py up`` first (it never creates schema).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.seed_workflow import (  # noqa: E402
    STAGES_14,
    TEMPLATE_NAME,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate  # noqa: E402


def create_standard_template(session: Session) -> dict:
    """Explicit creation only; the general legacy seed remains disabled."""
    template = session.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()
    if template is None:
        template = WorkflowTemplate(name=TEMPLATE_NAME, is_active=True)
        session.add(template)
        session.flush()
    stages = {
        stage.order_index: stage
        for stage in session.scalars(
            select(WorkflowStage).where(WorkflowStage.template_id == template.id)
        )
    }
    for index, (name, required) in enumerate(STAGES_14, start=1):
        stage = stages.get(index)
        if stage is None:
            session.add(WorkflowStage(
                template_id=template.id, order_index=index, name=name,
                is_required=required, is_active=True,
            ))
        else:
            stage.name = name
            stage.is_required = required
    session.commit()
    return {"workflow_templates": 1, "workflow_stages": len(STAGES_14)}


def main() -> int:
    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            before = _snapshot(session)
            stats = create_standard_template(session)
            after = _snapshot(session)
    finally:
        engine.dispose()

    print(f"Шаблон: {TEMPLATE_NAME}")
    print(f"  шаблонов было/стало: {before['templates']}/{after['templates']}")
    print(f"  этапов было/стало:    {before['stages']}/{after['stages']}")
    print(f"  ожидается этапов:     {len(STAGES_14)}")
    print("Этапы:")
    for stage in after["stage_rows"]:
        flag = "" if stage.is_required else "  (опциональный)"
        print(f"  {stage.order_index:2}. {stage.name}{flag}")

    ok = (
        after["templates"] == 1
        and after["stages"] == len(STAGES_14)
        and stats == {"workflow_templates": 1, "workflow_stages": len(STAGES_14)}
    )
    if not ok:
        print("ОШИБКА: состояние не совпадает с ожидаемым", file=sys.stderr)
        return 1
    print("OK")
    return 0


def _snapshot(session: Session) -> dict:
    template = session.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()
    stages = (
        session.execute(
            select(WorkflowStage)
            .where(WorkflowStage.template_id == template.id)
            .order_by(WorkflowStage.order_index)
        )
        .scalars()
        .all()
        if template is not None
        else []
    )
    return {
        "templates": (
            len(
                session.execute(
                    select(WorkflowTemplate).where(WorkflowTemplate.name == TEMPLATE_NAME)
                )
                .scalars()
                .all()
            )
        ),
        "stages": len(stages),
        "stage_rows": stages,
    }


if __name__ == "__main__":
    raise SystemExit(main())
