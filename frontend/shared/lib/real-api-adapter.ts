import { apiFetch, apiUploadFormData } from './api-client';
import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from './query-keys';
import { ApiRequestError } from './api-errors';
import { getExpirationStatus } from './formatters';
import type { ImportExecuteResponse, ImportRunOptions } from './import-repository';
import type { CatalogInput, CatalogItem, CatalogListQuery, CatalogListResult, CatalogReferenceData, CatalogType, ResponsibleCatalogItem } from './catalogs-repository';
import type {
  AdminUser,
  AdminUserListQuery,
  AdminUserListResult,
  AdminUserUpdateInput,
  InviteAdminUserInput,
  ResponsibleAssignmentInput,
  ResponsibleCandidate,
} from './users-repository';
import type {
  PaginatedResult,
  ProgramStatus,
  UniversityDocumentRow,
  UniversityFilters,
  UniversityHistoryEvent,
  UniversityHistoryFilters,
  UniversityLicenseRow,
  UniversityListItem,
  UniversityListQuery,
  UniversityMeetingRow,
  UniversityPassport,
  UniversityProductRow,
  UniversityProgramRow,
  UniversityResponsible,
  UniversityResponsibleContact,
} from './universities-repository';
import type {
  CreateWorkflowFromExternalInput,
  CreateWorkflowFromExternalResult,
  ExternalApplication,
  ExternalDataSource,
  ExternalStudent,
  UniversityExternalData,
} from './external-integrations-repository';

type ApiPage<T> = { items: T[]; page: number; page_size: number; total: number };
type ApiUniversity = {
  id: string;
  name: string;
  city: string | null;
  created_at: string;
  updated_at: string;
  health_score: number | null;
  health_status: 'green' | 'yellow' | 'red' | null;
};
type ApiProgram = { id: string; name: string; direction_name: string; status: ProgramStatus; launch_date: string | null; responsible_name: string | null };
type ApiLicense = { id: string; license_number: string; product_name: string; vendor_name: string; signed_at: string; expires_at: string; status: string; transfer_status: string; contract_number: string | null };
type ApiProduct = { id: string; name: string; version: string; vendor_name: string; status: string; license: ApiLicense | null };
type ApiDocument = { id: string; document_type: string; title: string; file_name: string; file_size: number; signed_at: string | null; expires_at: string | null; status: string; uploaded_by: string; created_at: string };
type ApiMeeting = { id: string; meeting_type: string; subject: string; participants: string[]; outcome: string | null; next_action: string | null; next_action_due: string | null; meeting_at: string; created_by: string };
type ApiMeetingRead = Omit<ApiMeeting, 'participants' | 'created_by'> & { participants: unknown[]; created_by_keycloak_sub: string };
type ApiResponsible = { id: string; full_name: string; email: string; phone: string | null; role: string; is_primary?: boolean };
type ApiTimeline = { id: string; type: string; title: string; description: string | null; author: string; created_at: string };
type ApiWorkflowSummary = { instance_id: string | null; template_name: string | null; current_stage: string | { code: string; name: string } | null; progress_percent: number; overdue_stages: number; next_due_date: string | null };
type ApiPassport = {
  university: { id: string; name: string; city: string | null };
  programs: ApiProgram[];
  products: ApiProduct[];
  licenses: ApiLicense[];
  documents: ApiDocument[];
  meetings: ApiMeeting[];
  responsibles: ApiResponsible[];
  workflow_summary: ApiWorkflowSummary;
  last_interactions: ApiTimeline[];
};

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>, message: string): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, message, result.error);
}

async function passport(id: string, include = '', signal?: AbortSignal): Promise<ApiPassport> {
  const suffix = include ? `?include=${encodeURIComponent(include)}` : '';
  return unwrap(await apiFetch<ApiPassport>(`/api/v1/universities/${encodeURIComponent(id)}/passport${suffix}`, { signal }), 'Не удалось загрузить паспорт ВУЗа.');
}

/** The aggregate is the sole backend source for passport-only blocks. */
async function passportBundle(id: string, queryClient?: QueryClient): Promise<ApiPassport> {
  if (!queryClient) return passport(id);
  return queryClient.ensureQueryData({
    queryKey: queryKeys.universities.passportBundle(id),
    queryFn: ({ signal }) => passport(id, '', signal),
    staleTime: 30_000,
  });
}

function responsible(value: string | null): UniversityResponsible | null {
  return value ? { id: `responsible:${value}`, name: value } : null;
}

function mapProgram(item: ApiProgram): UniversityProgramRow {
  return {
    id: item.id,
    direction: item.direction_name,
    name: item.name,
    status: item.status,
    launchDate: item.launch_date ?? '',
    responsible: responsible(item.responsible_name),
    teachersCount: 0,
    studentsCount: 0,
  };
}

function appendRepeated(params: URLSearchParams, key: string, values: readonly string[]): void {
  values.forEach((value) => params.append(key, value));
}

/** Single UniversityListQuery -> FastAPI query-contract serializer. */
export function serializeUniversityListQuery(params: UniversityListQuery): URLSearchParams {
  const search = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) });
  const filters: UniversityFilters = params.filters;
  if (filters.search.trim()) search.set('search', filters.search.trim());
  if (filters.city) search.set('city', filters.city);
  if (filters.externalSource) search.set('external_source', filters.externalSource);
  appendRepeated(search, 'university_ids', filters.universityIds);
  appendRepeated(search, 'program_ids', filters.programIds);
  appendRepeated(search, 'product_ids', filters.productIds);
  appendRepeated(search, 'responsible_ids', filters.responsibleIds);
  if (filters.dateFrom) search.set('date_from', filters.dateFrom);
  if (filters.dateTo) search.set('date_to', filters.dateTo);
  const supportedSort = 'name';
  search.set('sort_by', supportedSort);
  search.set('sort_order', params.order);
  return search;
}

export async function realGetUniversities(params: UniversityListQuery, signal?: AbortSignal): Promise<PaginatedResult<UniversityListItem>> {
  const search = serializeUniversityListQuery(params);
  const page = unwrap(
    await apiFetch<ApiPage<ApiUniversity>>(`/api/v1/universities?${search}`, { signal }),
    'Не удалось загрузить список ВУЗов.',
  );
  return {
    items: page.items.map((item) => ({
      id: item.id,
      name: item.name,
      city: item.city ?? '—',
      responsible: null,
      programsCount: 0,
      programStatusCounts: {},
      currentStage: { id: 'unavailable', name: '—', tone: 'neutral' },
      healthScore: item.health_score ?? 0,
      lastInteractionAt: item.updated_at || item.created_at,
      attention: item.health_status === 'red',
      availability: {
        responsible: false,
        programs: false,
        stage: false,
        healthScore: item.health_score !== null,
        lastInteraction: false,
      },
    })),
    page: page.page,
    pageSize: page.page_size,
    total: page.total,
  };
}

export async function realGetUniversityPassport(id: string, queryClient?: QueryClient): Promise<UniversityPassport> {
  const data = await passportBundle(id, queryClient);
  const totalSteps = 100;
  const workflowStatus: UniversityPassport['workflow']['status'] = data.workflow_summary.overdue_stages > 0 ? 'attention' : data.workflow_summary.progress_percent >= 100 ? 'completed' : 'in_progress';
  return {
    id: data.university.id,
    name: data.university.name,
    city: data.university.city ?? '—',
    healthScore: 0,
    metrics: {
      activePrograms: data.programs.filter((item) => item.status === 'active' || item.status === 'launched').length,
      teachers: { total: 0, ready: 0, attention: 0 },
      licenses: { active: data.licenses.filter((item) => item.status === 'active').length, expiring: data.licenses.filter((item) => item.status === 'expires_soon').length, overdue: data.licenses.filter((item) => item.status === 'expired').length },
      documents: { total: data.documents.length, signed: data.documents.filter((item) => item.status === 'signed').length, overdue: data.documents.filter((item) => item.status === 'expired').length, limited: data.documents.length >= 20 },
    },
    workflow: {
      currentStage: { id: data.workflow_summary.instance_id ?? 'not-started', name: typeof data.workflow_summary.current_stage === 'string' ? data.workflow_summary.current_stage : data.workflow_summary.current_stage?.name ?? 'Не запущен', tone: workflowStatus === 'attention' ? 'warning' : workflowStatus === 'completed' ? 'success' : 'brand' },
      status: workflowStatus,
      deadline: data.workflow_summary.next_due_date ?? '',
      overdue: data.workflow_summary.overdue_stages > 0,
      responsible: data.responsibles[0] ? { id: data.responsibles[0].id, name: data.responsibles[0].full_name, email: data.responsibles[0].email, role: data.responsibles[0].role } : null,
      completedSteps: Math.round(data.workflow_summary.progress_percent),
      totalSteps,
      nextStage: null,
    },
    timeline: data.last_interactions.map((item) => ({
      id: item.id,
      type: item.type === 'workflow_transition' ? 'workflow' : item.type === 'meeting' || item.type === 'document' || item.type === 'note' ? item.type : 'note',
      occurredAt: item.created_at,
      description: item.description ?? item.title,
    })),
  };
}

export async function realGetUniversityPrograms(id: string, page = 1, pageSize = 20, signal?: AbortSignal, status: ProgramStatus | 'all' = 'all'): Promise<PaginatedResult<UniversityProgramRow>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status !== 'all') params.set('status', status);
  const data = unwrap(await apiFetch<ApiPage<ApiProgram>>(`/api/v1/universities/${encodeURIComponent(id)}/passport/programs?${params}`, { signal }), 'Не удалось загрузить программы ВУЗа.');
  return { items: data.items.map(mapProgram), page: data.page, pageSize: data.page_size, total: data.total };
}




type ExternalDataDto = {
  university_id: string;
  source: ExternalDataSource;
  mode: 'real' | 'mock' | 'import' | 'unconfigured';
  synced_at: string | null;
  students: Array<{ id: string; name: string; program_id: string; flow: string | null; progress: number | null; source: 'lms'; synced_at: string | null }>;
  applications: Array<{ id: string; university_id: string; program_id: string; program_name: string; applications_count: number; demand_score: number | null; source: 'website'; synced_at: string | null; workflow_instance_id: string | null }>;
};

export async function realGetUniversityExternalData(
  universityId: string,
  source: ExternalDataSource,
  signal?: AbortSignal,
): Promise<UniversityExternalData> {
  const result = await apiFetch<ExternalDataDto>(`/api/v1/universities/${encodeURIComponent(universityId)}/external-data?source=${source}`, { signal });
  const data = unwrap(result, 'Не удалось загрузить данные внешнего источника.');
  return {
    universityId: data.university_id,
    source: data.source,
    mode: data.mode,
    syncedAt: data.synced_at,
    students: data.students.map((row): ExternalStudent => ({ id: row.id, name: row.name, programName: null, flow: row.flow, progress: row.progress, source: 'manual', syncedAt: row.synced_at })),
    applications: data.applications.map((row): ExternalApplication => ({ id: row.id, universityId: row.university_id, programId: row.program_id, programName: row.program_name, applicationsCount: row.applications_count, demandScore: row.demand_score, source: row.source, syncedAt: row.synced_at, workflowInstanceId: row.workflow_instance_id })),
  };
}

export async function realCreateWorkflowFromExternal(
  input: CreateWorkflowFromExternalInput,
): Promise<CreateWorkflowFromExternalResult> {
  const result = await apiFetch<{ instance_id: string; university_id: string; program_id: string; external_id: string; existing: boolean }>('/api/v1/workflow/instances/from-external', {
    method: 'POST',
    body: { university_id: input.universityId, source: input.source, external_id: input.externalId },
  });
  const payload = unwrap(result, 'Не удалось создать Workflow из внешней заявки.');
  return {
    instanceId: payload.instance_id,
    universityId: payload.university_id,
    programId: payload.program_id,
    externalId: payload.external_id,
    existing: payload.existing,
  };
}

export async function realGetExternalDashboardMetrics(): Promise<{ mode: 'real' | 'mock' | 'import'; websiteApplications7d: number | null; lmsStudents: number | null; websiteSyncedAt: string | null; lmsSyncedAt: string | null }> {
  const data = unwrap(await apiFetch<{ mode: 'real' | 'mock' | 'import'; website_applications_7d: number | null; lms_students: number | null; website_synced_at: string | null; lms_synced_at: string | null }>('/api/v1/integrations/metrics'), 'Не удалось загрузить показатели интеграций.');
  return { mode: data.mode, websiteApplications7d: data.website_applications_7d, lmsStudents: data.lms_students, websiteSyncedAt: data.website_synced_at, lmsSyncedAt: data.lms_synced_at };
}

export async function realGetUniversityProducts(id: string, queryClient?: QueryClient): Promise<UniversityProductRow[]> {
  const data = (await passportBundle(id, queryClient)).products;
  return data.map((item) => ({
    id: item.id,
    name: item.name,
    version: item.version,
    vendor: item.vendor_name,
    status: item.status === 'expired' ? 'expired' : item.status === 'active' ? 'active' : 'planned',
    licenseNumber: item.license?.license_number ?? '—',
    expiresAt: item.license?.expires_at ?? '',
  }));
}

export async function realGetUniversityLicenses(id: string, queryClient?: QueryClient): Promise<UniversityLicenseRow[]> {
  const data = (await passportBundle(id, queryClient)).licenses;
  return data.map((item) => ({
    id: item.id,
    product: item.product_name,
    vendor: item.vendor_name,
    licenseNumber: item.license_number,
    signedAt: item.signed_at,
    expiresAt: item.expires_at,
    status: item.status === 'expired' ? 'expired' : item.status === 'expires_soon' ? 'expires_soon' : 'active',
    transfer: item.transfer_status,
    contract: item.contract_number ?? '—',
  }));
}

export async function realGetUniversityDocuments(id: string, queryClient?: QueryClient): Promise<UniversityDocumentRow[]> {
  const data = (await passportBundle(id, queryClient)).documents;
  return data.map((item) => ({
    id: item.id,
    type: item.document_type,
    name: item.title,
    fileName: item.file_name,
    fileSize: item.file_size ? `${Math.max(1, Math.round(item.file_size / 1024))} КБ` : '0 КБ',
    signedAt: item.signed_at,
    expiresAt: item.expires_at,
    status: item.status === 'signed' ? 'signed' : item.status === 'archived' ? 'archived' : 'pending',
    uploadedBy: item.uploaded_by,
    uploadedAt: item.created_at,
  }));
}

export async function realGetUniversityMeetings(id: string, page = 1, pageSize = 20, signal?: AbortSignal): Promise<PaginatedResult<UniversityMeetingRow>> {
  const data = unwrap(await apiFetch<ApiPage<ApiMeetingRead>>(`/api/v1/universities/${encodeURIComponent(id)}/meetings?page=${page}&page_size=${pageSize}`, { signal }), 'Не удалось загрузить встречи ВУЗа.');
  return { items: data.items.map((item) => ({
    id: item.id,
    occurredAt: item.meeting_at,
    type: item.meeting_type === 'offline' || item.meeting_type === 'phone' || item.meeting_type === 'email' ? item.meeting_type : 'online',
    subject: item.subject,
    participants: item.participants.map((participant, index) => {
      const person = isRecord(participant) ? participant : {};
      const name = typeof participant === 'string' ? participant : stringValue(person.full_name ?? person.name, '—');
      return { id: `${item.id}:${index}`, name, initials: name.split(/\s+/).slice(0, 2).map((part) => part[0]).join('') };
    }),
    outcome: item.outcome ?? '—',
    nextAction: item.next_action ?? '—',
    dueDate: item.next_action_due,
    author: item.created_by_keycloak_sub,
  })), page: data.page, pageSize: data.page_size, total: data.total };
}

export async function realGetUniversityResponsibles(id: string, queryClient?: QueryClient): Promise<UniversityResponsibleContact[]> {
  const data = (await passportBundle(id, queryClient)).responsibles;
  return data.map((item) => ({
    id: item.id,
    name: item.full_name,
    role: item.role,
    email: item.email,
    phone: item.phone ?? '—',
    isPrimary: item.is_primary === true,
    initials: item.full_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join(''),
  }));
}

export async function realGetUniversityHistory(id: string, filters: UniversityHistoryFilters): Promise<UniversityHistoryEvent[]> {
  const data = await passport(id, 'audit');
  const defaultUser: UniversityResponsible = data.responsibles[0]
    ? { id: data.responsibles[0].id, name: data.responsibles[0].full_name, email: data.responsibles[0].email, role: data.responsibles[0].role }
    : { id: 'system', name: 'Система' };
  return data.last_interactions.map((item): UniversityHistoryEvent => ({
    id: item.id,
    occurredAt: item.created_at,
    type: item.type === 'workflow_transition' ? 'workflow' : item.type === 'meeting' || item.type === 'document' || item.type === 'note' ? item.type : 'audit',
    user: { ...defaultUser, name: item.author || defaultUser.name },
    action: item.title,
    details: item.description ?? item.title,
    entity: { id: item.id, label: item.title },
  })).filter((event) => {
    const date = event.occurredAt.slice(0, 10);
    if (filters.type !== 'all' && event.type !== filters.type) return false;
    if (filters.dateFrom && date < filters.dateFrom) return false;
    if (filters.dateTo && date > filters.dateTo) return false;
    if (filters.userId && event.user.id !== filters.userId) return false;
    if (filters.entityId && event.entity.id !== filters.entityId) return false;
    return true;
  });
}

// --------------------------------------------------------------------- import

export async function realUploadImportFile(file: File, signal?: AbortSignal, onProgress?: (value: number) => void): Promise<unknown> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  const result = await apiUploadFormData<unknown>('/api/v1/import/upload', formData, { signal, onProgress });
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить файл.', result.error);
}

export async function realPreviewImportSheet(fileId: string, sheet: string, signal?: AbortSignal): Promise<unknown> {
  return unwrap(await apiFetch<unknown>('/api/v1/import/sheets/preview', {
    method: 'POST',
    body: { file_id: fileId, sheet },
    signal,
  }), 'Не удалось построить предпросмотр листа.');
}

export async function realExecuteSheetImport(fileId: string, sheet: string, options: ImportRunOptions): Promise<ImportExecuteResponse> {
  return unwrap(await apiFetch<ImportExecuteResponse>('/api/v1/import/execute', {
    method: 'POST',
    body: { file_id: fileId, sheet, dry_run: options.dry_run, update_existing: options.update_existing, filename: options.filename ?? null },
  }), 'Не удалось запустить импорт.');
}

export async function realExecuteSheetsImport(fileId: string, sheets: string[], options: ImportRunOptions): Promise<ImportExecuteResponse> {
  return unwrap(await apiFetch<ImportExecuteResponse>('/api/v1/import/execute', {
    method: 'POST',
    body: { file_id: fileId, sheets, dry_run: options.dry_run, update_existing: options.update_existing, filename: options.filename ?? null },
  }), 'Не удалось запустить импорт.');
}

export async function realGetImportJob(jobId: string): Promise<unknown> {
  return unwrap(await apiFetch<unknown>(`/api/v1/import/jobs/${encodeURIComponent(jobId)}`), 'Не удалось обновить статус импорта.');
}

export async function realListImportJobs(): Promise<unknown[]> {
  const result = await apiFetch<unknown>('/api/v1/import/jobs');
  const data = unwrap(result, 'Не удалось загрузить журнал импортов.');
  if (Array.isArray(data)) return data;
  return data && typeof data === 'object' && 'items' in data && Array.isArray(data.items) ? data.items : [];
}

// --------------------------------------------------------------- users / RBAC

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function userRole(value: unknown): AdminUser['role'] {
  return value === 'admin' || value === 'manager' || value === 'user' ? value : 'user';
}

function mapRealAdminUser(value: unknown): AdminUser {
  const item = isRecord(value) ? value : {};
  const scope = isRecord(item.scope) ? item.scope : {};
  const rawScope = item.university_ids ?? scope.university_ids;
  const universityIds = Array.isArray(rawScope) ? rawScope.filter((id): id is string => typeof id === 'string') : [];
  const role = userRole(item.role ?? item.user_role ?? item.userRole);
  return {
    id: stringValue(item.id ?? item.user_id),
    username: stringValue(item.username ?? item.login ?? item.email),
    name: stringValue(item.full_name ?? item.name ?? item.username, 'Пользователь'),
    email: stringValue(item.email),
    role,
    status: item.is_active === false || item.status === 'blocked' ? 'blocked' : 'active',
    scope: role === 'admin' ? { kind: 'all' } : { kind: 'universities', universityIds },
    lastLoginAt: stringValue(item.last_login_at ?? item.last_login ?? item.lastLoginAt) || null,
  };
}

function mapUserListPayload(value: unknown, query: AdminUserListQuery): AdminUserListResult {
  const payload = isRecord(value) ? value : {};
  const rows = Array.isArray(value) ? value : Array.isArray(payload.items) ? payload.items : [];
  return {
    items: rows.map(mapRealAdminUser),
    page: typeof payload.page === 'number' ? payload.page : query.page,
    pageSize: typeof payload.page_size === 'number' ? payload.page_size : query.pageSize,
    total: typeof payload.total === 'number' ? payload.total : rows.length,
  };
}

export async function realListAdminUsers(query: AdminUserListQuery): Promise<AdminUserListResult> {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
  if (query.search) params.set('search', query.search);
  if (query.role !== 'all') params.set('role', query.role);
  const data = unwrap(await apiFetch<unknown>(`/api/v1/admin/users?${params}`), 'Не удалось загрузить список пользователей.');
  return mapUserListPayload(data, query);
}

export async function realGetAdminUser(id: string): Promise<AdminUser> {
  return mapRealAdminUser(unwrap(await apiFetch<unknown>(`/api/v1/admin/users/${encodeURIComponent(id)}`), 'Не удалось загрузить пользователя.'));
}

function userWriteBody(input: AdminUserUpdateInput) {
  return { role: input.role, scope: { kind: input.scope.kind, university_ids: input.scope.kind === 'all' ? [] : input.scope.universityIds } };
}

export async function realUpdateAdminUser(id: string, input: AdminUserUpdateInput): Promise<AdminUser> {
  return mapRealAdminUser(unwrap(await apiFetch<unknown>(`/api/v1/admin/users/${encodeURIComponent(id)}`, {
    method: 'PATCH', body: userWriteBody(input),
  }), 'Не удалось сохранить роль и скоуп.'));
}

export async function realBlockAdminUser(id: string, blocked: boolean): Promise<AdminUser> {
  return mapRealAdminUser(unwrap(await apiFetch<unknown>(`/api/v1/admin/users/${encodeURIComponent(id)}/block`, {
    method: 'POST', body: { blocked },
  }), 'Не удалось изменить статус пользователя.'));
}

export async function realInviteAdminUser(input: InviteAdminUserInput): Promise<{ user: AdminUser; status: 'email_sent' | 'invite_email_unavailable' }> {
  const data = unwrap(await apiFetch<unknown>('/api/v1/admin/users/invite', {
    method: 'POST', body: { ...userWriteBody(input), name: input.name, username: input.username, email: input.email },
  }), 'Не удалось создать учётную запись.');
  const payload = isRecord(data) ? data : {};
  return { user: mapRealAdminUser(payload.user), status: payload.status === 'email_sent' ? 'email_sent' : 'invite_email_unavailable' };
}

export async function realResetAdminUserPassword(id: string): Promise<{ status: 'requested' }> {
  const data = unwrap(await apiFetch<unknown>(`/api/v1/admin/users/${encodeURIComponent(id)}/password-reset`, {
    method: 'POST',
  }), 'Не удалось отправить запрос на сброс пароля.');
  if (!isRecord(data) || data.status !== 'requested') throw new ApiRequestError(502, data, 'Некорректный ответ сервера сброса пароля.');
  return { status: 'requested' };
}

export async function realListResponsibleCandidates(): Promise<ResponsibleCandidate[]> {
  const data = unwrap(await apiFetch<unknown>('/api/v1/responsibles?page=1&page_size=100'), 'Не удалось загрузить список ответственных.');
  const payload = isRecord(data) ? data : {};
  const rows = Array.isArray(data) ? data : Array.isArray(payload.items) ? payload.items : [];
  return rows.map((value): ResponsibleCandidate => {
    const item = isRecord(value) ? value : {};
    return {
      id: stringValue(item.id),
      name: stringValue(item.full_name ?? item.name, 'Пользователь'),
      email: stringValue(item.email),
      role: stringValue(item.role, 'Ответственный'),
    };
  }).filter((item) => item.id);
}

export async function realAssignUniversityResponsible(input: ResponsibleAssignmentInput): Promise<void> {
  unwrap(await apiFetch<unknown>(`/api/v1/universities/${encodeURIComponent(input.universityId)}/responsibles/primary`, {
    method: 'PATCH',
    body: { responsible_id: input.responsibleId, reason: input.reason },
  }), 'Не удалось назначить ответственного ВУЗа.');
}

// -------------------------------------------------------------- catalog CRUD

function catalogTimestamp(value: unknown): string {
  return stringValue(value) || new Date().toISOString();
}

function catalogItem(type: CatalogType, value: unknown): CatalogItem {
  const item = isRecord(value) ? value : {};
  const base = {
    id: stringValue(item.id),
    name: stringValue(item.name ?? item.full_name),
    isActive: item.is_active !== false,
    createdAt: catalogTimestamp(item.created_at),
    updatedAt: catalogTimestamp(item.updated_at),
  };
  if (type === 'universities') return { ...base, type, city: stringValue(item.city) };
  if (type === 'products') {
    const vendor = isRecord(item.vendor) ? item.vendor : {};
    const contacts = Array.isArray(item.contacts) ? item.contacts.flatMap((value) => {
      if (!isRecord(value)) return [];
      return [{ id: stringValue(value.id), fullName: stringValue(value.full_name), email: stringValue(value.email), phone: stringValue(value.phone), communicationMethod: stringValue(value.communication_method) }];
    }) : undefined;
    return { ...base, type, version: stringValue(item.version), vendorId: stringValue(item.vendor_id ?? vendor.id), vendorName: stringValue(item.vendor_name ?? vendor.name), contacts };
  }
  if (type === 'directions') return { ...base, type, code: stringValue(item.code) };
  const universities = Array.isArray(item.universities) ? item.universities : [];
  return {
    ...base,
    type,
    email: stringValue(item.email),
    phone: stringValue(item.phone),
    role: stringValue(item.role),
    universityIds: universities.flatMap((university) => isRecord(university) && stringValue(university.id) ? [stringValue(university.id)] : []),
  };
}

function catalogPayloadPage(value: unknown, query: CatalogListQuery): CatalogListResult {
  const payload = isRecord(value) ? value : {};
  const rows = Array.isArray(value) ? value : Array.isArray(payload.items) ? payload.items : [];
  return {
    items: rows.map((item) => catalogItem(query.type, item)),
    page: typeof payload.page === 'number' ? payload.page : query.page,
    pageSize: typeof payload.page_size === 'number' ? payload.page_size : query.pageSize,
    total: typeof payload.total === 'number' ? payload.total : rows.length,
  };
}

export async function realListCatalogItems(query: CatalogListQuery, signal?: AbortSignal): Promise<CatalogListResult> {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
  if (query.search.trim()) params.set('search', query.search.trim());
  const data = unwrap(await apiFetch<unknown>(`/api/v1/${query.type}?${params}`, { signal }), 'Не удалось загрузить каталог.');
  return catalogPayloadPage(data, query);
}

export async function realGetCatalogItem(type: CatalogType, id: string, signal?: AbortSignal): Promise<CatalogItem> {
  const data = unwrap(await apiFetch<unknown>(`/api/v1/${type}/${encodeURIComponent(id)}`, { signal }), 'Не удалось загрузить запись каталога.');
  return catalogItem(type, data);
}

function referenceItems(
  value: unknown,
  names: readonly string[] = ['name'],
  descriptions: readonly string[] = [],
): Array<{ id: string; name: string; description?: string }> {
  const payload = isRecord(value) ? value : {};
  const rows = Array.isArray(value) ? value : Array.isArray(payload.items) ? payload.items : [];
  return rows.flatMap((value) => {
    const item = isRecord(value) ? value : {};
    const id = stringValue(item.id);
    const name = names.map((key) => stringValue(item[key])).find(Boolean) ?? '';
    const description = descriptions.map((key) => stringValue(item[key])).find(Boolean);
    return id && name ? [{ id, name, ...(description ? { description } : {}) }] : [];
  });
}

async function allReferencePages(
  path: string,
  message: string,
  signal?: AbortSignal,
): Promise<unknown[]> {
  const first = unwrap(
    await apiFetch<ApiPage<unknown>>(`/api/v1/${path}?page=1&page_size=100`, { signal }),
    message,
  );
  const pages = Math.ceil(first.total / first.page_size);
  if (pages <= 1) return first.items;
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, index) => index + 2).map(async (page) => unwrap(
      await apiFetch<ApiPage<unknown>>(`/api/v1/${path}?page=${page}&page_size=100`, { signal }),
      message,
    )),
  );
  return [first.items, ...rest.map((page) => page.items)].flat();
}

function universityReferenceQuery(page: number): UniversityListQuery {
  return {
    filters: {
      search: '', city: '', externalSource: '', universityIds: [], programIds: [], productIds: [],
      responsibleIds: [], healthStatuses: [], workflowStageId: '', dateFrom: '', dateTo: '',
    },
    sort: 'name',
    order: 'asc',
    page,
    pageSize: 100,
  };
}

async function allUniversityReferencePages(signal?: AbortSignal): Promise<UniversityListItem[]> {
  const first = await realGetUniversities(universityReferenceQuery(1), signal);
  const pages = Math.ceil(first.total / first.pageSize);
  if (pages <= 1) return first.items;
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, index) => index + 2)
      .map((page) => realGetUniversities(universityReferenceQuery(page), signal)),
  );
  return [first.items, ...rest.map((page) => page.items)].flat();
}

export async function realGetCatalogReferenceData(signal?: AbortSignal): Promise<CatalogReferenceData> {
  const [vendors, universities, products, directions, programs, responsibles] = await Promise.all([
    allReferencePages('vendors', 'Не удалось загрузить список вендоров.', signal),
    allUniversityReferencePages(signal),
    allReferencePages('products', 'Не удалось загрузить список продуктов.', signal),
    allReferencePages('directions', 'Не удалось загрузить список направлений.', signal),
    allReferencePages('programs', 'Не удалось загрузить список программ.', signal),
    allReferencePages('responsibles', 'Не удалось загрузить список ответственных.', signal),
  ]);
  return {
    vendors: referenceItems(vendors),
    universities: referenceItems(universities, ['name'], ['city']),
    products: referenceItems(products, ['name'], ['vendor_name', 'version']),
    directions: referenceItems(directions, ['name'], ['code']),
    programs: referenceItems(programs, ['name'], ['direction_name']),
    responsibles: referenceItems(responsibles, ['full_name', 'name'], ['role', 'email']),
  };
}

function catalogWriteBody(input: CatalogInput): Record<string, unknown> {
  if (input.type === 'universities') return { name: input.name, city: input.city || null };
  if (input.type === 'products') return { name: input.name, vendor_id: input.vendorId, version: input.version };
  if (input.type === 'directions') return { name: input.name, code: input.code };
  return { full_name: input.name, email: input.email, phone: input.phone || null, role: input.role };
}

async function syncResponsibleUniversities(responsibleId: string, currentIds: string[], nextIds: string[]): Promise<void> {
  const current = new Set(currentIds);
  const next = new Set(nextIds);
  const additions = [...next].filter((id) => !current.has(id));
  const removals = [...current].filter((id) => !next.has(id));
  await Promise.all(additions.map(async (universityId) => {
    unwrap(await apiFetch<unknown>(`/api/v1/universities/${encodeURIComponent(universityId)}/responsibles/${encodeURIComponent(responsibleId)}`, { method: 'POST', body: { is_primary: false } }), 'Не удалось связать ответственного с ВУЗом.');
  }));
  await Promise.all(removals.map(async (universityId) => {
    unwrap(await apiFetch<unknown>(`/api/v1/universities/${encodeURIComponent(universityId)}/responsibles/${encodeURIComponent(responsibleId)}`, { method: 'DELETE' }), 'Не удалось убрать связь ответственного с ВУЗом.');
  }));
}

export async function realCreateCatalogItem(input: CatalogInput): Promise<CatalogItem> {
  const data = unwrap(await apiFetch<unknown>(`/api/v1/${input.type}`, { method: 'POST', body: catalogWriteBody(input) }), 'Не удалось добавить запись каталога.');
  const created = catalogItem(input.type, data);
  if (input.type === 'responsibles' && input.universityIds.length) {
    await syncResponsibleUniversities(created.id, [], input.universityIds);
    return { ...(created as ResponsibleCatalogItem), universityIds: [...input.universityIds] };
  }
  return created;
}

export async function realUpdateCatalogItem(id: string, input: CatalogInput): Promise<CatalogItem> {
  const current = input.type === 'responsibles' ? await realGetCatalogItem(input.type, id) as ResponsibleCatalogItem : null;
  const data = unwrap(await apiFetch<unknown>(`/api/v1/${input.type}/${encodeURIComponent(id)}`, { method: 'PATCH', body: catalogWriteBody(input) }), 'Не удалось сохранить запись каталога.');
  const updated = catalogItem(input.type, data);
  if (input.type === 'responsibles') {
    await syncResponsibleUniversities(id, current?.universityIds ?? [], input.universityIds);
    return { ...(updated as ResponsibleCatalogItem), universityIds: [...input.universityIds] };
  }
  return updated;
}

export function realSetCatalogItemActive(_type: CatalogType, _id: string, _active: boolean): never {
  void _type;
  void _id;
  void _active;
  throw new ApiRequestError(501, { code: 'CATALOG_SOFT_DELETE_UNAVAILABLE' }, 'Текущий backend не публикует soft activate/deactivate contract.');
}
