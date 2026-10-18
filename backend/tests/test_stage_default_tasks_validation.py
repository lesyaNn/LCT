"""Default checklist titles follow the runtime task naming contract."""

import pytest
from pydantic import ValidationError

from app.modules.workflow_templates.schemas import StageCreate, StageUpdate


@pytest.mark.parametrize("value", [[""], ["  \n  "], ["x" * 513], [None], [123], None, "task"])
@pytest.mark.parametrize("schema", [StageCreate, StageUpdate])
def test_default_tasks_reject_invalid_titles(schema, value):
    with pytest.raises(ValidationError):
        schema(name="Этап", default_tasks=value)


def test_default_tasks_trim_and_allow_explicit_clear():
    assert StageCreate(name="Этап", default_tasks=["  Проверить документы  "]).default_tasks == [
        "Проверить документы"
    ]
    assert StageUpdate(default_tasks=[]).default_tasks == []
    assert "default_tasks" in StageUpdate(default_tasks=[]).model_fields_set
    assert "default_tasks" not in StageUpdate(name="Новое имя").model_fields_set
