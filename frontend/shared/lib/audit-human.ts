import { formatFileSize } from './formatters';
import type { AuditEvent, AuditJsonValue } from './audit-repository';

export interface AuditChangeRow {
  field: string;
  label: string;
  old: string;
  next: string;
}

export interface AuditSummary {
  title: string;
  section: string;
  objectName: string | null;
  changes: AuditChangeRow[];
  note: string | null;
  actorName: string;
  actorRole: string | null;
}

/** «Что произошло» — пользовательские группы вместо технических action. */
export const AUDIT_ACTION_GROUP_OPTIONS: ReadonlyArray<{ id: string; label: string; actions: string[] }> = [
  { id: 'create', label: 'Создание', actions: ['CREATE'] },
  { id: 'update', label: 'Изменение', actions: ['UPDATE'] },
  { id: 'delete', label: 'Удаление', actions: ['DELETE'] },
  { id: 'workflow', label: 'Изменение Workflow', actions: ['WORKFLOW_TRANSITION'] },
  { id: 'assign', label: 'Назначение ответственного', actions: ['ASSIGN_RESPONSIBLE'] },
  { id: 'import', label: 'Импорт данных', actions: ['IMPORT'] },
  { id: 'report', label: 'Формирование отчёта', actions: ['REPORT_GENERATE'] },
  { id: 'admin', label: 'Администрирование', actions: ['ADMIN_CONFIG'] },
];

/** «Раздел» — пользовательские разделы вместо «Тип сущности». */
export const AUDIT_SECTION_OPTIONS: ReadonlyArray<{ id: string; label: string; entityTypes: string[] }> = [
  { id: 'universities', label: 'ВУЗы', entityTypes: ['university'] },
  { id: 'workflow', label: 'Workflow', entityTypes: ['workflow_instance', 'workflow_stage', 'workflow_comment'] },
  { id: 'programs', label: 'Программы', entityTypes: ['program'] },
  { id: 'products', label: 'Продукты', entityTypes: ['product'] },
  { id: 'catalogs', label: 'Справочники', entityTypes: ['direction', 'vendor'] },
  { id: 'responsible', label: 'Ответственные', entityTypes: ['responsible'] },
  { id: 'meetings', label: 'Встречи', entityTypes: ['meeting'] },
  { id: 'files', label: 'Файлы', entityTypes: ['document'] },
  { id: 'users', label: 'Пользователи и шаблоны', entityTypes: ['config'] },
  { id: 'import', label: 'Импорт и отчёты', entityTypes: ['report', 'external_sync'] },
];

const ENTITY_LABELS: Record<string, string> = {
  university: 'ВУЗ',
  direction: 'Направление',
  program: 'Программа',
  vendor: 'Производитель',
  product: 'Продукт',
  responsible: 'Ответственное лицо',
  meeting: 'Встреча',
  workflow_stage: 'Этап Workflow',
  workflow_instance: 'Workflow ВУЗа',
  workflow_comment: 'Комментарий',
  document: 'Файл',
  report: 'Отчёт',
  config: 'Настройки',
  external_sync: 'Синхронизация',
};

const FIELD_LABELS: Record<string, string> = {
  name: 'Название',
  city: 'Город',
  code: 'Код',
  description: 'Описание',
  is_active: 'Статус',
  order_index: 'Порядок этапа',
  is_required: 'Обязательный этап',
  sla_days: 'Срок выполнения',
  direction_id: 'Направление',
  direction_name: 'Направление',
  vendor_id: 'Производитель',
  vendor_name: 'Производитель',
  program_id: 'Программа',
  program_name: 'Программа',
  product_id: 'Продукт',
  product_name: 'Продукт',
  template_id: 'Шаблон Workflow',
  template_name: 'Шаблон Workflow',
  responsible_id: 'Ответственный',
  responsible_name: 'Ответственный',
  responsible: 'Ответственный',
  old_name: 'Ответственный',
  new_name: 'Ответственный',
  target_name: 'Пользователь',
  university_id: 'ВУЗ',
  university_name: 'ВУЗ',
  role_in_university: 'Роль в ВУЗе',
  is_primary: 'Основной ответственный',
  meeting_type: 'Формат встречи',
  subject: 'Тема',
  outcome: 'Итог встречи',
  next_action: 'Следующее действие',
  next_action_due: 'Срок следующего действия',
  meeting_at: 'Дата встречи',
  original_filename: 'Имя файла',
  file_name: 'Имя файла',
  file_size: 'Размер файла',
  mime_type: 'Тип файла',
  content: 'Комментарий',
  comment: 'Комментарий',
  is_internal: 'Внутренний комментарий',
  status: 'Статус',
  stages: 'Этапов',
  stage_name: 'Этап',
  stage_id: 'Этап',
  instance_id: 'Workflow',
  format: 'Формат',
  columns: 'Колонки',
  job_type: 'Тип задачи',
  source: 'Источник',
  processed: 'Обработано',
  unresolved: 'Не распознано',
  full_name: 'ФИО',
  email: 'Почта',
  phone: 'Телефон',
  role: 'Роль',
  version: 'Версия',
  reason: 'Причина',
  deadline: 'Срок',
};

const BOOLEAN_LABELS: Record<string, [string, string]> = {
  is_active: ['Включён', 'Выключен'],
  is_required: ['Обязательный', 'Необязательный'],
  is_primary: ['Основной', 'Дополнительный'],
  is_internal: ['Внутренний', 'Обычный'],
};

const ENUM_LABELS: Record<string, Record<string, string>> = {
  meeting_type: { online: 'Онлайн', offline: 'Очно', phone: 'Телефон', email: 'Электронная почта' },
  status: {
    planned: 'Запланирована', active: 'Активна', launched: 'Запущена',
    archived: 'В архиве', expired: 'Истёк', queued: 'Поставлен в очередь',
    draft: 'Черновик', signed: 'Подписан', terminated: 'Расторгнут',
    attention: 'Требует внимания', current: 'Текущий',
  },
  role: { admin: 'Администратор', manager: 'Менеджер', curator: 'Куратор', user: 'Пользователь' },
};

const PRODUCT_STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', active: 'Активен', expired: 'Истёк',
};

const ROLE_LABELS: Record<string, string> = {
  admin: 'Администратор', manager: 'Менеджер', curator: 'Куратор', user: 'Пользователь',
};

const FALLBACK_NAMES: Record<string, string> = {
  university: 'ВУЗ (название недоступно)',
  direction: 'Направление (название недоступно)',
  program: 'Программа (название недоступно)',
  vendor: 'Производитель (название недоступно)',
  product: 'Продукт (название недоступно)',
  responsible: 'Ответственное лицо (данные недоступны)',
  meeting: 'Встреча (данные недоступны)',
  workflow_stage: 'Этап Workflow (название недоступно)',
  workflow_instance: 'Workflow (название недоступно)',
  workflow_comment: 'Комментарий (недоступен)',
  document: 'Файл (название недоступно)',
  report: 'Отчёт (данные недоступны)',
  config: 'Объект (данные недоступны)',
  external_sync: 'Синхронизация (данные недоступны)',
};

const UUID_LIKE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const SECRET_KEY = /password|passwd|access.?token|refresh.?token|authorization|cookie|client.?secret|secret|private.?key|api.?key|jwt/i;
const INTERNAL_KEYS = new Set(['audit_object_type', 'keycloak_sub', 'author_keycloak_sub']);

export function isUuidLike(value: unknown): boolean {
  return typeof value === 'string' && UUID_LIKE.test(value.trim());
}

function quote(value: string): string {
  return `«${value}»`;
}

function humanizeKey(key: string): string {
  const normalized = key.trim().replace(/[\s_]+/g, ' ').toLocaleLowerCase('ru-RU');
  return normalized ? normalized.charAt(0).toLocaleUpperCase('ru-RU') + normalized.slice(1) : key;
}

export function formatAuditFieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? humanizeKey(field);
}

export function getAuditEntityLabel(entityType: string): string {
  return ENTITY_LABELS[entityType.trim().toLowerCase()] ?? 'Системный объект';
}

export function getAuditRoleLabel(role?: string): string {
  if (!role) return '—';
  return ROLE_LABELS[role.trim().toLowerCase()] ?? humanizeKey(role);
}

export function auditActorName(event: Pick<AuditEvent, 'user'>): string {
  const id = event.user.id.trim();
  const name = event.user.name.trim();
  if (id.toLowerCase() === 'system' || name.toLowerCase() === 'system') return 'Система';
  if (!name) return 'Пользователь (имя недоступно)';
  const lowered = name.toLocaleLowerCase('ru-RU');
  if (lowered === 'unknown') return 'Пользователь (имя недоступно)';
  // Keycloak sub or any UUID-like string is never a display name.
  if (isUuidLike(name)) return 'Пользователь (имя недоступно)';
  if (id && name === id) return 'Пользователь (имя недоступно)';
  return name;
}

/**
 * Centralized university display for the audit UI — the single place that
 * decides what goes into the «ВУЗ / Раздел» column. Never returns a UUID:
 * human name → historic object name (deleted universities) → '' (callers
 * render the section instead).
 */
export function universityDisplayName(event: Pick<AuditEvent, 'university' | 'entity' | 'presentation'>): string {
  const raw = event.university.name.trim();
  if (raw && raw !== '—' && !isUuidLike(raw)) return raw;
  const presentation = event.presentation;
  if (event.entity.type.trim().toLowerCase() === 'university' && presentation && typeof presentation === 'object' && !Array.isArray(presentation)) {
    const objectName = (presentation as { object_name?: unknown }).object_name;
    if (typeof objectName === 'string' && objectName.trim() && !isUuidLike(objectName)) return objectName.trim();
  }
  return '';
}

function formatDateValue(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(text) ? new Date(`${text}T00:00:00`) : new Date(text);
  if (Number.isNaN(date.getTime()) || !/\d{4}-\d{2}-\d{2}/.test(text)) return null;
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return `${day}.${month}.${year}`;
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${day}.${month}.${year}, ${hours}:${minutes}`;
}

function pluralizeDays(days: number): string {
  if (days % 10 === 1 && days % 100 !== 11) return 'день';
  if (days % 10 >= 2 && days % 10 <= 4 && (days % 100 < 10 || days % 100 >= 20)) return 'дня';
  return 'дней';
}

export function formatAuditFieldValue(field: string, value: AuditJsonValue | undefined): string {
  if (value === undefined || value === null || value === '') return '—';
  if (typeof value === 'boolean') {
    const pair = BOOLEAN_LABELS[field];
    if (pair) return value ? pair[0] : pair[1];
    return value ? 'Да' : 'Нет';
  }
  if (field === 'file_size' && typeof value === 'number') return formatFileSize(value);
  if (field === 'sla_days' && typeof value === 'number') return `${value} ${pluralizeDays(value)}`;
  if (field === 'order_index' && typeof value === 'number') return String(value);
  if (typeof value === 'string') {
    const enumLabel = ENUM_LABELS[field]?.[value.trim().toLowerCase()];
    if (enumLabel) return enumLabel;
    const dateLabel = formatDateValue(value);
    if (dateLabel !== null) return dateLabel;
    if (isUuidLike(value)) return '';
    return value;
  }
  if (typeof value === 'number') return new Intl.NumberFormat('ru-RU').format(value);
  if (Array.isArray(value)) {
    if (!value.length) return '—';
    const parts = value.map((item) => formatAuditFieldValue(field, item)).filter((part) => part && part !== '—');
    return parts.length ? parts.join('; ') : `Элементов: ${value.length}`;
  }
  return `Полей: ${Object.keys(value).length}`;
}

type JsonObject = { [key: string]: AuditJsonValue };

function formatAuditFieldValueWithOverride(field: string, value: AuditJsonValue | undefined, enumOverride: Record<string, Record<string, string>>): string {
  const override = enumOverride[field];
  if (override && typeof value === 'string') {
    const label = override[value.trim().toLowerCase()];
    if (label) return label;
  }
  return formatAuditFieldValue(field, value);
}

function asObject(value: AuditJsonValue | undefined): JsonObject | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject) : null;
}

function payloadName(payload: JsonObject | null, ...keys: string[]): string | null {
  if (!payload) return null;
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim() && !isUuidLike(value)) return value.trim();
  }
  return null;
}

function resolveRef(raw: AuditJsonValue | undefined, display: AuditJsonValue | undefined, fallback: string): string {
  if (typeof display === 'string' && display.trim() && !isUuidLike(display)) return display.trim();
  if (typeof raw === 'string' && raw.trim() && !isUuidLike(raw)) return raw.trim();
  return fallback;
}

function changeRows(oldObj: JsonObject | null, newObj: JsonObject | null, skip: Set<string> = new Set(), enumOverride: Record<string, Record<string, string>> = {}): AuditChangeRow[] {
  const rows: AuditChangeRow[] = [];
  const keys = [...Object.keys(oldObj ?? {}), ...Object.keys(newObj ?? {}).filter((key) => !(key in (oldObj ?? {})))];
  const twin: Record<string, string> = {
    direction_id: 'direction_name', vendor_id: 'vendor_name', program_id: 'program_name',
    product_id: 'product_name', template_id: 'template_name', responsible_id: 'responsible_name',
    university_id: 'university_name', stage_id: 'stage_name',
  };
  for (const key of keys) {
    if (skip.has(key) || INTERNAL_KEYS.has(key) || SECRET_KEY.test(key)) continue;
    const oldRaw = oldObj?.[key];
    const newRaw = newObj?.[key];
    const twinKey = twin[key];
    if (twinKey && (oldObj?.[twinKey] !== undefined || newObj?.[twinKey] !== undefined)) {
      if (key.endsWith('_id')) {
        const oldText = resolveRef(oldRaw, oldObj?.[twinKey], '');
        const newText = resolveRef(newRaw, newObj?.[twinKey], '');
        if (!oldText && !newText) continue;
        if (oldText === newText) continue;
        rows.push({ field: key, label: formatAuditFieldLabel(twinKey), old: oldText || '—', next: newText || '—' });
        continue;
      }
      continue;
    }
    if (key.endsWith('_name')) {
      const idKey = `${key.slice(0, -5)}_id`;
      if (oldObj?.[idKey] !== undefined || newObj?.[idKey] !== undefined) continue;
    }
    const oldText = formatAuditFieldValueWithOverride(key, oldRaw, enumOverride);
    const newText = formatAuditFieldValueWithOverride(key, newRaw, enumOverride);
    if (!oldText && !newText) continue;
    if (oldText === newText) continue;
    rows.push({ field: key, label: formatAuditFieldLabel(key), old: oldText || '—', next: newText || '—' });
  }
  return rows;
}

function classifyConfig(oldObj: JsonObject | null, newObj: JsonObject | null): string {
  const payload = newObj ?? oldObj ?? {};
  const objectType = payload.audit_object_type;
  if (objectType === 'workflow_template') return 'workflow_template';
  const kind = payload.kind;
  if (typeof kind === 'string' && ['role', 'scope', 'status', 'invite', 'password_reset_requested'].includes(kind)) return 'user';
  if ('name' in payload && 'is_active' in payload && !('kind' in payload)) return 'workflow_template';
  return 'unknown';
}

/** Главный суммайзер: событие → человеческое предложение. Никогда не бросает исключений. */
export function summarizeAuditEvent(event: AuditEvent): AuditSummary {
  try {
    return summarize(event);
  } catch {
    return {
      title: 'Изменение данных', section: getAuditEntityLabel(event.entity.type), objectName: event.entity.label || null,
      changes: [], note: null, actorName: auditActorName(event), actorRole: event.role ?? null,
    };
  }
}

function summarize(event: AuditEvent): AuditSummary {
  const attachmentPayload = asObject(event.newValues) ?? asObject(event.oldValues);
  if (attachmentPayload?.audit_object_type === 'workflow_attachment' || event.entity.type.toLowerCase() === 'workflow_attachment') {
    const filename = payloadName(attachmentPayload, 'original_filename') ?? 'Файл (название недоступно)';
    const title = event.action.toUpperCase() === 'DELETE' ? `Удалил файл ${quote(filename)}` : event.action.toUpperCase() === 'CREATE' ? `Загрузил файл ${quote(filename)}` : `Изменил файл ${quote(filename)}`;
    return { title, section: 'Файлы', objectName: filename, changes: changeRows(asObject(event.oldValues), asObject(event.newValues), new Set(['original_filename'])), note: null, actorName: auditActorName(event), actorRole: event.role ?? null };
  }
  // Серверный presentation — первичен (уже с резолвом имён).
  const presentationRaw = event.presentation;
  if (presentationRaw && typeof presentationRaw === 'object' && !Array.isArray(presentationRaw)) {
    const presentation = presentationRaw as {
      title?: unknown; section?: unknown; object_name?: unknown;
      changes?: Array<{ field?: unknown; label?: unknown; old?: unknown; new?: unknown; next?: unknown }>;
      note?: unknown; actor_name?: unknown; actor_role?: unknown;
    };
    if (typeof presentation.title === 'string') {
      const changes = Array.isArray(presentation.changes)
        ? presentation.changes.map((row) => ({
          field: String(row.field ?? ''),
          label: String(row.label ?? row.field ?? ''),
          old: String(row.old ?? '—').trim() || '—',
          next: String((row.next === '' ? row.new : row.next) ?? row.new ?? '—').trim() || '—',
        }))
        : [];
      return {
        title: presentation.title,
        section: typeof presentation.section === 'string' && presentation.section ? presentation.section : 'Система',
        objectName: typeof presentation.object_name === 'string' ? presentation.object_name : null,
        changes,
        note: typeof presentation.note === 'string' ? presentation.note : null,
        actorName: typeof presentation.actor_name === 'string' && presentation.actor_name && presentation.actor_name !== 'Системное действие' ? presentation.actor_name : auditActorName(event),
        actorRole: typeof presentation.actor_role === 'string' ? presentation.actor_role : (event.role ?? null),
      };
    }
  }

  const action = event.action.trim().toUpperCase();
  const entity = event.entity.type.trim().toLowerCase();
  const oldObj = asObject(event.oldValues);
  const newObj = asObject(event.newValues);
  const uni = event.university.name !== '—' ? event.university.name : payloadName(newObj, 'university_name') ?? payloadName(oldObj, 'university_name');
  const base = { actorName: auditActorName(event), actorRole: event.role ?? null };

  if (action === 'WORKFLOW_TRANSITION') {
    const fromStage = payloadName(oldObj, 'stage_name') ?? '—';
    const toStage = payloadName(newObj, 'stage_name') ?? '—';
    const comment = payloadName(newObj, 'comment');
    const changes: AuditChangeRow[] = [{ field: 'stage_name', label: 'Этап', old: fromStage, next: toStage }];
    if (comment) changes.push({ field: 'comment', label: 'Комментарий', old: '—', next: comment });
    return { ...base, title: fromStage === '—' || toStage === '—' ? `Изменил этап Workflow${uni ? ` ${quote(uni)}` : ''}` : `Перевёл${uni ? ` ${quote(uni)}` : ''} с этапа ${quote(fromStage)} на этап ${quote(toStage)}`, section: 'Workflow', objectName: uni ?? null, changes, note: null };
  }

  if (action === 'ASSIGN_RESPONSIBLE') {
    const oldName = resolveRef(oldObj?.responsible_id, oldObj?.responsible_name, '');
    const newName = resolveRef(newObj?.responsible_id, newObj?.responsible_name, '');
    const reason = payloadName(newObj, 'reason');
    const where = uni ? ` за ${quote(uni)}` : '';
    let title = `Изменил ответственного${where}`;
    if (newName && !oldName) title = `Назначил ${quote(newName)} ответственным${where}`;
    else if (oldName && !newName) title = `Снял ${quote(oldName)} с ответственных${where}`;
    else if (oldName && newName && oldName !== newName) title = `Сменил ответственного${where}: ${quote(oldName)} → ${quote(newName)}`;
    else if (newName) title = `Назначил ${quote(newName)} ответственным${where}`;
    const changes: AuditChangeRow[] = [];
    if (oldName || newName) changes.push({ field: 'responsible_id', label: 'Ответственный', old: oldName || '—', next: newName || '—' });
    if (reason) changes.push({ field: 'reason', label: 'Причина', old: '—', next: reason });
    return { ...base, title, section: 'Ответственные', objectName: newName || oldName || null, changes, note: null };
  }

  if (entity === 'config') {
    const subtype = classifyConfig(oldObj, newObj);
    if (subtype === 'workflow_template') {
      const name = payloadName(newObj, 'name') ?? payloadName(oldObj, 'name') ?? 'Шаблон Workflow (название недоступно)';
      const oldActive = oldObj?.is_active;
      const newActive = newObj?.is_active;
      if (action !== 'CREATE' && oldActive === true && newActive === false) {
        return { ...base, title: `Отключил шаблон Workflow ${quote(name)}`, section: 'Workflow', objectName: name, changes: [{ field: 'is_active', label: 'Статус', old: 'Включён', next: 'Выключен' }], note: null };
      }
      if (action !== 'CREATE' && oldActive === false && newActive === true) {
        return { ...base, title: `Включил шаблон Workflow ${quote(name)}`, section: 'Workflow', objectName: name, changes: [{ field: 'is_active', label: 'Статус', old: 'Выключен', next: 'Включён' }], note: null };
      }
      if (action === 'CREATE' || !oldObj) return { ...base, title: `Создал шаблон Workflow ${quote(name)}`, section: 'Workflow', objectName: name, changes: [], note: null };
      return { ...base, title: `Изменил шаблон Workflow ${quote(name)}`, section: 'Workflow', objectName: name, changes: changeRows(oldObj, newObj), note: null };
    }
    if (subtype === 'user') {
      const target = payloadName(newObj, 'target_name') ?? payloadName(oldObj, 'target_name') ?? 'Пользователь (данные недоступны)';
      const kind = typeof newObj?.kind === 'string' ? newObj.kind : (typeof oldObj?.kind === 'string' ? oldObj.kind : '');
      if (kind === 'role') {
        const oldRole = getAuditRoleLabel(typeof oldObj?.value === 'string' ? oldObj.value : undefined);
        const newRole = getAuditRoleLabel(typeof newObj?.value === 'string' ? newObj.value : undefined);
        return { ...base, title: `Изменил роль пользователя ${quote(target)}`, section: 'Пользователи', objectName: target, changes: [{ field: 'role', label: 'Роль', old: oldRole, next: newRole }], note: null };
      }
      if (kind === 'status') {
        const after = typeof newObj?.value === 'string' ? newObj.value.toLowerCase() : '';
        const title = after === 'blocked' ? `Заблокировал пользователя ${quote(target)}` : `Восстановил доступ пользователя ${quote(target)}`;
        return { ...base, title, section: 'Пользователи', objectName: target, changes: changeRows(oldObj, newObj, new Set(['kind', 'target_name', 'audit_object_type'])), note: null };
      }
      if (kind === 'invite') return { ...base, title: `Пригласил пользователя ${quote(target)}`, section: 'Пользователи', objectName: target, changes: [], note: null };
      if (kind === 'password_reset_requested') return { ...base, title: `Отправил сброс пароля пользователю ${quote(target)}`, section: 'Пользователи', objectName: target, changes: [], note: null };
      if (kind === 'scope') return { ...base, title: `Изменил доступ пользователя ${quote(target)}`, section: 'Пользователи', objectName: target, changes: changeRows(oldObj, newObj, new Set(['kind', 'target_name', 'audit_object_type'])), note: null };
    }
  }

  if (entity === 'workflow_stage') {
    const name = payloadName(newObj, 'name') ?? payloadName(oldObj, 'name') ?? 'Этап Workflow (название недоступно)';
    const template = payloadName(newObj, 'template_name') ?? payloadName(oldObj, 'template_name');
    if (action === 'CREATE' || !oldObj) {
      return { ...base, title: `Добавил этап ${quote(name)}${template ? ` в Workflow ${quote(template)}` : ''}`, section: 'Workflow', objectName: name, changes: [], note: null };
    }
    const restOld = { ...(oldObj ?? {}) };
    const restNew = { ...(newObj ?? {}) };
    delete restOld.is_active; delete restNew.is_active;
    if (oldObj?.is_active === true && newObj?.is_active === false && JSON.stringify(restOld) === JSON.stringify(restNew)) {
      return { ...base, title: `Отключил этап ${quote(name)}`, section: 'Workflow', objectName: name, changes: [{ field: 'is_active', label: 'Статус', old: 'Включён', next: 'Выключен' }], note: null };
    }
    if (oldObj?.is_active === false && newObj?.is_active === true && JSON.stringify(restOld) === JSON.stringify(restNew)) {
      return { ...base, title: `Включил этап ${quote(name)}`, section: 'Workflow', objectName: name, changes: [{ field: 'is_active', label: 'Статус', old: 'Выключен', next: 'Включён' }], note: null };
    }
    return { ...base, title: `Изменил этап ${quote(name)}`, section: 'Workflow', objectName: name, changes: changeRows(oldObj, newObj), note: null };
  }

  if (entity === 'workflow_instance' && action === 'CREATE') {
    const template = payloadName(newObj, 'template_name') ?? 'Workflow (название недоступно)';
    return { ...base, title: `Запустил Workflow ${quote(template)}${uni ? ` для ${quote(uni)}` : ''}`, section: 'Workflow', objectName: template, changes: [], note: null };
  }

  if (entity === 'workflow_comment') {
    const content = payloadName(newObj, 'content') ?? payloadName(oldObj, 'content');
    const title = action === 'CREATE' ? 'Добавил комментарий' : action === 'DELETE' ? 'Удалил комментарий' : 'Изменил комментарий';
    const changes: AuditChangeRow[] = content ? [{ field: 'content', label: 'Комментарий', old: action === 'CREATE' ? '—' : content, next: action === 'DELETE' ? '—' : content }] : [];
    return { ...base, title, section: 'Workflow', objectName: null, changes, note: null };
  }

  if (entity === 'document') {
    const filename = payloadName(newObj, 'original_filename') ?? payloadName(newObj, 'file_name') ?? payloadName(oldObj, 'original_filename') ?? payloadName(oldObj, 'file_name') ?? 'Файл (название недоступно)';
    const title = action === 'DELETE' ? `Удалил файл ${quote(filename)}` : action === 'CREATE' ? `Загрузил файл ${quote(filename)}` : `Изменил файл ${quote(filename)}`;
    return { ...base, title, section: 'Файлы', objectName: filename, changes: changeRows(oldObj, newObj, new Set(['original_filename', 'file_name'])) , note: null };
  }

  if (entity === 'meeting') {
    const subject = payloadName(newObj, 'subject') ?? payloadName(oldObj, 'subject');
    const baseTitle = action === 'CREATE' ? `Создал встречу${uni ? ` с ${quote(uni)}` : ''}` : action === 'DELETE' ? `Удалил встречу${uni ? ` с ${quote(uni)}` : ''}` : `Изменил встречу${uni ? ` с ${quote(uni)}` : ''}`;
    return { ...base, title: baseTitle, section: 'Встречи', objectName: subject, changes: changeRows(oldObj, newObj), note: null };
  }

  if ((entity === 'program' || entity === 'product') && action === 'CREATE' && (newObj?.[`${entity}_id`] !== undefined)) {
    const objName = resolveRef(newObj?.[`${entity}_id`], newObj?.[`${entity}_name`], FALLBACK_NAMES[entity] ?? 'Объект (данные недоступны)');
    const verb = entity === 'program' ? 'Добавил программу' : 'Добавил продукт';
    const statusOverride: Record<string, Record<string, string>> = entity === 'product' ? { status: PRODUCT_STATUS_LABELS } : {};
    return { ...base, title: `${verb} ${quote(objName)}${uni ? ` ВУЗу ${quote(uni)}` : ''}`, section: entity === 'program' ? 'Программы' : 'Продукты', objectName: objName, changes: changeRows(oldObj, newObj, new Set([`${entity}_id`, `${entity}_name`, 'university_name', 'audit_object_type']), statusOverride), note: null };
  }

  if (action === 'IMPORT' || action === 'REPORT_GENERATE') {
    if (entity === 'external_sync') return { ...base, title: 'Синхронизировал внешние данные', section: 'Импорт', objectName: null, changes: [], note: null };
    if (action === 'REPORT_GENERATE') return { ...base, title: 'Сформировал отчёт', section: 'Импорт', objectName: null, changes: [], note: null };
    return { ...base, title: uni ? `Запустил импорт данных для ${quote(uni)}` : 'Запустил импорт данных', section: 'Импорт', objectName: null, changes: [], note: null };
  }

  if (action === 'LOGIN') return { ...base, title: 'Вошёл в систему', section: 'Система', objectName: null, changes: [], note: null };
  if (action === 'LOGOUT') return { ...base, title: 'Вышел из системы', section: 'Система', objectName: null, changes: [], note: null };

  if (['CREATE', 'UPDATE', 'DELETE'].includes(action)) {
    const label = ENTITY_LABELS[entity];
    if (!label) return { ...base, title: 'Изменение данных', section: getAuditEntityLabel(entity), objectName: event.entity.label || null, changes: changeRows(oldObj, newObj), note: null };
    const objName = payloadName(newObj, 'name', 'full_name', 'subject', 'original_filename', 'file_name') ?? payloadName(oldObj, 'name', 'full_name', 'subject', 'original_filename', 'file_name') ?? (entity === 'university' ? uni : null);
    const sectionMap: Record<string, string> = {
      university: 'ВУЗы', direction: 'Направления', program: 'Программы', vendor: 'Производители',
      product: 'Продукты', responsible: 'Ответственные', meeting: 'Встречи',
    };
    if (!objName) {
      const fallback = action === 'DELETE'
        ? { university: 'Удалённый ВУЗ', program: 'Удалённая программа', product: 'Удалённый продукт', responsible: 'Удалённое ответственное лицо', meeting: 'Удалённая встреча' }[entity] ?? 'Удалённый объект'
        : FALLBACK_NAMES[entity] ?? 'Объект (данные недоступны)';
      const verb = action === 'CREATE' ? 'Создал' : action === 'DELETE' ? 'Удалил' : 'Изменил';
      return { ...base, title: `${verb}: ${fallback}`, section: sectionMap[entity] ?? 'Система', objectName: null, changes: changeRows(oldObj, newObj), note: null };
    }
    let title: string;
    if (entity === 'university') title = `${action === 'CREATE' ? 'Создал' : action === 'DELETE' ? 'Удалил' : 'Изменил'} ВУЗ ${quote(objName)}`;
    else if (entity === 'responsible') title = `${action === 'CREATE' ? 'Добавил ответственного' : action === 'DELETE' ? 'Удалил ответственного' : 'Изменил ответственного'} ${quote(objName)}`;
    else title = `${action === 'CREATE' ? 'Создал' : action === 'DELETE' ? 'Удалил' : 'Изменил'}: ${label} ${quote(objName)}`;
    const skip = action === 'UPDATE' ? new Set<string>() : new Set(['name', 'full_name', 'subject']);
    return { ...base, title, section: sectionMap[entity] ?? 'Система', objectName: objName, changes: changeRows(oldObj, newObj, skip), note: null };
  }

  return { ...base, title: 'Изменение данных', section: getAuditEntityLabel(entity), objectName: event.entity.label || null, changes: changeRows(oldObj, newObj), note: null };
}
