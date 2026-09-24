import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
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
}

export interface AuditFilters {
  dateFrom: string;
  dateTo: string;
  userIds: string[];
  universityIds: string[];
  actions: string[];
  entityTypes: string[];
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
  manager: 'Менеджер',
  curator: 'Куратор',
  user: 'Пользователь',
};

/** Current backend exposes only entity_type/entity_id and a plain array. */
export const CURRENT_AUDIT_API_CAPABILITIES: AuditApiCapabilities = {
  dateRange: false,
  users: false,
  universities: false,
  actions: false,
  entityTypes: true,
  pagination: false,
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
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (!text) return '—';
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
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
  return {
    id: stringValue(item.id) ?? `audit-${index}`,
    occurredAt: stringValue(item.created_at ?? item.occurredAt ?? item.createdAt) ?? '',
    user: {
      id: userId,
      name: stringValue(item.user_name ?? item.userName) ?? userId,
      email: stringValue(item.user_email ?? item.userEmail),
    },
    role: stringValue(item.role ?? item.user_role ?? item.userRole),
    action,
    entity: { id: entityId, type: entityType, label: `${getAuditEntityLabel(entityType)} · ${entityId}` },
    university: { id: universityId ?? '', name: stringValue(item.university_name ?? item.universityName) ?? universityId ?? '—' },
    oldValues: parseJsonValue(item.before_data ?? item.beforeData ?? item.old_values ?? item.oldValues),
    newValues: parseJsonValue(item.after_data ?? item.afterData ?? item.new_values ?? item.newValues),
    requestId: stringValue(item.request_id ?? item.requestId),
    ip: stringValue(item.ip_address ?? item.ip),
    userAgent: stringValue(item.user_agent ?? item.userAgent),
  };
}

function queryPath(query: AuditListQuery): string {
  const params = new URLSearchParams();
  // These are the only query parameters in the currently implemented backend contract.
  if (query.filters.entityTypes.length === 1) params.set('entity_type', query.filters.entityTypes[0]);
  const queryString = params.toString();
  return queryString ? `/api/v1/audit?${queryString}` : '/api/v1/audit';
}

async function getRealAuditEvents(query: AuditListQuery): Promise<AuditListResult> {
  const result = await apiFetch<unknown>(queryPath(query));
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить журнал аудита.', result.error);

  const payload = result.data;
  const rows = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.items) ? payload.items : [];
  const items = rows.map(adaptAuditEvent);
  // The discovered contract is a plain array capped at 200 rows. Do not infer
  // pagination from a future-shaped payload until P5-05-03 is actually wired.
  const page = 1;
  const pageSize = query.pageSize;
  const total = items.length;

  return {
    items,
    total,
    page,
    pageSize,
    filterOptions: { users: [], universities: [], actions: Object.keys(auditActionMeta), entityTypes: Object.keys(auditEntityLabels) },
    capabilities: CURRENT_AUDIT_API_CAPABILITIES,
  };
}

export async function getAuditEvents(query: AuditListQuery): Promise<AuditListResult> {
  return fromDataSource({ mock: () => mockGetAuditEvents(query), real: () => getRealAuditEvents(query) });
}
