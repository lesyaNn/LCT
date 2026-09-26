import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import { isUuidLike } from './audit-human';
import type { SemanticIntent } from './status-semantics';
import { mockGetAuditEvents } from '@/shared/mocks/api-adapter';

export type AuditJsonValue = string | number | boolean | null | AuditJsonValue[] | { [key: string]: AuditJsonValue };

export interface AuditEvent {
  id: string;
  occurredAt: string;
  user: { id: string; name: string; email?: string };
  role?: string;
  action: string;
  entity: { id: string; type: string; label: string };
  university: { id: string; name: string };
  oldValues?: AuditJsonValue;
  newValues?: AuditJsonValue;
  requestId?: string;
  ip?: string;
  userAgent?: string;
  /** Server-side human presentation (new API). Null when the backend predates it. */
  presentation?: unknown | null;
  /** Resolved display names (new API). Fall back to ids when absent. */
  universityName?: string;
  entityName?: string;
}

export interface AuditFilters {
  dateFrom: string;
  dateTo: string;
  userIds: string[];
  universityIds: string[];
  actions: string[];
  entityTypes: string[];
  sections: string[];
  search: string;
}

export interface AuditListQuery {
  filters: AuditFilters;
  page: number;
  pageSize: number;
}

export interface AuditFilterOptions {
  users: Array<{ id: string; name: string }>;
  universities: Array<{ id: string; name: string }>;
  actions: string[];
  entityTypes: string[];
}

export interface AuditApiCapabilities {
  dateRange: boolean;
  users: boolean;
  universities: boolean;
  actions: boolean;
  entityTypes: boolean;
  pagination: boolean;
}

export interface AuditListResult {
  items: AuditEvent[];
  total: number;
  page: number;
  pageSize: number;
  filterOptions: AuditFilterOptions;
  capabilities: AuditApiCapabilities;
}

export const EMPTY_AUDIT_FILTERS: AuditFilters = {
  dateFrom: '',
  dateTo: '',
  userIds: [],
  universityIds: [],
  actions: [],
  entityTypes: [],
  sections: [],
  search: '',
};

export const AUDIT_PAGE_SIZES = [20, 50, 100] as const;

export const auditQueryKey = queryKeys.audit.list;

export const auditActionMeta: Record<string, { label: string; intent: SemanticIntent }> = {
  CREATE: { label: 'Создание', intent: 'success' },
  UPDATE: { label: 'Изменение', intent: 'brand' },
  DELETE: { label: 'Удаление', intent: 'danger' },
  WORKFLOW_TRANSITION: { label: 'Переход Workflow', intent: 'brand' },
  WORKFLOW_CREATE: { label: 'Создание Workflow', intent: 'success' },
  WORKFLOW_UPDATE: { label: 'Изменение Workflow', intent: 'brand' },
  WORKFLOW_DELETE: { label: 'Удаление Workflow', intent: 'danger' },
  LOGIN: { label: 'Вход', intent: 'neutral' },
  LOGOUT: { label: 'Выход', intent: 'neutral' },
};

export const auditEntityLabels: Record<string, string> = {
  workflow_instance: 'Workflow',
  workflow_stage: 'Этап Workflow',
  university: 'ВУЗ',
  teacher: 'Преподаватель',
  document: 'Документ',
  meeting: 'Встреча',
  note: 'Заметка',
  user: 'Пользователь',
};

export const auditRoleLabels: Record<string, string> = {
  admin: 'Администратор',
  manager: 'Руководитель',
  user: 'Пользователь',
};

/** The server provides scoped filtering and paginated audit events. */
export const CURRENT_AUDIT_API_CAPABILITIES: AuditApiCapabilities = {
  dateRange: true,
  users: true,
  universities: true,
  actions: true,
  entityTypes: true,
  pagination: true,
};

export function getAuditActionMeta(action: string): { label: string; intent: SemanticIntent } {
  const key = normalizeTechnicalValue(action);
  return auditActionMeta[key] ?? { label: humanizeTechnicalValue(action), intent: 'neutral' };
}

export function getAuditEntityLabel(entityType: string): string {
  const key = normalizeTechnicalValue(entityType).toLowerCase();
  return auditEntityLabels[key] ?? humanizeTechnicalValue(entityType);
}

export function getAuditRoleLabel(role?: string): string {
  if (!role) return '—';
  return auditRoleLabels[normalizeTechnicalValue(role).toLowerCase()] ?? humanizeTechnicalValue(role);
}

export function formatAuditValue(value: AuditJsonValue | undefined, maxLength = 92): string {
  if (value === undefined || value === null) return '—';
  if (isAuditJsonObject(value)) {
    const fields = Object.keys(value);
    const text = fields.length ? `Поля: ${fields.join(', ')}` : 'Изменена запись';
    return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
  }
  if (Array.isArray(value)) return `Изменён список (${value.length})`;
  return 'Значение изменено';
}

export function isAuditJsonObject(value: AuditJsonValue | undefined): value is { [key: string]: AuditJsonValue } {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function normalizeTechnicalValue(value: string): string {
  return value.trim().replace(/[\s-]+/g, '_').toUpperCase();
}

function humanizeTechnicalValue(value: string): string {
  const normalized = value.trim().replace(/[\s_]+/g, ' ').toLocaleLowerCase('ru-RU');
  return normalized ? normalized.charAt(0).toLocaleUpperCase('ru-RU') + normalized.slice(1) : '—';
}

type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function toJsonValue(value: unknown): AuditJsonValue | undefined {
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value;
  if (Array.isArray(value)) return value.map(toJsonValue).filter((item): item is AuditJsonValue => item !== undefined);
  if (isRecord(value)) {
    return Object.fromEntries(Object.entries(value).flatMap(([key, item]) => {
      const normalized = toJsonValue(item);
      return normalized === undefined ? [] : [[key, normalized]];
    }));
  }
  return undefined;
}

function parseJsonValue(value: unknown): AuditJsonValue | undefined {
  if (typeof value !== 'string') return toJsonValue(value);
  try { return toJsonValue(JSON.parse(value)); } catch { return value; }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : value === null || value === undefined ? undefined : String(value);
}

function adaptAuditEvent(raw: unknown, index: number): AuditEvent {
  const item = isRecord(raw) ? raw : {};
  const userId = stringValue(item.user_id ?? item.userId) ?? 'unknown';
  const entityType = stringValue(item.entity_type ?? item.entityType) ?? 'unknown';
  const entityId = stringValue(item.entity_id ?? item.entityId) ?? 'unknown';
  const universityId = stringValue(item.university_id ?? item.universityId);
  const action = stringValue(item.action) ?? 'UNKNOWN';
  // Defence-in-depth: raw UUIDs must never become display names. The API
  // resolves names server-side; when it cannot, the UI shows the section
  // or an explicit fallback — never the id.
  const universityNameRaw = stringValue(item.university_name ?? item.universityName);
  const universityName = universityNameRaw && !isUuidLike(universityNameRaw) ? universityNameRaw : '—';
  const entityNameRaw = stringValue(item.entity_name ?? item.entityName);
  const entityName = entityNameRaw && !isUuidLike(entityNameRaw) ? entityNameRaw : undefined;
  const presentation = isRecord(item.presentation) || Array.isArray(item.presentation) ? (item.presentation as unknown) : (item.presentation ?? null);
  return {
    id: stringValue(item.id) ?? `audit-${index}`,
    occurredAt: stringValue(item.timestamp ?? item.created_at ?? item.occurredAt ?? item.createdAt) ?? '',
    user: {
      id: userId,
      name: stringValue(item.user_name ?? item.userName) ?? userId,
      email: stringValue(item.user_email ?? item.userEmail),
    },
    role: stringValue(item.role ?? item.user_role ?? item.userRole),
    action,
    entity: { id: entityId, type: entityType, label: entityName ?? getAuditEntityLabel(entityType) },
    university: { id: universityId ?? '', name: universityName },
    oldValues: parseJsonValue(item.old_value ?? item.before_data ?? item.beforeData ?? item.old_values ?? item.oldValues),
    newValues: parseJsonValue(item.new_value ?? item.after_data ?? item.afterData ?? item.new_values ?? item.newValues),
    requestId: stringValue(item.request_id ?? item.requestId),
    ip: stringValue(item.ip_address ?? item.ip),
    userAgent: stringValue(item.user_agent ?? item.userAgent),
    presentation: presentation ?? null,
    universityName,
    entityName,
  };
}

function queryPath(query: AuditListQuery): string {
  const params = new URLSearchParams();
  if (query.filters.dateFrom) params.set('date_from', query.filters.dateFrom);
  if (query.filters.dateTo) params.set('date_to', query.filters.dateTo);
  if (query.filters.search.trim()) params.set('search', query.filters.search.trim());
  for (const [key, values] of [
    ['user_id', query.filters.userIds], ['university_id', query.filters.universityIds],
    ['action', query.filters.actions], ['entity_type', query.filters.entityTypes],
  ] as const) for (const value of values) params.append(key, value);
  params.set('page', String(query.page));
  params.set('page_size', String(query.pageSize));
  const queryString = params.toString();
  return `/api/v1/audit/events?${queryString}`;
}

async function getRealAuditEvents(query: AuditListQuery): Promise<AuditListResult> {
  const result = await apiFetch<unknown>(queryPath(query));
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить журнал аудита.', result.error);

  const payload = result.data;
  const rows = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.items) ? payload.items : [];
  const items = rows.map(adaptAuditEvent);
  const page = isRecord(payload) && typeof payload.page === 'number' ? payload.page : query.page;
  const pageSize = isRecord(payload) && typeof payload.page_size === 'number' ? payload.page_size : query.pageSize;
  const total = isRecord(payload) && typeof payload.total === 'number' ? payload.total : items.length;

  return {
    items,
    total,
    page,
    pageSize,
    filterOptions: { users: [], universities: [], actions: [], entityTypes: [] },
    capabilities: CURRENT_AUDIT_API_CAPABILITIES,
  };
}

export async function getAuditFilterOptions(): Promise<AuditFilterOptions> {
  const result = await apiFetch<unknown>('/api/v1/audit/filter-options');
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить фильтры аудита.', result.error);
  const raw = isRecord(result.data) ? result.data : {};
  const options = (value: unknown): Array<{ id: string; name: string }> => Array.isArray(value) ? value.flatMap((item) => isRecord(item) && stringValue(item.id) ? [{ id: stringValue(item.id)!, name: stringValue(item.name) ?? stringValue(item.id)! }] : []) : [];
  return { users: options(raw.users), universities: options(raw.universities), actions: Array.isArray(raw.actions) ? raw.actions.filter((value): value is string => typeof value === 'string') : [], entityTypes: Array.isArray(raw.entity_types) ? raw.entity_types.filter((value): value is string => typeof value === 'string') : [] };
}

export async function getAuditEvents(query: AuditListQuery): Promise<AuditListResult> {
  return fromDataSource({ mock: () => mockGetAuditEvents(query), real: () => getRealAuditEvents(query) });
}
