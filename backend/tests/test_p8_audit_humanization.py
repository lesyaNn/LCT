"""Human-readable audit presentation: titles, fallbacks, redaction, resolver.

Pure-unit tests (no database): the presentation layer must turn technical
payloads into sentences without ever leaking UUIDs, ORM names, DB field
names, booleans or secrets into user-facing strings.
"""

import re
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.audit.presentation import (
    actor_display_name,
    classify_config,
    format_file_size,
    format_value,
    summarize_event,
)
from app.modules.audit.resolver import collect_ids, entity_display_name, resolve_names
from app.modules.audit.router import AuditEventRead

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
TECHNICAL_WORDS = [
    "Admin config", "Config", "config", "workflow_instance", "workflow_comment",
    "external_sync", "template_id", "program_id", "product_id", "responsible_id",
    "direction_id", "vendor_id", "stage_id", "instance_id", "keycloak_sub",
    "author_keycloak_sub", "order_index", "is_active", "is_required", "sla_days",
]


def assert_human(*texts: str) -> None:
    for text in texts:
        assert not UUID_RE.search(text), f"UUID leaked: {text}"
    joined = "\n".join(texts)
    for word in TECHNICAL_WORDS:
        assert word not in joined, f"technical token leaked: {word!r} in {joined!r}"


def summary_text(summary: dict) -> list[str]:
    parts = [summary["title"], summary["section"]]
    for row in summary["changes"]:
        parts += [row["label"], row["old"], row["new"]]
    return parts


# ------------------------------------------------------------------ university

def test_create_university_title():
    summary = summarize_event(
        "CREATE", "university", None, {"name": "МТУСИ", "city": "Москва"}, {}, None)
    assert summary["title"] == "Создал ВУЗ «МТУСИ»"
    assert summary["section"] == "ВУЗы"
    assert_human(*summary_text(summary))


def test_update_university_changes():
    summary = summarize_event(
        "UPDATE", "university",
        {"name": "МТУСИ", "city": "Москва"},
        {"name": "МТУСИ", "city": "Санкт-Петербург"}, {}, "МТУСИ")
    assert summary["title"] == "Изменил ВУЗ «МТУСИ»"
    labels = [row["label"] for row in summary["changes"]]
    assert labels == ["Город"]
    assert summary["changes"][0]["new"] == "Санкт-Петербург"
    assert_human(*summary_text(summary))


def test_delete_university_keeps_name_from_old():
    summary = summarize_event(
        "DELETE", "university", {"name": "МТУСИ", "city": "Москва"}, None, {}, None)
    assert "МТУСИ" in summary["title"]
    assert_human(*summary_text(summary))


# ------------------------------------------------------- workflow templates

def test_create_workflow_template():
    summary = summarize_event(
        "ADMIN_CONFIG", "config", None,
        {"audit_object_type": "workflow_template",
         "name": "Запуск образовательной программы", "is_active": True}, {}, None)
    assert summary["title"] == "Создал шаблон Workflow «Запуск образовательной программы»"
    assert_human(*summary_text(summary))


def test_update_workflow_template_name():
    summary = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "workflow_template", "name": "Старое", "is_active": True},
        {"audit_object_type": "workflow_template", "name": "Новое", "is_active": True},
        {}, None)
    assert summary["title"] == "Изменил шаблон Workflow «Новое»"
    assert summary["changes"][0]["label"] == "Название"
    assert_human(*summary_text(summary))


def test_deactivate_template_special_title():
    summary = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "workflow_template", "name": "Шаблон", "is_active": True},
        {"audit_object_type": "workflow_template", "name": "Шаблон", "is_active": False},
        {}, None)
    assert summary["title"] == "Отключил шаблон Workflow «Шаблон»"
    assert summary["changes"][0]["new"] == "Выключен"
    assert_human(*summary_text(summary))


# ------------------------------------------------------------ workflow stages

OLD_STAGE = {
    "template_id": "30d06bca-af1a-4483-a835-5b7121b20ac2",
    "name": "Согласование", "order_index": 2, "is_active": True,
}


def test_old_stage_record_without_names_stays_human():
    """Historical create-stage payload: UUID must not reach the user."""
    summary = summarize_event("ADMIN_CONFIG", "workflow_stage", None, dict(OLD_STAGE), {}, None)
    assert "Согласование" in summary["title"]
    assert_human(summary["title"], summary["section"])


def test_stage_reorder_shows_numbers():
    summary = summarize_event(
        "ADMIN_CONFIG", "workflow_stage",
        {"audit_object_type": "workflow_stage", "name": "Согласование",
         "order_index": 2, "is_active": True, "is_required": True, "sla_days": 5},
        {"audit_object_type": "workflow_stage", "name": "Согласование",
         "order_index": 3, "is_active": True, "is_required": True, "sla_days": 5},
        {}, None)
    assert summary["title"] == "Изменил этап «Согласование»"
    by_label = {row["label"]: row for row in summary["changes"]}
    assert by_label["Порядок этапа"]["old"] == "2"
    assert by_label["Порядок этапа"]["new"] == "3"
    assert_human(*summary_text(summary))


def test_stage_deactivate():
    summary = summarize_event(
        "ADMIN_CONFIG", "workflow_stage",
        {"audit_object_type": "workflow_stage", "name": "Согласование",
         "order_index": 2, "is_active": True, "is_required": True, "sla_days": 5},
        {"audit_object_type": "workflow_stage", "name": "Согласование",
         "order_index": 2, "is_active": False, "is_required": True, "sla_days": 5},
        {}, None)
    assert summary["title"] == "Отключил этап «Согласование»"
    assert_human(*summary_text(summary))


def test_stage_boolean_and_sla_formatting():
    summary = summarize_event(
        "ADMIN_CONFIG", "workflow_stage",
        {"audit_object_type": "workflow_stage", "name": "Этап",
         "order_index": 1, "is_active": True, "is_required": False, "sla_days": 5},
        {"audit_object_type": "workflow_stage", "name": "Этап",
         "order_index": 1, "is_active": True, "is_required": True, "sla_days": 7},
        {}, None)
    by_label = {row["label"]: row for row in summary["changes"]}
    assert by_label["Обязательный этап"] == {
        "field": "is_required", "label": "Обязательный этап",
        "old": "Необязательный", "new": "Обязательный"}
    assert by_label["Срок выполнения"]["new"] == "7 дней"
    assert_human(*summary_text(summary))


# -------------------------------------------------------------- transitions

def test_workflow_transition_title_and_comment():
    summary = summarize_event(
        "WORKFLOW_TRANSITION", "workflow_instance",
        {"stage_id": str(uuid.uuid4()), "stage_name": "Подготовка"},
        {"stage_id": str(uuid.uuid4()), "stage_name": "Запуск",
         "comment": "Документы согласованы"},
        {}, "МТУСИ")
    assert summary["title"] == "Перевёл «МТУСИ» с этапа «Подготовка» на этап «Запуск»"
    assert summary["changes"][-1] == {
        "field": "comment", "label": "Комментарий",
        "old": "—", "new": "Документы согласованы"}
    assert_human(*summary_text(summary))


# ----------------------------------------------------------------- comments

def test_workflow_comment_create():
    summary = summarize_event(
        "CREATE", "workflow_comment", None,
        {"audit_object_type": "workflow_comment",
         "instance_id": str(uuid.uuid4()), "stage_id": str(uuid.uuid4()),
         "author_keycloak_sub": str(uuid.uuid4()),
         "content": "Необходимо обновить договор", "is_internal": True}, {}, None)
    assert summary["title"] == "Добавил комментарий"
    assert summary["changes"][0]["new"] == "Необходимо обновить договор"
    assert_human(*summary_text(summary))


# --------------------------------------------------------------- attachments

def test_attachment_upload_formats_file_size():
    summary = summarize_event(
        "CREATE", "document", None,
        {"instance_id": str(uuid.uuid4()),
         "original_filename": "дорожная-карта.pdf",
         "file_size": 102400, "mime_type": "application/pdf"}, {}, None)
    assert summary["title"] == "Загрузил файл «дорожная-карта.pdf»"
    assert summary["changes"][0]["new"] == "100 КБ"
    assert_human(*summary_text(summary))


def test_attachment_delete():
    summary = summarize_event(
        "DELETE", "document",
        {"instance_id": str(uuid.uuid4()),
         "original_filename": "дорожная-карта.pdf",
         "file_size": 2516582, "mime_type": "application/pdf"}, None, {}, None)
    assert summary["title"] == "Удалил файл «дорожная-карта.pdf»"
    assert "МБ" in summary["changes"][0]["old"]
    assert_human(*summary_text(summary))


# --------------------------------------------------------------- responsible

def test_assign_responsible_with_names():
    summary = summarize_event(
        "ASSIGN_RESPONSIBLE", "responsible",
        {"responsible_id": str(uuid.uuid4())},
        {"responsible_id": str(uuid.uuid4()),
         "responsible_name": "Иван Петров", "reason": "Ротация"},
        {}, "МТУСИ")
    assert "Иван Петров" in summary["title"]
    assert "МТУСИ" in summary["title"]
    assert summary["changes"][-1]["new"] == "Ротация"
    assert_human(*summary_text(summary))


def test_unassign_responsible_resolves_old_name():
    old_id, new_id = str(uuid.uuid4()), str(uuid.uuid4())
    names = {old_id.lower(): "Анна Смирнова"}
    summary = summarize_event(
        "ASSIGN_RESPONSIBLE", "responsible",
        {"responsible_id": old_id}, {"responsible_id": None},
        names, "МТУСИ")
    assert summary["title"] == "Снял «Анна Смирнова» с ответственных за «МТУСИ»"
    assert_human(*summary_text(summary))


# -------------------------------------------------------------------- users

def test_user_role_change():
    summary = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "user", "kind": "role",
         "value": "manager", "target_name": "Иван Петров"},
        {"audit_object_type": "user", "kind": "role",
         "value": "admin", "target_name": "Иван Петров"}, {}, None)
    assert summary["title"] == "Изменил роль пользователя «Иван Петров»"
    assert summary["changes"][0] == {
        "field": "role", "label": "Роль",
        "old": "Менеджер", "new": "Администратор"}
    assert_human(*summary_text(summary))


def test_user_block_unblock():
    blocked = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "user", "kind": "status",
         "value": "active", "target_name": "Иван Петров"},
        {"audit_object_type": "user", "kind": "status",
         "value": "blocked", "target_name": "Иван Петров"}, {}, None)
    assert blocked["title"] == "Заблокировал пользователя «Иван Петров»"
    unblocked = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "user", "kind": "status",
         "value": "blocked", "target_name": "Иван Петров"},
        {"audit_object_type": "user", "kind": "status",
         "value": "active", "target_name": "Иван Петров"}, {}, None)
    assert unblocked["title"] == "Восстановил доступ пользователя «Иван Петров»"
    assert_human(*summary_text(blocked), *summary_text(unblocked))


def test_user_scope_change_resolves_universities():
    uni_a, uni_b = str(uuid.uuid4()), str(uuid.uuid4())
    names = {uni_a.lower(): "МТУСИ", uni_b.lower(): "РТУ МИРЭА"}
    summary = summarize_event(
        "ADMIN_CONFIG", "config",
        {"audit_object_type": "user", "kind": "scope",
         "value": [uni_a], "target_name": "Иван Петров"},
        {"audit_object_type": "user", "kind": "scope",
         "value": [uni_a, uni_b], "target_name": "Иван Петров"}, names, None)
    assert summary["title"] == "Изменил доступ пользователя «Иван Петров»"
    assert summary["changes"][0]["new"] == "РТУ МИРЭА"
    assert_human(*summary_text(summary))


def test_classify_config_subtypes():
    assert classify_config(None, {"name": "X", "is_active": True}) == "workflow_template"
    assert classify_config(
        {"kind": "role", "value": "manager"},
        {"kind": "role", "value": "admin"}) == "user"
    assert classify_config(None, {"foo": 1}) == "unknown"
    # Legacy template payload without marker still classifies correctly.
    assert classify_config(
        {"name": "A", "description": "d", "is_active": True},
        {"name": "B", "description": "d", "is_active": True}) == "workflow_template"


# -------------------------------------------------------- program / product

def test_program_attach():
    program_id = str(uuid.uuid4())
    summary = summarize_event(
        "CREATE", "program",
        None, {"program_id": program_id, "status": "planned"}, {}, "МТУСИ")
    assert summary["title"].startswith("Добавил программу")
    assert "МТУСИ" in summary["title"]
    assert summary["changes"][0]["new"] == "Запланирована"
    assert_human(*summary_text(summary))


def test_product_attach_uses_unresolvable_fallback_not_uuid():
    summary = summarize_event(
        "CREATE", "product",
        None, {"product_id": str(uuid.uuid4()), "status": "active"}, {}, "МТУСИ")
    assert "Удалённая программа" not in summary["title"]
    assert "название недоступно" in summary["title"]
    assert summary["changes"][0]["new"] == "Активен"
    assert_human(*summary_text(summary))


# ----------------------------------------------------------------- meetings

def test_meeting_create_and_update():
    created = summarize_event(
        "CREATE", "meeting", None,
        {"meeting_type": "online", "subject": "Обсуждение запуска",
         "meeting_at": "2026-09-26T15:00:00+03:00"}, {}, "МТУСИ")
    assert created["title"] == "Создал встречу с «МТУСИ»"
    assert created["object_name"] == "Обсуждение запуска"
    assert_human(*summary_text(created))
    updated = summarize_event(
        "UPDATE", "meeting",
        {"meeting_type": "online", "subject": "Созвон",
         "next_action": "Отправить договор"},
        {"meeting_type": "offline", "subject": "Созвон",
         "next_action": "Отправить обновлённый договор"}, {}, "МТУСИ")
    by_label = {row["label"]: row for row in updated["changes"]}
    assert by_label["Формат встречи"]["new"] == "Очно"
    assert by_label["Дата встречи"] if "Дата встречи" in by_label else True
    assert_human(*summary_text(updated))


def test_meeting_date_formatting():
    summary = summarize_event(
        "CREATE", "meeting", None,
        {"meeting_type": "phone", "subject": "Созвон",
         "meeting_at": "2026-09-26T15:00:00+03:00"}, {}, None)
    row = {r["label"]: r for r in summary["changes"]}["Дата встречи"]
    assert row["new"] == "26.09.2026, 15:00"
    assert_human(row["new"])


# ------------------------------------------------------------------- import

def test_import_and_report():
    started = summarize_event(
        "IMPORT", "report", None,
        {"format": "xlsx", "columns": ["a"], "status": "queued",
         "job_type": "xlsx_import"}, {}, None)
    assert started["title"] == "Запустил импорт данных"
    assert started["section"] == "Импорт"
    report = summarize_event("REPORT_GENERATE", "report", None, {"format": "pdf"}, {}, None)
    assert report["title"] == "Сформировал отчёт"
    sync = summarize_event(
        "IMPORT", "external_sync", None, {"source": "mock"}, {}, None)
    assert sync["title"] == "Синхронизировал внешние данные"
    assert_human(started["title"], report["title"], sync["title"])


# ------------------------------------------------------------------ unknown

def test_unknown_types_never_technical():
    summary = summarize_event(
        "SOMETHING_NEW", "my_custom_thing",
        {"weird_field": "x"}, {"weird_field": "y", "some_id": str(uuid.uuid4())},
        {}, None)
    assert summary["title"] == "Изменение данных"
    assert_human(summary["title"], summary["section"])


def test_deleted_entity_fallback_without_uuid():
    summary = summarize_event(
        "DELETE", "program", {"direction_id": str(uuid.uuid4()),
                              "name": None, "description": None}, None, {}, None)
    assert "название недоступно" in summary["title"] or "Удалён" in summary["title"]
    assert_human(summary["title"], summary["section"])


def test_login_logout_supported():
    assert summarize_event("LOGIN", "config", None, None, {}, None)["title"] == "Вошёл в систему"
    assert summarize_event("LOGOUT", "config", None, None, {}, None)["title"] == "Вышел из системы"


# ------------------------------------------------------------------ security

def test_secret_keys_dropped_from_changes():
    summary = summarize_event(
        "UPDATE", "university",
        {"name": "МТУСИ", "password": "old-secret"},
        {"name": "МТУСИ", "password": "new-secret"}, {}, None)
    fields = [row["field"] for row in summary["changes"]]
    assert "password" not in fields
    joined = "\n".join(summary_text(summary))
    assert "old-secret" not in joined and "new-secret" not in joined


def test_actor_display_name_fallbacks():
    assert actor_display_name("Demo Admin") == "Demo Admin"
    assert actor_display_name("") == "Пользователь (имя недоступно)"
    assert actor_display_name(None) == "Пользователь (имя недоступно)"
    assert actor_display_name("system") == "Система"
    assert actor_display_name("  ") == "Пользователь (имя недоступно)"


def test_format_value_primitives():
    assert format_value("is_active", True) == "Включён"
    assert format_value("is_active", False) == "Выключен"
    assert format_value("is_required", False) == "Необязательный"
    assert format_value("meeting_type", "online") == "Онлайн"
    assert format_value("meeting_type", "email") == "Электронная почта"
    assert format_value("sla_days", 1) == "1 день"
    assert format_value("sla_days", 3) == "3 дня"
    assert format_value("sla_days", 7) == "7 дней"
    assert format_value("file_size", 102400) == "100 КБ"
    assert format_file_size(102400) == "100 КБ"
    assert format_file_size(0) == "0 Б"
    assert format_value("meeting_at", "2026-09-26") == "26.09.2026"
    assert format_value("template_id", str(uuid.uuid4()), {}) == ""
    assert format_value("name", None) == "—"


# ------------------------------------------------------------------ resolver

def _event(entity_type: str, entity_id, old=None, new=None, university_id=None):
    return SimpleNamespace(
        entity_type=entity_type, entity_id=entity_id,
        old_value=old, new_value=new, university_id=university_id)


def test_collect_ids_gathers_everything():
    uni, template, program = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    events = [_event("workflow_stage", uuid.uuid4(), None,
                     {"template_id": str(template), "name": "Этап"}),
              _event("program", uuid.uuid4(), None,
                     {"program_id": str(program), "status": "planned"}, uni)]
    buckets = collect_ids(events)
    assert template in buckets["template"]
    assert program in buckets["program"]
    assert uni in buckets["university"]


def test_resolve_names_batches_queries():
    """One query per table max, regardless of page size."""
    uni = uuid.uuid4()
    events = [_event("university", uuid.uuid4(), None, {"name": "A"}, uni)
              for _ in range(50)]

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    db = Mock()

    def fake_execute(stmt):
        return FakeResult([(uni, "МТУСИ")])

    db.execute.side_effect = fake_execute
    names = resolve_names(db, events)
    assert names[str(uni).lower()] == "МТУСИ"
    # 8 tables + second wave (university/template already fetched) — bounded.
    assert db.execute.call_count <= 10, db.execute.call_count


def test_entity_display_name_prefers_snapshot_then_lookup():
    program_id = uuid.uuid4()
    assert entity_display_name(
        "program", program_id, None,
        {"program_id": str(program_id), "program_name": "Прикладная информатика"},
        {}) == "Прикладная информатика"
    assert entity_display_name(
        "program", program_id, None, {"program_id": str(program_id)},
        {str(program_id).lower(): "Прикладная информатика"}) == "Прикладная информатика"
    assert entity_display_name("program", program_id, None, None, {}) is None


# --------------------------------------------------------------------- router

def _db_event(**overrides):
    from datetime import datetime, timezone

    event_id, entity_id, uni_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = dict(
        id=event_id, created_at=datetime(2026, 9, 26, 17, 32, tzinfo=timezone.utc),
        user_id="keycloak-sub",
        user_name="Demo Admin", role="admin", action="CREATE",
        entity_type="university", entity_id=entity_id,
        university_id=uni_id, old_value=None,
        new_value={"name": "МТУСИ", "city": "Москва"},
        request_id=None, ip_address=None, user_agent=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_router_enrichment_keeps_contract_and_adds_presentation():
    read = AuditEventRead.from_event_enriched(
        _db_event(), {}, "МТУСИ", "МТУСИ")
    # Legacy fields intact (backward compatible).
    assert read.action == "CREATE"
    assert read.entity_type == "university"
    assert read.user_name == "Demo Admin"
    # New enrichment present and human.
    assert read.university_name == "МТУСИ"
    assert read.entity_name == "МТУСИ"
    assert read.presentation is not None
    assert read.presentation["title"] == "Создал ВУЗ «МТУСИ»"
    assert_human(read.presentation["title"])


def test_deleted_university_create_and_delete_keep_historic_name():
    """Regression: after physical deletion the resolver finds nothing
    (names={}), yet the API must return the historic snapshot name,
    never a UUID."""
    gone_id = uuid.uuid4()
    created = _db_event(
        action="CREATE", entity_type="university", entity_id=gone_id,
        university_id=gone_id, old_value=None,
        new_value={"name": "Audit Deleted University", "city": "Moscow"},
    )
    deleted = _db_event(
        action="DELETE", entity_type="university", entity_id=gone_id,
        university_id=gone_id,
        old_value={"name": "Audit Deleted University", "city": "Moscow"},
        new_value=None,
    )
    read_create = AuditEventRead.from_event_enriched(created, {}, None, None)
    read_delete = AuditEventRead.from_event_enriched(deleted, {}, None, None)
    assert read_create.university_name == "Audit Deleted University"
    assert read_delete.university_name == "Audit Deleted University"
    assert read_create.presentation["title"] == "Создал ВУЗ «Audit Deleted University»"
    assert "Audit Deleted University" in read_delete.presentation["title"]
    for read in (read_create, read_delete):
        assert_human(
            read.university_name or "", read.entity_name or "",
            read.presentation["title"], read.presentation["section"],
            *[c for row in read.presentation["changes"] for c in (row["old"], row["new"])],
        )
        # The id is kept for scoping only; it must never reach display strings.
        assert read.university_id == gone_id
