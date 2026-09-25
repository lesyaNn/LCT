import { apiFetch } from './api-client';
import { ApiRequestError, ERROR_MESSAGES } from './api-errors';
import { fromDataSource, isMockDataSource } from './data-source';
import { periodPresetRange, type PeriodPreset } from './date-period';
import { queryKeys } from './query-keys';
import { universityFilterOptions, universityProgramDirectionOptions, type UniversityWorkflowStageStatus } from './universities-repository';
import { workflowStageStatusSemantics } from './status-semantics';
import { mockCreateReportJob, mockGetReportJob, mockListReportJobs } from '@/shared/mocks/api-adapter';

export type ReportFormat = 'xlsx' | 'pdf' | 'json';

export type ReportPeriodPreset = PeriodPreset | null;
export type ReportJobStatus = 'queued' | 'building' | 'ready' | 'failed';

export interface ReportFormValues {
  dateFrom: string;
  dateTo: string;
  universityIds: string[];
  directionIds: string[];
  productIds: string[];
  responsibleIds: string[];
  workflowStatuses: UniversityWorkflowStageStatus[];
  columnIds: string[];
  format: ReportFormat;
}

export interface ReportRequest {
  date_from: string;
  date_to: string;
  university_ids: string[];
  direction_ids: string[];
  product_ids: string[];
  responsible_ids: string[];
  workflow_statuses: UniversityWorkflowStageStatus[];
  columns: string[];
  format: ReportFormat;
}

export interface ReportJob {
  id: string;
  name: string;
  format: ReportFormat;
  status: ReportJobStatus;
  progress: number | null;
  createdAt: string;
  error?: string;
  errorCode?: string;
  downloadUrl?: string;
  /** The original form request is retained for create-based retry. */
  request?: ReportRequest;
}

export interface ReportFilterOptions {
  universities: Array<{ id: string; name: string }>;
  directions: Array<{ id: string; name: string }>;
  products: Array<{ id: string; name: string }>;
  responsibles: Array<{ id: string; name: string; description?: string }>;
  workflowStatuses: Array<{ id: UniversityWorkflowStageStatus; name: string }>;
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

/** The only current reporting router accepts format, region and columns. */
const realReportsApiCapabilities: ReportsApiCapabilities = {
  createJob: true,
  jobStatus: true,
  jobList: false,
  // The current API has no dedicated retry route. The UI retries by creating
  // another job with the original request payload.
  retry: true,
  download: false,
  formats: { xlsx: true, pdf: false, json: false },
  filters: false,
  columns: true,
  progress: false,
};

export const REPORTS_API_CAPABILITIES: ReportsApiCapabilities = isMockDataSource ? {
  createJob: true,
  jobStatus: true,
  jobList: true,
  retry: true,
  download: true,
  formats: { xlsx: true, pdf: false, json: false },
  filters: true,
  columns: true,
  progress: true,
} : realReportsApiCapabilities;

export const reportQueryKeys = {
  jobs: queryKeys.reports.jobs,
  job: queryKeys.reports.job,
  filterOptions: queryKeys.reports.filterOptions,
};

export const reportFilterOptions: ReportFilterOptions = {
  universities: universityFilterOptions.universities,
  directions: universityProgramDirectionOptions,
  products: universityFilterOptions.products,
  responsibles: universityFilterOptions.responsibles.map((item) => ({ id: item.id, name: item.name, description: item.role })),
  workflowStatuses: (Object.keys(workflowStageStatusSemantics) as UniversityWorkflowStageStatus[]).map((id) => ({ id, name: workflowStageStatusSemantics[id].label })),
};

/** Column identifiers are kept separate from UI labels until P4-02-01 publishes its config. */
export const reportColumnDefinitions: ReportColumnDefinition[] = [
  { id: 'university_name', label: 'Наименование ВУЗа' },
  { id: 'it_direction', label: 'ИТ-направление' },
  { id: 'it_program', label: 'ИТ-программа' },
  { id: 'it_product', label: 'ИТ-продукт' },
  { id: 'workflow_status', label: 'Статус работы' },
  { id: 'responsible', label: 'Ответственный' },
  { id: 'vendor', label: 'Вендор' },
  { id: 'software', label: 'ПО' },
  { id: 'contract_number', label: 'Номер договора' },
  { id: 'license_signed_at', label: 'Подписание лицензии' },
  { id: 'license_expires_at', label: 'Срок действия' },
  { id: 'transfer_status', label: 'Статус передачи' },
  { id: 'comment', label: 'Комментарий' },
  { id: 'health_score', label: 'Health Score' },
];

/** Exact preset compositions are intentionally unavailable until P4-02-01. */
export const reportColumnPresetNames = ['Минимум', 'Стандарт', 'Полный', 'Для руководителя'] as const;
export const DEFAULT_REPORT_COLUMNS = ['university_name', 'workflow_status', 'responsible'];
export const REPORT_FORMATS: Array<{ id: ReportFormat; label: string }> = [
  { id: 'xlsx', label: 'XLSX' },
  { id: 'pdf', label: 'PDF' },
  { id: 'json', label: 'JSON' },
];

export const EMPTY_REPORT_FORM: ReportFormValues = {
  dateFrom: '',
  dateTo: '',
  universityIds: [],
  directionIds: [],
  productIds: [],
  responsibleIds: [],
  workflowStatuses: [],
  columnIds: DEFAULT_REPORT_COLUMNS,
  format: 'xlsx',
};

/** Calculate presets in local calendar dates; no UTC conversion is involved. */
export function reportPeriodPreset(preset: Exclude<ReportPeriodPreset, null>, now = new Date()): Pick<ReportFormValues, 'dateFrom' | 'dateTo'> {
  return periodPresetRange(preset, now);
}

export function reportRequestFromForm(values: ReportFormValues): ReportRequest {
  return {
    date_from: values.dateFrom,
    date_to: values.dateTo,
    university_ids: values.universityIds,
    direction_ids: values.directionIds,
    product_ids: values.productIds,
    responsible_ids: values.responsibleIds,
    workflow_statuses: values.workflowStatuses,
    columns: values.columnIds,
    format: values.format,
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
  const raw = item.error ?? result.error ?? item.message ?? result.message;
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
  const format: ReportFormat = rawFormat === 'pdf' || rawFormat === 'json' ? rawFormat : 'xlsx';
  const timestamp = item.created_at ?? item.createdAt ?? item.started_at ?? item.startedAt;
  const createdAt = typeof timestamp === 'number' ? new Date(timestamp * 1000).toISOString() : stringValue(timestamp) ?? new Date().toISOString();
  const result = isRecord(item.result) ? item.result : {};
  const rawProgress = item.progress ?? result.progress;
  const progress = typeof rawProgress === 'number' && Number.isFinite(rawProgress) ? Math.max(0, Math.min(100, rawProgress)) : null;
  const errorCode = reportErrorCode(item, result);
  return {
    id,
    name: reportName(item, format),
    format,
    status: reportStatus(item.status),
    progress,
    createdAt,
    error: reportErrorMessage(item, result, errorCode),
    errorCode,
    downloadUrl: stringValue(item.download_url ?? item.downloadUrl ?? result.download_url ?? result.downloadUrl),
  };
}

function unwrap<T>(result: Awaited<ReturnType<typeof apiFetch<T>>>, message: string): T {
  if (result.ok) return result.data;
  throw new ApiRequestError(result.status, result.body, message, result.error);
}

async function createRealReportJob(request: ReportRequest): Promise<ReportJob> {
  // Only format/columns exist in the current reporting router. Filters stay in
  // the normalized form model and are not silently sent as invented DTO keys.
  const result = await apiFetch<unknown>('/api/v1/reports/export', { method: 'POST', body: { format: request.format, columns: request.columns } });
  return { ...adaptReportJob(unwrap(result, 'Не удалось создать задачу отчёта.')), request };
}

async function getRealReportJob(jobId: string): Promise<ReportJob> {
  const result = await apiFetch<unknown>(`/api/v1/reports/jobs/${encodeURIComponent(jobId)}`);
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

/** No list endpoint exists in the current reporting API. */
export async function listReportJobs(): Promise<ReportJob[]> {
  return fromDataSource({ mock: mockListReportJobs, real: () => [] });
}
