"""Centralized human-readable presentation for audit events.

Single source of truth for turning technical ``audit_events`` rows into
sentences a non-technical employee can understand. Pure functions only —
no DB access here (name resolution lives in ``resolver.py``).

Constraints honoured:
* never invents data — when a name cannot be resolved it uses an explicit
  fallback label, never a raw UUID;
* never leaks secrets — secret-shaped keys are dropped from changes;
* never raises — any unexpected payload degrades to «Изменение данных».
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Dictionaries
# ---------------------------------------------------------------------------

ENTITY_LABELS: dict[str, str] = {
    "university": "ВУЗ",
    "direction": "Направление",
    "program": "Программа",
    "vendor": "Производитель",
    "product": "Продукт",
    "responsible": "Ответственное лицо",
    "meeting": "Встреча",
    "workflow_stage": "Этап Workflow",
    "workflow_instance": "Workflow ВУЗа",
    "workflow_comment": "Комментарий",
    "document": "Файл",
    "report": "Отчёт",
    "config": "Настройки",
    "teacher": "Преподаватель",
    "student": "Студент",
    "license": "Лицензия",
    "contract": "Договор",
    "external_sync": "Синхронизация",
}

SECTION_LABELS: dict[str, str] = {
    "university": "ВУЗы",
    "direction": "Направления",
    "program": "Программы",
    "vendor": "Производители",
    "product": "Продукты",
    "responsible": "Ответственные",
    "meeting": "Встречи",
    "workflow_stage": "Workflow",
    "workflow_instance": "Workflow",
    "workflow_comment": "Workflow",
    "document": "Файлы",
    "report": "Импорт",
    "config": "Администрирование",
    "external_sync": "Импорт",
    "teacher": "Преподаватели",
    "student": "Студенты",
    "license": "Лицензии",
    "contract": "Договоры",
}

FIELD_LABELS: dict[str, str] = {
    "name": "Название",
    "city": "Город",
    "code": "Код",
    "description": "Описание",
    "is_active": "Статус",
    "order_index": "Порядок этапа",
    "is_required": "Обязательный этап",
    "sla_days": "Срок выполнения",
    "direction_id": "Направление",
    "direction_name": "Направление",
    "vendor_id": "Производитель",
    "vendor_name": "Производитель",
    "program_id": "Программа",
    "program_name": "Программа",
    "product_id": "Продукт",
    "product_name": "Продукт",
    "template_id": "Шаблон Workflow",
    "template_name": "Шаблон Workflow",
    "responsible_id": "Ответственный",
    "responsible_name": "Ответственный",
    "old_name": "Ответственный",
    "new_name": "Ответственный",
    "target_name": "Пользователь",
    "university_id": "ВУЗ",
    "university_name": "ВУЗ",
    "role_in_university": "Роль в ВУЗе",
    "is_primary": "Основной ответственный",
    "meeting_type": "Формат встречи",
    "subject": "Тема",
    "outcome": "Итог встречи",
    "next_action": "Следующее действие",
    "next_action_due": "Срок следующего действия",
    "meeting_at": "Дата встречи",
    "original_filename": "Имя файла",
    "file_size": "Размер файла",
    "mime_type": "Тип файла",
    "content": "Комментарий",
    "comment": "Комментарий",
    "is_internal": "Внутренний комментарий",
    "status": "Статус",
    "stages": "Этапов",
    "stage_name": "Этап",
    "stage_id": "Этап",
    "instance_id": "Workflow",
    "format": "Формат",
    "columns": "Колонки",
    "job_type": "Тип задачи",
    "source": "Источник",
    "processed": "Обработано",
    "unresolved": "Не распознано",
    "full_name": "ФИО",
    "email": "Почта",
    "phone": "Телефон",
    "role": "Роль",
    "version": "Версия",
    "reason": "Причина",
    "kind": "Тип изменения",
    "value": "Значение",
}

BOOLEAN_LABELS: dict[str, tuple[str, str]] = {
    "is_active": ("Включён", "Выключен"),
    "is_required": ("Обязательный", "Необязательный"),
    "is_primary": ("Основной", "Дополнительный"),
    "is_internal": ("Внутренний", "Обычный"),
}

ENUM_LABELS: dict[str, dict[str, str]] = {
    "meeting_type": {
        "online": "Онлайн",
        "offline": "Очно",
        "phone": "Телефон",
        "email": "Электронная почта",
    },
    "status": {
        "planned": "Запланирована",
        "active": "Активна",
        "launched": "Запущена",
        "archived": "В архиве",
        "expired": "Истёк",
        "queued": "Поставлен в очередь",
        "draft": "Черновик",
        "signed": "Подписан",
        "terminated": "Расторгнут",
    },
    "role": {
        "admin": "Администратор",
        "manager": "Менеджер",
        "curator": "Куратор",
        "user": "Пользователь",
    },
    "kind_role": {
        "admin": "Администратор",
        "manager": "Менеджер",
        "curator": "Куратор",
        "user": "Пользователь",
    },
}

PRODUCT_STATUS_LABELS: dict[str, str] = {
    "planned": "Запланирован",
    "active": "Активен",
    "expired": "Истёк",
}

ROLE_LABELS: dict[str, str] = {
    "admin": "Администратор",
    "manager": "Менеджер",
    "curator": "Куратор",
    "user": "Пользователь",
}

FALLBACK_OBJECT_NAMES: dict[str, str] = {
    "university": "ВУЗ (название недоступно)",
    "direction": "Направление (название недоступно)",
    "program": "Программа (название недоступно)",
    "vendor": "Производитель (название недоступно)",
    "product": "Продукт (название недоступно)",
    "responsible": "Ответственное лицо (данные недоступны)",
    "meeting": "Встреча (данные недоступны)",
    "workflow_stage": "Этап Workflow (название недоступно)",
    "workflow_instance": "Workflow (название недоступно)",
    "workflow_comment": "Комментарий (недоступен)",
    "document": "Файл (название недоступно)",
    "report": "Отчёт (данные недоступны)",
    "config": "Объект (данные недоступны)",
    "external_sync": "Синхронизация (данные недоступны)",
}

DELETED_OBJECT_NAMES: dict[str, str] = {
    "university": "Удалённый ВУЗ",
    "direction": "Удалённое направление",
    "program": "Удалённая программа",
    "vendor": "Удалённый производитель",
    "product": "Удалённый продукт",
    "responsible": "Удалённое ответственное лицо",
    "meeting": "Удалённая встреча",
    "workflow_stage": "Удалённый этап",
    "workflow_instance": "Удалённый Workflow",
    "workflow_comment": "Удалённый комментарий",
    "document": "Удалённый файл",
}

ACTION_GROUP_LABELS: dict[str, str] = {
    "CREATE": "Создание",
    "UPDATE": "Изменение",
    "DELETE": "Удаление",
    "WORKFLOW_TRANSITION": "Изменение Workflow",
    "ASSIGN_RESPONSIBLE": "Назначение ответственного",
    "IMPORT": "Импорт данных",
    "REPORT_GENERATE": "Формирование отчёта",
    "ADMIN_CONFIG": "Администрирование",
    "LOGIN": "Вход",
    "LOGOUT": "Выход",
}

_USER_STATUS_LABELS: dict[str, str] = {
    "active": "активен",
    "blocked": "заблокирован",
}

_SECRET_KEY = re.compile(
    r"password|passwd|access.?token|refresh.?token|authorization|cookie|"
    r"client.?secret|secret|private.?key|api.?key|jwt",
    re.I,
)
_UUID_LIKE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Keys that are join artefacts / technical duplicates and must not appear
# as separate change rows.
_DUPLICATE_NAME_KEYS = {
    "direction_id": "direction_name",
    "vendor_id": "vendor_name",
    "program_id": "program_name",
    "product_id": "product_name",
    "template_id": "template_name",
    "responsible_id": "responsible_name",
    "university_id": "university_name",
    "stage_id": "stage_name",
}
_INTERNAL_KEYS = {"audit_object_type", "keycloak_sub", "author_keycloak_sub"}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def is_uuid_like(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_LIKE.match(value.strip()))


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY.search(key))


def quote(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"«{text}»"


def format_file_size(size: Any) -> str:
    if isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0:
        return "Размер не указан"
    if size < 1024:
        return f"{int(size)} Б"
    units = ("КБ", "МБ", "ГБ")
    value = float(size) / 1024.0
    unit = units[0]
    for next_unit in units[1:]:
        if value < 1024:
            break
        value /= 1024.0
        unit = next_unit
    formatted = f"{value:.0f}" if value >= 10 else f"{value:.1f}".replace(".", ",")
    return f"{formatted} {unit}"


def format_date_value(value: Any) -> str | None:
    """Format ISO date/datetime to ru-RU. Returns None when not a date."""
    if not isinstance(value, str):
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y, %H:%M")
        if isinstance(value, date):
            return value.strftime("%d.%m.%Y")
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return parsed.strftime("%d.%m.%Y")
    return parsed.strftime("%d.%m.%Y, %H:%M")


def format_sla_days(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    days = int(value)
    if days % 10 == 1 and days % 100 != 11:
        word = "день"
    elif 2 <= days % 10 <= 4 and (days % 100 < 10 or days % 100 >= 20):
        word = "дня"
    else:
        word = "дней"
    return f"{days} {word}"


def format_value(field: str, value: Any, names: dict[str, str] | None = None) -> str:
    """Human string for a single old/new value. Never returns raw UUID."""
    names = names or {}
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        pair = BOOLEAN_LABELS.get(field)
        if pair:
            return pair[0] if value else pair[1]
        return "Да" if value else "Нет"
    if field == "file_size":
        return format_file_size(value)
    if field == "sla_days":
        formatted = format_sla_days(value)
        if formatted is not None:
            return formatted
    if field == "order_index" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value))
    if field in ENUM_LABELS and isinstance(value, str):
        label = ENUM_LABELS[field].get(value.strip().lower())
        if label:
            return label
    if field == "status" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in PRODUCT_STATUS_LABELS:
            return PRODUCT_STATUS_LABELS[lowered]
    if field in ("role", "value") and isinstance(value, str):
        label = ROLE_LABELS.get(value.strip().lower())
        if label:
            return label
    if isinstance(value, str):
        date_formatted = format_date_value(value)
        if date_formatted is not None:
            return date_formatted
        if is_uuid_like(value):
            resolved = names.get(value.strip().lower()) or names.get(value.strip())
            if resolved:
                return resolved
            return ""
    if isinstance(value, list):
        if not value:
            return "—"
        parts = [format_value(field, item, names) for item in value]
        parts = [part for part in parts if part and part != "—"]
        return "; ".join(parts) if parts else f"Элементов: {len(value)}"
    if isinstance(value, dict):
        return f"Полей: {len(value)}"
    return str(value)


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def classify_config(old: Any, new: Any) -> str:
    """Semantic subtype for the overloaded ``config`` entity type."""
    payload = new if isinstance(new, dict) else (old if isinstance(old, dict) else {})
    if not isinstance(payload, dict):
        return "unknown"
    if payload.get("audit_object_type") == "workflow_template":
        return "workflow_template"
    kind = payload.get("kind")
    if isinstance(kind, str) and kind in (
        "role", "scope", "status", "invite", "password_reset_requested",
    ):
        return "user"
    if any(key in payload for key in ("is_active", "template_name")) and "kind" not in payload:
        # Workflow template snapshots: {name, description?, is_active}.
        if "name" in payload:
            return "workflow_template"
    return "unknown"


def actor_display_name(user_name: Any, user_id: Any = None) -> str:
    name = (str(user_name).strip() if user_name else "")
    if name and name.lower() not in ("system", "unknown"):
        return name
    if str(user_id or "").strip().lower() == "system" or name.lower() == "system":
        return "Система"
    return "Пользователь (имя недоступно)"


def _payload_name(payload: Any, *keys: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and not is_uuid_like(value):
            return value.strip()
    return None


def _resolve_reference(
    raw: Any,
    display: Any,
    names: dict[str, str],
    fallback: str,
) -> str:
    """Turn an id (+ optional pre-saved display name) into a human name."""
    if isinstance(display, str) and display.strip() and not is_uuid_like(display):
        return display.strip()
    if isinstance(raw, str) and raw.strip() and not is_uuid_like(raw):
        return raw.strip()
    if isinstance(raw, str) and is_uuid_like(raw):
        resolved = names.get(raw.strip().lower()) or names.get(raw.strip())
        if resolved:
            return resolved
    return fallback


# ---------------------------------------------------------------------------
# Main summarizer
# ---------------------------------------------------------------------------

def summarize_event(
    action: Any,
    entity_type: Any,
    old: Any,
    new: Any,
    names: dict[str, str] | None = None,
    university_name: str | None = None,
) -> dict[str, Any]:
    """Build a human presentation for one audit event.

    ``names`` maps lowercase UUID strings to display names (batch-resolved
    by ``resolver.py`` or pre-saved ``*_name`` snapshot fields).
    """
    names = names or {}
    try:
        return _summarize(str(action or "").upper(), str(entity_type or ""),
                          old, new, names, university_name)
    except Exception:
        return {
            "title": "Изменение данных",
            "section": "Данные",
            "object_name": None,
            "changes": [],
            "note": None,
        }


def _change_rows(
    old: Any,
    new: Any,
    names: dict[str, str],
    skip: set[str] | None = None,
    only: set[str] | None = None,
) -> list[dict[str, str]]:
    old_map = old if isinstance(old, dict) else {}
    new_map = new if isinstance(new, dict) else {}
    skip = set(skip or set()) | _INTERNAL_KEYS
    keys = [key for key in list(old_map) + [k for k in new_map if k not in old_map]]
    if only is not None:
        keys = [key for key in keys if key in only]
    rows: list[dict[str, str]] = []
    for key in keys:
        if key in skip or is_secret_key(key):
            continue
        twin = _DUPLICATE_NAME_KEYS.get(key)
        twin_present = (
            twin is not None
            and (twin in old_map or twin in new_map)
            and twin != key
        )
        old_raw = old_map.get(key)
        new_raw = new_map.get(key)
        # An id with a sibling *_name field is rendered via the name only.
        if twin_present and key.endswith("_id"):
            display_old = old_map.get(twin)
            display_new = new_map.get(twin)
            old_text = _resolve_reference(old_raw, display_old, names, "")
            new_text = _resolve_reference(new_raw, display_new, names, "")
            if old_text == new_text:
                continue
            rows.append({
                "field": key,
                "label": field_label(twin),
                "old": old_text or "—",
                "new": new_text or "—",
            })
            continue
        if key.endswith("_name") and key[:-5] + "_id" in {**old_map, **new_map}:
            continue
        old_text = format_value(key, old_raw, names)
        new_text = format_value(key, new_raw, names)
        if not old_text and not new_text:
            continue
        if old_text == new_text:
            continue
        rows.append({
            "field": key,
            "label": field_label(key),
            "old": old_text or "—",
            "new": new_text or "—",
        })
    return rows


def _summarize(
    action: str,
    entity_type: str,
    old: Any,
    new: Any,
    names: dict[str, str],
    university_name: str | None,
) -> dict[str, Any]:
    entity_key = entity_type.strip().lower()
    uni = university_name or _payload_name(new, "university_name") or _payload_name(old, "university_name")

    # ---- workflow transition (most valuable event) ----
    if action == "WORKFLOW_TRANSITION":
        old_map = old if isinstance(old, dict) else {}
        new_map = new if isinstance(new, dict) else {}
        from_stage = old_map.get("stage_name") or _resolve_reference(
            old_map.get("stage_id"), None, names, "предыдущий этап")
        to_stage = new_map.get("stage_name") or _resolve_reference(
            new_map.get("stage_id"), None, names, "следующий этап")
        comment = new_map.get("comment")
        comment_text = comment.strip() if isinstance(comment, str) and comment.strip() else None
        where = f" {quote(uni)}" if uni else ""
        title = f"Перевёл{where} с этапа {quote(from_stage)} на этап {quote(to_stage)}"
        changes = [
            {"field": "stage_name", "label": "Этап",
             "old": str(from_stage), "new": str(to_stage)},
        ]
        if comment_text:
            changes.append({"field": "comment", "label": "Комментарий",
                            "old": "—", "new": comment_text})
        return {"title": title, "section": "Workflow", "object_name": uni,
                "changes": changes, "note": None}

    # ---- assign responsible ----
    if action == "ASSIGN_RESPONSIBLE":
        old_map = old if isinstance(old, dict) else {}
        new_map = new if isinstance(new, dict) else {}
        old_name = _resolve_reference(
            old_map.get("responsible_id"), old_map.get("responsible_name"),
            names, "")
        new_name = _resolve_reference(
            new_map.get("responsible_id"), new_map.get("responsible_name"),
            names, "")
        reason = new_map.get("reason")
        reason_text = reason.strip() if isinstance(reason, str) and reason.strip() else None
        where = f" за {quote(uni)}" if uni else ""
        if new_name and not old_name:
            title = f"Назначил {quote(new_name)} ответственным{where}"
        elif old_name and not new_name:
            title = f"Снял {quote(old_name)} с ответственных{where}"
        elif old_name and new_name and old_name != new_name:
            title = f"Сменил ответственного{where}: {quote(old_name)} → {quote(new_name)}"
        elif new_name:
            title = f"Назначил {quote(new_name)} ответственным{where}"
        else:
            title = f"Изменил ответственного{where}"
        changes = []
        if old_name or new_name:
            changes.append({"field": "responsible_id", "label": "Ответственный",
                            "old": old_name or "—", "new": new_name or "—"})
        if reason_text:
            changes.append({"field": "reason", "label": "Причина",
                            "old": "—", "new": reason_text})
        return {"title": title, "section": "Ответственные",
                "object_name": new_name or old_name, "changes": changes, "note": None}

    # ---- overloaded config: workflow template vs user administration ----
    subtype = classify_config(old, new) if entity_key == "config" else ""
    if entity_key == "config" and subtype == "workflow_template":
        return _summarize_template(action, old, new, names)
    if entity_key == "config" and subtype == "user":
        return _summarize_user_admin(action, old, new, names)

    # ---- workflow stage ----
    if entity_key == "workflow_stage":
        return _summarize_stage(action, old, new, names)

    # ---- workflow instance creation ----
    if entity_key == "workflow_instance" and action == "CREATE":
        template = _payload_name(new, "template_name") or _resolve_reference(
            (new or {}).get("template_id") if isinstance(new, dict) else None,
            None, names, "Workflow (название недоступно)")
        where = f" для {quote(uni)}" if uni else ""
        return {"title": f"Запустил Workflow {quote(template)}{where}",
                "section": "Workflow", "object_name": template,
                "changes": [], "note": None}

    # ---- comments ----
    if entity_key == "workflow_comment":
        stage = _resolve_reference(
            (new if isinstance(new, dict) else old or {}).get("stage_id")
            if isinstance(new if isinstance(new, dict) else old, dict) else None,
            None, names, "")
        content = _payload_name(new, "content") or _payload_name(old, "content")
        if action == "CREATE":
            title = f"Добавил комментарий{(' к этапу ' + quote(stage)) if stage else ''}"
        elif action == "DELETE":
            title = "Удалил комментарий"
        else:
            title = "Изменил комментарий"
        changes = []
        if content:
            changes.append({"field": "content", "label": "Комментарий",
                            "old": "—" if action == "CREATE" else (content if action == "DELETE" else content),
                            "new": content if action != "DELETE" else "—"})
        return {"title": title, "section": "Workflow", "object_name": stage or None,
                "changes": changes, "note": None}

    # ---- attachments (entity_type=document produced by workflow uploads) ----
    if entity_key == "document":
        filename = _payload_name(new, "original_filename") or _payload_name(old, "original_filename")
        size_raw = (new if isinstance(new, dict) else old or {}).get("file_size") \
            if isinstance(new if isinstance(new, dict) else old, dict) else None
        size_text = format_file_size(size_raw) if size_raw is not None else None
        name = filename or "Файл (название недоступно)"
        title = f"Загрузил файл {quote(name)}" if action == "CREATE" else (
            f"Удалил файл {quote(name)}" if action == "DELETE" else f"Изменил файл {quote(name)}")
        changes = []
        if size_text:
            changes.append({"field": "file_size", "label": "Размер файла",
                            "old": "—" if action == "CREATE" else size_text,
                            "new": size_text if action == "CREATE" else "—"})
        return {"title": title, "section": "Файлы", "object_name": name,
                "changes": changes, "note": None}

    # ---- meetings ----
    if entity_key == "meeting":
        subject = _payload_name(new, "subject") or _payload_name(old, "subject")
        where = f" с {quote(uni)}" if uni else ""
        if action == "CREATE":
            title = f"Создал встречу{where}"
        elif action == "DELETE":
            title = f"Удалил встречу{where}"
        else:
            title = f"Изменил встречу{where}"
        changes = _change_rows(old, new, names)
        return {"title": title, "section": "Встречи",
                "object_name": subject, "changes": changes, "note": None}

    # ---- program / product attach vs global CRUD ----
    if entity_key in ("program", "product") and action == "CREATE" \
            and isinstance(new, dict) and f"{entity_key}_id" in new:
        id_key = f"{entity_key}_id"
        name_key = f"{entity_key}_name"
        obj_name = _resolve_reference(new.get(id_key), new.get(name_key), names,
                                      FALLBACK_OBJECT_NAMES.get(entity_key, "Объект (данные недоступны)"))
        verb = "Добавил программу" if entity_key == "program" else "Добавил продукт"
        where = f" ВУЗу {quote(uni)}" if uni else ""
        status_raw = new.get("status")
        status_text = None
        if isinstance(status_raw, str):
            lowered = status_raw.strip().lower()
            if entity_key == "product":
                status_text = PRODUCT_STATUS_LABELS.get(lowered)
            else:
                status_text = ENUM_LABELS["status"].get(lowered)
        if status_text in (None, "", "—"):
            status_text = None
        title = f"{verb} {quote(obj_name)}{where}"
        changes = []
        if status_text:
            changes.append({"field": "status", "label": "Статус",
                            "old": "—", "new": status_text})
        return {"title": title,
                "section": SECTION_LABELS.get(entity_key, "Система"),
                "object_name": obj_name, "changes": changes, "note": None}

    # ---- import / report ----
    if action == "IMPORT" or (entity_key == "report" and action in ("CREATE", "UPDATE")):
        job = new if isinstance(new, dict) else (old if isinstance(old, dict) else {})
        job_type = job.get("job_type") if isinstance(job, dict) else None
        if job_type == "xlsx_import" or entity_key in ("report", "external_sync"):
            if entity_key == "external_sync":
                title = "Синхронизировал внешние данные"
            else:
                count = (job.get("university_count")
                         if isinstance(job, dict) else None)
                if isinstance(count, int) and count > 1:
                    title = f"Запустил импорт данных для {count} ВУЗов"
                elif uni:
                    title = f"Запустил импорт данных для {quote(uni)}"
                else:
                    title = "Запустил импорт данных"
            return {"title": title, "section": "Импорт", "object_name": None,
                    "changes": [], "note": None}
    if action == "REPORT_GENERATE":
        return {"title": "Сформировал отчёт", "section": "Импорт",
                "object_name": None, "changes": [], "note": None}

    # ---- generic catalog CRUD ----
    if entity_key in ENTITY_LABELS and action in ("CREATE", "UPDATE", "DELETE"):
        label = ENTITY_LABELS[entity_key]
        obj_name = _payload_name(new, "name", "full_name", "subject", "original_filename") \
            or _payload_name(old, "name", "full_name", "subject", "original_filename")
        if not obj_name and uni and entity_key == "university":
            obj_name = uni
        if not obj_name:
            resolved_entity = names.get(f"entity:{entity_key}") or ""
            obj_name = resolved_entity
        verb = {"CREATE": "Создал", "UPDATE": "Изменил",
                "DELETE": "Удалил"}.get(action, "Изменил")
        # Feminine nouns take «Создала»-style verbs; keep neutral past tense
        # with masculine agreement except known feminine labels.
        if label in ("Программа", "Встреча", "Лицензия"):
            verb = {"CREATE": "Создала", "UPDATE": "Изменила",
                    "DELETE": "Удалила"}.get(action, verb)
        if entity_key == "responsible":
            verb = {"CREATE": "Добавил ответственного",
                    "UPDATE": "Изменил ответственного",
                    "DELETE": "Удалил ответственного"}.get(action, verb)
            title = f"{verb} {quote(obj_name)}" if obj_name else verb
        elif entity_key == "university":
            title = f"{verb} ВУЗ {quote(obj_name)}" if obj_name else f"{verb} ВУЗ"
        else:
            title = f"{verb}: {label} {quote(obj_name)}" if obj_name else f"{verb}: {label.lower()}"
        if not obj_name:
            title = f"{verb}: {(DELETED_OBJECT_NAMES if action == 'DELETE' else FALLBACK_OBJECT_NAMES).get(entity_key, 'Объект (данные недоступны)')}"
        changes = _change_rows(old, new, names) if action == "UPDATE" else []
        if action in ("CREATE", "DELETE"):
            # Show meaningful context for create/delete as well.
            changes = _change_rows(old, new, names,
                                   skip={"name", "full_name", "subject"})
        return {"title": title,
                "section": SECTION_LABELS.get(entity_key, "Система"),
                "object_name": obj_name or None, "changes": changes, "note": None}

    if action in ("LOGIN", "LOGOUT"):
        return {"title": "Вошёл в систему" if action == "LOGIN" else "Вышел из системы",
                "section": "Система", "object_name": None, "changes": [], "note": None}

    # ---- total fallback: never technical ----
    return {"title": "Изменение данных", "section": SECTION_LABELS.get(entity_key, "Данные"),
            "object_name": None,
            "changes": _change_rows(old, new, names) if isinstance(old, dict) or isinstance(new, dict) else [],
            "note": None}


def _summarize_template(action: str, old: Any, new: Any, names: dict[str, str]) -> dict[str, Any]:
    name = _payload_name(new, "name") or _payload_name(old, "name") or "Шаблон Workflow (название недоступно)"
    old_map = old if isinstance(old, dict) else {}
    new_map = new if isinstance(new, dict) else {}
    if action == "CREATE" or not isinstance(old, dict):
        return {"title": f"Создал шаблон Workflow {quote(name)}",
                "section": "Workflow", "object_name": name, "changes": [], "note": None}
    old_active = old_map.get("is_active")
    new_active = new_map.get("is_active")
    if old_active is True and new_active is False:
        return {"title": f"Отключил шаблон Workflow {quote(name)}",
                "section": "Workflow", "object_name": name,
                "changes": [{"field": "is_active", "label": "Статус",
                             "old": "Включён", "new": "Выключен"}], "note": None}
    if old_active is False and new_active is True:
        return {"title": f"Включил шаблон Workflow {quote(name)}",
                "section": "Workflow", "object_name": name,
                "changes": [{"field": "is_active", "label": "Статус",
                             "old": "Выключен", "new": "Включён"}], "note": None}
    return {"title": f"Изменил шаблон Workflow {quote(name)}",
            "section": "Workflow", "object_name": name,
            "changes": _change_rows(old, new, names), "note": None}


def _summarize_stage(action: str, old: Any, new: Any, names: dict[str, str]) -> dict[str, Any]:
    payload = new if isinstance(new, dict) else (old if isinstance(old, dict) else {})
    name = _payload_name(new, "name") or _payload_name(old, "name") or "Этап Workflow (название недоступно)"
    template = _payload_name(new, "template_name") or _payload_name(old, "template_name")
    if not template and isinstance(payload, dict):
        template = _resolve_reference(payload.get("template_id"), None, names, "")
    old_map = old if isinstance(old, dict) else {}
    new_map = new if isinstance(new, dict) else {}
    if action == "CREATE" or not isinstance(old, dict):
        title = f"Добавил этап {quote(name)}"
        if template:
            title += f" в Workflow {quote(template)}"
        return {"title": title, "section": "Workflow", "object_name": name,
                "changes": [], "note": None}
    old_active = old_map.get("is_active")
    new_active = new_map.get("is_active")
    rest_old = {k: v for k, v in old_map.items() if k != "is_active"}
    rest_new = {k: v for k, v in new_map.items() if k != "is_active"}
    if old_active is True and new_active is False and rest_old == rest_new:
        return {"title": f"Отключил этап {quote(name)}",
                "section": "Workflow", "object_name": name,
                "changes": [{"field": "is_active", "label": "Статус",
                             "old": "Включён", "new": "Выключен"}], "note": None}
    if old_active is False and new_active is True and rest_old == rest_new:
        return {"title": f"Включил этап {quote(name)}",
                "section": "Workflow", "object_name": name,
                "changes": [{"field": "is_active", "label": "Статус",
                             "old": "Выключен", "new": "Включён"}], "note": None}
    return {"title": f"Изменил этап {quote(name)}",
            "section": "Workflow", "object_name": name,
            "changes": _change_rows(old, new, names), "note": None}


def _keycloak_display(payload: Any) -> str | None:
    """Best-effort display name from a Keycloak user dict. Never a UUID."""
    if not isinstance(payload, dict):
        return None
    first = str(payload.get("firstName") or "").strip()
    last = str(payload.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    for key in ("username", "email"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _summarize_user_admin(action: str, old: Any, new: Any, names: dict[str, str]) -> dict[str, Any]:
    old_map = old if isinstance(old, dict) else {}
    new_map = new if isinstance(new, dict) else {}
    kind = new_map.get("kind") if isinstance(new_map.get("kind"), str) else old_map.get("kind")
    target = _payload_name(new, "target_name") or _payload_name(old, "target_name") \
        or "Пользователь (данные недоступны)"
    before = old_map.get("value")
    after = new_map.get("value")
    if kind == "role":
        old_role = ROLE_LABELS.get(str(before or "").lower(), str(before or "—"))
        new_role = ROLE_LABELS.get(str(after or "").lower(), str(after or "—"))
        return {"title": f"Изменил роль пользователя {quote(target)}",
                "section": "Пользователи", "object_name": target,
                "changes": [{"field": "role", "label": "Роль",
                             "old": old_role, "new": new_role}], "note": None}
    if kind == "scope":
        old_ids = before if isinstance(before, list) else []
        new_ids = after if isinstance(after, list) else []
        added = [names.get(str(item).lower(), "") or "" for item in new_ids
                 if item not in old_ids]
        removed = [names.get(str(item).lower(), "") or "" for item in old_ids
                   if item not in new_ids]
        added = [name for name in added if name]
        removed = [name for name in removed if name]
        changes = []
        if added:
            changes.append({"field": "scope_added", "label": "Добавлен доступ",
                            "old": "—", "new": "; ".join(added)})
        if removed:
            changes.append({"field": "scope_removed", "label": "Убран доступ",
                            "old": "; ".join(removed), "new": "—"})
        if not changes:
            scope_note = "Состав доступа не изменился"
        else:
            scope_note = None
        return {"title": f"Изменил доступ пользователя {quote(target)}",
                "section": "Пользователи", "object_name": target,
                "changes": changes, "note": scope_note}
    if kind == "status":
        if str(after).lower() == "blocked":
            title = f"Заблокировал пользователя {quote(target)}"
        else:
            title = f"Восстановил доступ пользователя {quote(target)}"
        old_text = _USER_STATUS_LABELS.get(str(before).lower(), str(before or "—"))
        new_text = _USER_STATUS_LABELS.get(str(after).lower(), str(after or "—"))
        return {"title": title, "section": "Пользователи", "object_name": target,
                "changes": [{"field": "status", "label": "Статус",
                             "old": old_text, "new": new_text}], "note": None}
    if kind == "invite":
        role = None
        if isinstance(after, dict):
            role = ROLE_LABELS.get(str(after.get("role") or "").lower())
        title = f"Пригласил пользователя {quote(target)}"
        changes = []
        if role:
            changes.append({"field": "role", "label": "Роль",
                            "old": "—", "new": role})
        return {"title": title, "section": "Пользователи", "object_name": target,
                "changes": changes, "note": None}
    if kind == "password_reset_requested":
        return {"title": f"Отправил сброс пароля пользователю {quote(target)}",
                "section": "Пользователи", "object_name": target,
                "changes": [], "note": None}
    return {"title": f"Изменил пользователя {quote(target)}",
            "section": "Пользователи", "object_name": target,
            "changes": _change_rows(old, new, names), "note": None}
