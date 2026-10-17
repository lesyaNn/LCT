import { apiDownload, apiFetch } from './api-client';
import { ApiRequestError, ERROR_MESSAGES } from './api-errors';
import { fromDataSource, isMockDataSource } from './data-source';
import { periodPresetRange, type PeriodPreset } from './date-period';
import { queryKeys } from './query-keys';
import { type UniversityWorkflowStageStatus } from './universities-repository';
import { mockCreateReportJob, mockGetReportJob, mockListReportJobs } from '@/shared/mocks/api-adapter';

export type ReportFormat = 'xls' | 'xlsx' | 'pdf' | 'json';
export const REPORT_GROUP_IDS = ['university', 'direction', 'program', 'product', 'responsible', 'workflow_status'] as const;
export type ReportGroupBy = (typeof REPORT_GROUP_IDS)[number];

export const REPORT_GROUP_OPTIONS: Array<{ id: ReportGroupBy; name: string }> = [
  { id: 'university', name: 'ВУЗы' },
  { id: 'direction', name: 'ИТ-направления' },
  { id: 'program', name: 'ИТ-программы' },
  { id: 'product', name: 'ИТ-продукты' },
  { id: 'responsible', name: 'Ответственные' },
  { id: 'workflow_status', name: 'Статус работы' },
];

export type ReportPeriodPreset = PeriodPreset | null;
export type ReportJobStatus = 'queued' | 'building' | 'ready' | 'failed';

export interface ReportFormValues {
  dateFrom: string;
  dateTo: string;
  universityIds: string[];
  directionIds: string[];
  programIds: string[];
  productIds: string[];
  responsibleIds: string[];
  workflowStatuses: UniversityWorkflowStageStatus[];
  groupBy: ReportGroupBy | '';
  columnIds: string[];
  format: ReportFormat;
}

export interface ReportRequest {
  date_from: string;
  date_to: string;
  university_ids: string[];
  direction_ids: string[];
  program_ids: string[];
  product_ids: string[];
  responsible_ids: string[];
  workflow_statuses: UniversityWorkflowStageStatus[];
  group_by: ReportGroupBy | null;
  columns: string[];
  format: ReportFormat;
}

export interface ReportTemplate {
  id: string;
  name: string;
  ownerSub: string;
  isShared: boolean;
  format: ReportFormat;
  filters: {
    date_from: string;
    date_to: string;
    university_ids: string[];
    direction_ids: string[];
    program_ids: string[];
    product_ids: string[];
    responsible_ids: string[];
    workflow_statuses: UniversityWorkflowStageStatus[];
  };
  columns: string[];
  groupBy?: ReportGroupBy | null;
}

export interface ReportJob {
  id: string;
  name: string;
  format: ReportFormat;
  status: ReportJobStatus;
  progress: number | null;
  createdAt: string;
  expiresAt?: string;
  fileSize?: number;
  error?: string;
  errorCode?: string;
  downloadUrl?: string;
  /** The original form request is retained for create-based retry. */
  request?: ReportRequest;
}

export interface ReportColumnDefinition {
  id: string;
  label: string;
}

export interface ReportsApiCapabilities {
  createJob: boolean;
  jobStatus: boolean;
  jobList: boolean;
  retry: boolean;
  download: boolean;
  formats: Record<ReportFormat, boolean>;
  filters: boolean;
  columns: boolean;
  progress: boolean;
}

/** Capabilities of the real report-job API. */
const realReportsApiCapabilities: ReportsApiCapabilities = {
  createJob: true,
  jobStatus: true,
  jobList: true,
  // The current API has no dedicated retry route. The UI retries by creating
  // another job with the original request payload.
  retry: true,
  download: true,
  formats: { xls: true, xlsx: true, pdf: true, json: true },
  filters: true,
  columns: true,
  progress: true,
};

export const REPORTS_API_CAPABILITIES: ReportsApiCapabilities = isMockDataSource ? {
  createJob: true,
  jobStatus: true,
  jobList: true,
  retry: true,
  download: true,
  formats: { xls: false, xlsx: true, pdf: false, json: false },
  filters: true,
  columns: true,
  progress: true,
} : realReportsApiCapabilities;

export const reportQueryKeys = {
  jobs: queryKeys.reports.jobs,
  job: queryKeys.reports.job,
  filterOptions: queryKeys.reports.filterOptions,
  templates: queryKeys.reports.templates,
  preview: queryKeys.reports.preview,
  statistics: queryKeys.reports.statistics,
};

/** Backend column identifiers with UI labels; keys mirror analytics/columns.py. */
export const reportColumnDefinitions: ReportColumnDefinition[] = [
  { id: 'university', label: 'Наименование ВУЗа' },
  { id: 'direction', label: 'ИТ-направление' },
  { id: 'program', label: 'ИТ-программа' },
  { id: 'product', label: 'ИТ-продукт' },
  { id: 'workflow_status', label: 'Статус работы' },
  { id: 'responsible', label: 'Ответственный' },
  { id: 'vendor', label: 'Вендор' },
  { id: 'contract_number', label: 'Номер договора' },
  { id: 'license_signed', label: 'Подписание лицензии' },
  { id: 'license_expires', label: 'Срок действия' },
  { id: 'transfer_status', label: 'Статус передачи' },
  { id: 'comment', label: 'Комментарий' },
  { id: 'city', label: 'Город' },
  { id: 'current_stage', label: 'Текущий этап' },
  { id: 'last_interaction', label: 'Последнее взаимодействие' },
  { id: 'workflow_progress', label: 'Прогресс workflow, %' },
  { id: 'overdue_tasks', label: 'Просроченные задачи' },
];

/**
 * The 5 columns the ТЗ names, in ТЗ order. This is the default selection and
 * mirrors backend `TZ_COLUMNS` (= `DEFAULT_COLUMNS`).
 */
export const TZ_REPORT_COLUMNS = [
  'university',
  'direction',
  'product',
  'workflow_status',
  'responsible',
] as const;

/** Presets mirror backend PRESETS: MINIMAL=the ТЗ set, STANDARD adds context, FULL=all. */
export const reportColumnPresetNames = ['По ТЗ', 'Стандарт', 'Полный'] as const;
export const DEFAULT_REPORT_COLUMNS: string[] = [...TZ_REPORT_COLUMNS];
export const reportColumnPresets: Record<(typeof reportColumnPresetNames)[number], string[]> = {
  'По ТЗ': [...TZ_REPORT_COLUMNS],
  Стандарт: [...TZ_REPORT_COLUMNS, 'program', 'city', 'current_stage'],
  Полный: reportColumnDefinitions.map((column) => column.id),
};
export const REPORT_FORMATS: Array<{ id: ReportFormat; label: string }> = [
  { id: 'xls', label: 'XLS' },
  { id: 'xlsx', label: 'XLSX' },
  { id: 'pdf', label: 'PDF' },
  { id: 'json', label: 'JSON' },
];

/** Narrowing helper for API values that may carry an unknown format. */
function asReportFormat(value: unknown): ReportFormat {
  return value === 'xls' || value === 'xlsx' || value === 'pdf' || value === 'json'
    ? value
    : 'xlsx';
}

export const EMPTY_REPORT_FORM: ReportFormValues = {
  dateFrom: '',
  dateTo: '',
  universityIds: [],
  directionIds: [],
  programIds: [],
  productIds: [],
  responsibleIds: [],
  workflowStatuses: [],
  groupBy: '',
  columnIds: DEFAULT_REPORT_COLUMNS,
  format: 'xlsx',
};

/** Calculate presets in local calendar dates; no UTC conversion is involved. */
export function reportPeriodPreset(preset: Exclude<ReportPeriodPreset, null>, now = new Date()): Pick<ReportFormValues, 'dateFrom' | 'dateTo'> {
  return periodPresetRange(preset, now);
}

/**
 * The API filter body for a report request. Single source of truth: the job,
 * preview and statistics endpoints all send exactly this shape.
 */
export function reportFiltersPayload(request: ReportRequest) {
  return {
    date_from: request.date_from || null,
    date_to: request.date_to || null,
    university_ids: request.university_ids,
    direction_ids: request.direction_ids,
    program_ids: request.program_ids,
    product_ids: request.product_ids,
    responsible_ids: request.responsible_ids,
    workflow_statuses: request.workflow_statuses,
  };
}

export function reportRequestFromForm(values: ReportFormValues): ReportRequest {
  return {
    date_from: values.dateFrom,
    date_to: values.dateTo,
    university_ids: values.universityIds,
    direction_ids: values.directionIds,
    program_ids: values.programIds,
    product_ids: values.productIds,
    responsible_ids: values.responsibleIds,
    workflow_statuses: values.workflowStatuses,
    group_by: values.groupBy || null,
    columns: values.columnIds,
    format: values.format,
  };
}

export function reportFormFromTemplate(tpl: ReportTemplate): ReportFormValues {
  // Migrate pre-removal selections: 'software' was a pure alias of 'product'.
  const known = new Set(reportColumnDefinitions.map((column) => column.id));
  const columnIds = tpl.columns
    .map((column) => (column === 'software' ? 'product' : column))
    .filter((column) => known.has(column));
  return {
    dateFrom: tpl.filters.date_from ?? '',
    dateTo: tpl.filters.date_to ?? '',
    universityIds: tpl.filters.university_ids ?? [],
    directionIds: tpl.filters.direction_ids ?? [],
    programIds: tpl.filters.program_ids ?? [],
    productIds: tpl.filters.product_ids ?? [],
    responsibleIds: tpl.filters.responsible_ids ?? [],
    workflowStatuses: tpl.filters.workflow_statuses ?? [],
    groupBy: tpl.groupBy ?? '',
    columnIds: columnIds.length ? columnIds : [...DEFAULT_REPORT_COLUMNS],
    format: tpl.format,
  };
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : value === null || value === undefined ? undefined : String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function reportStatus(value: unknown): ReportJobStatus {
  if (value === 'queued' || value === 'accepted') return 'queued';
  if (value === 'running' || value === 'building') return 'building';
  if (value === 'done' || value === 'ready' || value === 'completed') return 'ready';
  return 'failed';
}

function safeJobError(value: unknown): string | undefined {
  const message = stringValue(value);
  if (!message) return undefined;
  if (message.length > 300 || /(traceback|stack trace|sql|exception|syntaxerror|typeerror)/i.test(message)) return 'Не удалось сформировать отчёт.';
  return message;
}

function reportErrorCode(item: Record<string, unknown>, result: Record<string, unknown>): string | undefined {
  const direct = stringValue(item.error_code ?? item.errorCode ?? result.code ?? item.code);
  if (direct) return direct.toUpperCase();
  const raw = item.error ?? result.error;
  if (isRecord(raw)) return stringValue(raw.code)?.toUpperCase();
  return stringValue(raw)?.toUpperCase() === 'REPORT_FAILED' ? 'REPORT_FAILED' : undefined;
}

function reportErrorMessage(item: Record<string, unknown>, result: Record<string, unknown>, code?: string): string | undefined {
  if (code === 'REPORT_FAILED') return ERROR_MESSAGES.REPORT_FAILED;
  const raw = item.error_message ?? item.error ?? result.error ?? item.message ?? result.message;
  if (isRecord(raw)) return safeJobError(raw.message ?? raw.detail);
  return safeJobError(raw);
}

function reportName(item: Record<string, unknown>, format: ReportFormat): string {
  const direct = stringValue(item.name ?? item.title);
  if (direct) return direct;
  return `Экспорт ${format.toUpperCase()}`;
}

export function adaptReportJob(raw: unknown, fallbackId?: string): ReportJob {
  const item = isRecord(raw) ? raw : {};
  const id = stringValue(item.id ?? item.job_id) ?? fallbackId ?? 'unknown';
  const rawFormat = stringValue(item.format ?? (isRecord(item.payload) ? item.payload.format : undefined));
  const format: ReportFormat = asReportFormat(rawFormat);
  const timestamp = item.created_at ?? item.createdAt ?? item.started_at ?? item.startedAt;
  const createdAt = typeof timestamp === 'number' ? new Date(timestamp * 1000).toISOString() : stringValue(timestamp) ?? new Date().toISOString();
  const result = isRecord(item.result) ? item.result : {};
  const rawProgress = item.progress ?? result.progress;
  const progress = typeof rawProgress === 'number' && Number.isFinite(rawProgress) ? Math.max(0, Math.min(100, rawProgress)) : null;
  const errorCode = reportErrorCode(item, result);
  const expiresAt = stringValue(item.expires_at ?? item.expiresAt);
  const rawSize = item.file_size ?? item.fileSize ?? result.file_size;
  const fileSize = typeof rawSize === 'number' && Number.isFinite(rawSize) ? rawSize : undefined;
  return {
    id,
    name: reportName(item, format),
    format,
    status: reportStatus(item.status),
    progress,
    createdAt,
    expiresAt,
    fileSize,
    error: reportErrorMessage(item, result, errorCode),
    errorCode,
    downloadUrl: item.status === 'ready' ? `/api/v1/reports/${encodeURIComponent(id)}/download` : undefined,
  };
}

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>, message: string): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, message, result.error);
}

async function createRealReportJob(request: ReportRequest): Promise<ReportJob> {
  const result = await apiFetch<unknown>('/api/v1/reports', {
    method: 'POST',
    body: { format: request.format, filters: reportFiltersPayload(request), columns: request.columns, group_by: request.group_by },
  });
  return { ...adaptReportJob(unwrap(result, 'Не удалось создать задачу отчёта.')), format: request.format, request };
}

async function getRealReportJob(jobId: string): Promise<ReportJob> {
  const result = await apiFetch<unknown>(`/api/v1/reports/${encodeURIComponent(jobId)}`);
  return adaptReportJob(unwrap(result, 'Не удалось обновить статус отчёта.'), jobId);
}

export async function createReportJob(request: ReportRequest): Promise<ReportJob> {
  return fromDataSource({ mock: () => mockCreateReportJob(request), real: () => createRealReportJob(request) });
}

export async function getReportJob(jobId: string): Promise<ReportJob> {
  return fromDataSource({ mock: () => mockGetReportJob(jobId), real: () => getRealReportJob(jobId) });
}

/** Retry uses the supported create contract because no retry endpoint exists. */
export async function retryReportJob(job: ReportJob): Promise<ReportJob> {
  if (!job.request) throw new ApiRequestError(409, { code: 'REPORT_RETRY_UNAVAILABLE' }, 'Параметры исходного отчёта недоступны для повтора.');
  return createReportJob(job.request);
}

export async function listReportJobs(): Promise<ReportJob[]> {
  return fromDataSource({ mock: mockListReportJobs, real: async () => {
    const result = await apiFetch<{ items: unknown[]; total: number; page: number; page_size: number }>('/api/v1/reports?page=1&page_size=100');
    return unwrap(result, 'Не удалось загрузить задачи отчётов.').items.map((item) => adaptReportJob(item));
  } });
}

export async function downloadReportJob(jobId: string): Promise<Blob> {
  const result = await apiDownload(`/api/v1/reports/${encodeURIComponent(jobId)}/download`);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось скачать отчёт.', result.error);
  return result.data;
}

function adaptReportTemplate(raw: unknown): ReportTemplate {
  const item = isRecord(raw) ? raw : {};
  const filters = isRecord(item.filters) ? item.filters : {};
  const asIds = (value: unknown): string[] => (Array.isArray(value) ? value.map((v) => String(v)) : []);
  return {
    id: stringValue(item.id) ?? 'unknown',
    name: stringValue(item.name) ?? 'Шаблон',
    ownerSub: stringValue(item.owner_sub ?? item.ownerSub) ?? '',
    isShared: item.is_shared === true || item.isShared === true,
    format: asReportFormat(item.format),
    groupBy: REPORT_GROUP_IDS.find((id) => id === (item.group_by ?? filters._group_by)) ?? null,
    filters: {
      date_from: stringValue(filters.date_from ?? filters.dateFrom) ?? '',
      date_to: stringValue(filters.date_to ?? filters.dateTo) ?? '',
      university_ids: asIds(filters.university_ids ?? filters.universityIds),
      direction_ids: asIds(filters.direction_ids ?? filters.directionIds),
      program_ids: asIds(filters.program_ids ?? filters.programIds),
      product_ids: asIds(filters.product_ids ?? filters.productIds),
      responsible_ids: asIds(filters.responsible_ids ?? filters.responsibleIds),
      workflow_statuses: asIds(filters.workflow_statuses ?? filters.workflowStatuses) as UniversityWorkflowStageStatus[],
    },
    columns: asIds(item.columns),
  };
}

const mockTemplates = new Map<string, ReportTemplate>();

export async function listReportTemplates(): Promise<ReportTemplate[]> {
  return fromDataSource({
    mock: async () => [...mockTemplates.values()].sort((a, b) => a.name.localeCompare(b.name)),
    real: async () => {
      const result = await apiFetch<unknown[]>('/api/v1/reports/templates');
      return unwrap(result, 'Не удалось загрузить шаблоны отчётов.').map(adaptReportTemplate);
    },
  });
}

export async function createReportTemplate(name: string, request: ReportRequest, isShared = false): Promise<ReportTemplate> {
  return fromDataSource({
    mock: async () => {
      const tpl: ReportTemplate = {
        id: `tpl-${Date.now()}`,
        name,
        ownerSub: 'mock-user',
        isShared: false,
        format: request.format,
        groupBy: request.group_by,
        filters: {
          date_from: request.date_from,
          date_to: request.date_to,
          university_ids: request.university_ids,
          direction_ids: request.direction_ids,
          program_ids: request.program_ids,
          product_ids: request.product_ids,
          responsible_ids: request.responsible_ids,
          workflow_statuses: request.workflow_statuses,
        },
        columns: request.columns,
      };
      mockTemplates.set(tpl.id, tpl);
      return tpl;
    },
    real: async () => {
      const result = await apiFetch<unknown>('/api/v1/reports/templates', {
        method: 'POST',
        body: {
          name,
          format: request.format,
          group_by: request.group_by,
          filters: {
            date_from: request.date_from || null,
            date_to: request.date_to || null,
            university_ids: request.university_ids,
            direction_ids: request.direction_ids,
            program_ids: request.program_ids,
            product_ids: request.product_ids,
            responsible_ids: request.responsible_ids,
            workflow_statuses: request.workflow_statuses,
          },
          columns: request.columns,
          is_shared: isShared,
        },
      });
      return adaptReportTemplate(unwrap(result, 'Не удалось сохранить шаблон.'));
    },
  });
}

export async function deleteReportTemplate(templateId: string): Promise<void> {
  return fromDataSource({
    mock: async () => { mockTemplates.delete(templateId); },
    real: async () => {
      const result = await apiFetch<unknown>(`/api/v1/reports/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
      unwrap(result, 'Не удалось удалить шаблон.');
    },
  });
}

/* ---------------------------------------------------------------- preview */

/**
 * First page of the filtered selection (ТЗ step "увидеть актуальную выборку").
 *
 * The row cap applies to the PREVIEW response only: `total` is the full
 * export size, so the UI can say "показано 50 из N" and the export still
 * contains every row.
 */
export interface ReportPreview {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  total: number;
  universityCount: number;
  previewLimit: number;
}

export const REPORT_PREVIEW_LIMIT = 50;

export async function getReportPreview(
  request: ReportRequest,
  limit: number = REPORT_PREVIEW_LIMIT,
): Promise<ReportPreview> {
  return fromDataSource({
    mock: async () => ({
      columns: request.columns,
      rows: [],
      total: 0,
      universityCount: 0,
      previewLimit: limit,
    }),
    real: async () => {
      const result = await apiFetch<ReportPreview>(`/api/v1/reports/preview?limit=${limit}`, {
        method: 'POST',
        body: {
          format: request.format,
          filters: reportFiltersPayload(request),
          columns: request.columns,
          group_by: request.group_by,
        },
      });
      return unwrap(result, 'Не удалось получить предпросмотр выборки.');
    },
  });
}

/* ------------------------------------------------------------- statistics */

export interface ReportStatBucket {
  label: string;
  count: number;
}

export interface ReportStatSlice {
  dimension: string;
  title: string;
  /** What the counts mean: report rows or distinct universities. */
  unit: 'rows' | 'universities';
  total: number;
  buckets: ReportStatBucket[];
}

export interface ReportStatistics {
  universityCount: number;
  rowCount: number;
  columns: string[];
  slices: ReportStatSlice[];
  grouped?: ReportStatSlice | null;
}

/**
 * Aggregated view of the same selection the table shows.
 *
 * The buckets come from the same `UnifiedFilter`, so a chart can never
 * describe a different selection than the exported table.
 */
export async function getReportStatistics(request: ReportRequest): Promise<ReportStatistics> {
  return fromDataSource({
    mock: async (): Promise<ReportStatistics> => ({ universityCount: 0, rowCount: 0, columns: request.columns, slices: [], grouped: null }),
    real: async () => {
      const result = await apiFetch<{
        university_count: number;
        row_count: number;
        columns: string[];
        slices: Array<{
          dimension: string;
          title: string;
          unit: 'rows' | 'universities';
          total: number;
          buckets: Array<{ label: string; count: number }>;
        }>;
        grouped?: { dimension: string; title: string; unit: 'rows' | 'universities'; total: number; buckets: Array<{ label: string; count: number }> } | null;
      }>('/api/v1/reports/statistics', {
        method: 'POST',
        body: { filters: reportFiltersPayload(request), columns: request.columns, group_by: request.group_by },
      });
      const data = unwrap(result, 'Не удалось получить статистику по выборке.');
      return {
        universityCount: data.university_count,
        rowCount: data.row_count,
        columns: data.columns,
        slices: data.slices.map((slice) => ({
          dimension: slice.dimension,
          title: slice.title,
          unit: slice.unit,
          total: slice.total,
          buckets: slice.buckets,
        })),
        grouped: data.grouped ?? null,
      };
    },
  });
}
