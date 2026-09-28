"""Passport history exposes useful audit actions without raw audit payloads."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.universities.history_service import present_history_event


def event(entity_type="document", action="CREATE", new_value=None, old_value=None, user_name="Анна Морозова"):
    return SimpleNamespace(
        id=uuid.uuid4(), entity_id=uuid.uuid4(), entity_type=entity_type,
        university_id=uuid.uuid4(), action=action, old_value=old_value,
        new_value=new_value, user_id="user-1", user_name=user_name,
        role="manager", created_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
    )


def test_attachment_has_human_action_and_download_metadata():
    instance_id = uuid.uuid4()
    row = event(new_value={
        "audit_object_type": "workflow_attachment", "instance_id": str(instance_id),
        "original_filename": "Договор.pdf", "mime_type": "application/pdf",
    })
    result = present_history_event(row, {}, "МТУСИ")
    assert result["title"] == "Загрузил файл «Договор.pdf»"
    assert result["user_name"] == "Анна Морозова"
    assert result["attachment"] == {
        "instance_id": str(instance_id), "attachment_id": str(row.entity_id),
        "file_name": "Договор.pdf", "mime_type": "application/pdf",
    }
    assert "new_value" not in result and "ip" not in result


def test_comment_and_transition_are_readable():
    comment = present_history_event(event(
        entity_type="workflow_comment", new_value={"content": "Согласовано"}), {}, "МТУСИ")
    assert comment["title"] == "Добавил комментарий"
    assert comment["changes"][0]["new"] == "Согласовано"
    transition = present_history_event(event(
        entity_type="workflow_instance", action="WORKFLOW_TRANSITION",
        old_value={"stage_name": "Встреча"}, new_value={"stage_name": "Документы"}), {}, "МТУСИ")
    assert "Встреча" in transition["title"] and "Документы" in transition["title"]


def test_unopenable_legacy_document_and_technical_event_are_hidden():
    assert present_history_event(event(new_value={"original_filename": "legacy.pdf"}), {}, "МТУСИ") is None
    assert present_history_event(event(entity_type="config", action="UPDATE"), {}, "МТУСИ") is None
