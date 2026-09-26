import { ApiRequestError } from './api-errors';
import type { QueryClient } from '@tanstack/react-query';
import { apiDownload } from './api-client';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockExecuteSheetImport,
  mockExecuteSheetsImport,
  mockGetImportJob,
  mockListImportJobs,
  mockPreviewImportSheet,
  mockUploadImportFile,
} from '@/shared/mocks/api-adapter';
import {
  realExecuteSheetImport,
  realExecuteSheetsImport,
  realGetImportJob,
  realListImportJobs,
  realPreviewImportSheet,
  realUploadImportFile,
} from './real-api-adapter';

/**
 * Import v2: файл целиком загружается на сервер, дальше пользователь
 * выбирает ОДИН лист из выпадающего списка и запускает его импорт.
 * Маппинг колонок держит сервер (структура листов фиксирована),
 * поэтому шагов сопоставления на клиенте больше нет.
 *
 * Контракт backend (реализовать при перестройке API):
 * - POST /api/v1/import/upload (multipart: file)
 *     -> { file_id, filename, sheets: [{ id, label, row_count }] }
 * - POST /api/v1/import/sheets/preview { file_id, sheet }
 *     -> { file_id, sheet, headers, preview, row_count }
 * - POST /api/v1/import/execute { file_id, sheet?, sheets?, dry_run, update_existing, filename }
 *     -> { job_id } (sheets = пачка одной транзакцией, sheets-итоги в result.sheets)
 * - GET /api/v1/import/jobs, GET /api/v1/import/jobs/{id},
 *   GET /api/v1/import/jobs/{id}/report — без изменений.
 */

export type ImportJobStatus = 'queued' | 'processing' | 'done' | 'failed';

export interface ImportSheet {
  id: string;
  label: string;
  row_count: number;
}

export interface ImportUploadResponse {
  file_id: string;
  filename: string;
  sheets: ImportSheet[];
}

export type ImportPreviewCell = string | number | boolean | null;

export interface ImportSheetPreview {
  file_id: string;
  sheet: string;
  headers: string[];
  preview: Array<Record<string, ImportPreviewCell>>;
  row_count: number;
}

export interface ImportRunOptions {
  dry_run: boolean;
  update_existing: boolean;
  filename?: string;
}

export interface ImportRowError {
  row: number;
  field: string;
  sourceField?: string;
  code?: string;
  error: string;
}

export interface ImportSheetResult {
  sheet: string;
  summary: ImportSummary | null;
  error?: string;
}

export interface ImportSummary {
  total_rows: number;
  inserted: number;
  updated: number;
  skipped: number;
  errors: ImportRowError[];
  dry_run: boolean;
  errors_total?: number;
  truncated?: boolean;
  sheets?: ImportSheetResult[];
}

export interface ImportJob {
  id: string;
  type: string;
  status: ImportJobStatus;
  progress: number | null;
  dryRun: boolean;
  createdAt: string;
  createdBy?: string;
  filename?: string;
  sheet?: string;
  result?: ImportSummary;
  error?: string;
  errorReportUrl?: string;
}

export interface ImportExecuteResponse { job_id: string; }

export const importQueryKeys = {
  preview: queryKeys.imports.preview,
  jobs: queryKeys.imports.jobs,
  job: queryKeys.imports.job,
};

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const supportedExtensions = ['.xlsx', '.xls'] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function sheetList(value: unknown): ImportSheet[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item)) return [];
    const id = stringValue(item.id ?? item.sheet ?? item.name);
    if (!id) return [];
    return [{
      id,
      label: stringValue(item.label ?? item.title ?? item.name) ?? id,
      row_count: numberValue(item.row_count ?? item.rowCount ?? item.rows),
    }];
  });
}

export function adaptUploadResponse(raw: unknown): ImportUploadResponse {
  const item = isRecord(raw) ? raw : {};
  return {
    file_id: stringValue(item.file_id ?? item.fileId) ?? '',
    filename: stringValue(item.filename ?? item.file_name ?? item.fileName) ?? '',
    sheets: sheetList(item.sheets),
  };
}

export function adaptSheetPreview(raw: unknown): ImportSheetPreview {
  const item = isRecord(raw) ? raw : {};
  const headers = Array.isArray(item.headers)
    ? item.headers.filter((header): header is string => typeof header === 'string')
    : [];
  const preview = Array.isArray(item.preview)
    ? item.preview.filter(isRecord) as Array<Record<string, ImportPreviewCell>>
    : [];
  return {
    file_id: stringValue(item.file_id ?? item.fileId) ?? '',
    sheet: stringValue(item.sheet ?? item.sheet_id ?? item.sheetId) ?? '',
    headers,
    preview,
    row_count: numberValue(item.row_count ?? item.rowCount),
  };
}

function rowErrors(value: unknown): ImportRowError[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item)) return [];
    const row = typeof item.row === 'number' ? item.row : Number(item.row);
    if (!Number.isFinite(row)) return [];
    return [{ row, field: stringValue(item.field) ?? 'row', sourceField: stringValue(item.source_field), code: stringValue(item.code), error: stringValue(item.error ?? item.message) ?? 'Ошибка строки' }];
  });
}

export function adaptImportSummary(raw: unknown): ImportSummary | undefined {
  if (!isRecord(raw)) return undefined;
  const source = isRecord(raw.result) ? raw.result : raw;
  if (!('total_rows' in source) && !('totalRows' in source) && !('inserted' in source) && !('errors' in source)) return undefined;
  const sheets = Array.isArray(source.sheets)
    ? source.sheets.flatMap((item): ImportSheetResult[] => {
        if (!isRecord(item)) return [];
        const sheet = stringValue(item.sheet) ?? '';
        if (!sheet) return [];
        return [{ sheet, summary: adaptImportSummary(item.summary) ?? null, error: stringValue(item.error) }];
      })
    : undefined;
  return {
    total_rows: numberValue(source.total_rows ?? source.totalRows),
    inserted: numberValue(source.inserted),
    updated: numberValue(source.updated),
    skipped: numberValue(source.skipped),
    errors: rowErrors(source.errors),
    dry_run: Boolean(source.dry_run ?? source.dryRun),
    errors_total: numberValue(source.errors_total),
    truncated: Boolean(source.truncated),
    ...(sheets ? { sheets } : {}),
  };
}

function statusValue(value: unknown): ImportJobStatus {
  if (value === 'queued' || value === 'processing' || value === 'done' || value === 'failed') return value;
  if (value === 'running' || value === 'in_progress' || value === 'building') return 'processing';
  if (value === 'completed' || value === 'success' || value === 'ready') return 'done';
  return 'failed';
}

export function adaptImportJob(raw: unknown, fallbackId?: string): ImportJob {
  const item = isRecord(raw) ? raw : {};
  const result = adaptImportSummary(item.result ?? item.summary);
  const timestamp = item.created_at ?? item.createdAt ?? item.started_at ?? item.startedAt;
  const createdAt = typeof timestamp === 'number'
    ? new Date(timestamp * 1000).toISOString()
    : stringValue(timestamp) ?? new Date().toISOString();
  const errorValue = isRecord(item.error) ? item.error.message : item.error ?? item.message;
  return {
    id: stringValue(item.id ?? item.job_id) ?? fallbackId ?? 'unknown',
    type: stringValue(item.type) ?? 'xlsx_import',
    status: statusValue(item.status),
    progress: typeof item.progress === 'number' ? item.progress : null,
    dryRun: Boolean(item.dry_run ?? item.dryRun),
    createdAt,
    createdBy: stringValue(item.created_by ?? item.createdBy ?? item.user_name ?? item.userName),
    filename: stringValue(item.filename ?? item.file_name ?? item.fileName),
    sheet: stringValue(item.sheet ?? item.sheet_id ?? item.sheetId ?? item.catalog_type ?? item.catalogType),
    result,
    error: stringValue(errorValue),
    errorReportUrl: stringValue(item.error_report_url ?? item.errorReportUrl ?? (isRecord(item.result) ? item.result.error_report_url ?? item.result.errorReportUrl : undefined)),
  };
}

export function validateImportFile(file: File): string | null {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!supportedExtensions.includes(extension as (typeof supportedExtensions)[number])) return 'Загрузите файл в формате .xlsx или .xls.';
  const acceptedMime = extension === '.xlsx' ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' : 'application/vnd.ms-excel';
  if (file.type && file.type !== acceptedMime && file.type !== 'application/octet-stream') return 'Тип файла не соответствует расширению Excel.';
  if (file.size === 0) return 'Файл пустой. Выберите файл с данными.';
  if (file.size > MAX_FILE_BYTES) return 'Файл больше лимита 10 МБ.';
  return null;
}

export async function uploadImportFile(file: File, signal?: AbortSignal, onProgress?: (value: number) => void): Promise<ImportUploadResponse> {
  const validationError = validateImportFile(file);
  if (validationError) throw new ApiRequestError(400, { detail: validationError }, validationError);
  onProgress?.(0);
  const raw = await fromDataSource({
    mock: () => mockUploadImportFile(file),
    real: () => realUploadImportFile(file, signal, onProgress),
    signal,
  });
  onProgress?.(100);
  return adaptUploadResponse(raw);
}

export async function previewImportSheet(fileId: string, sheet: string, signal?: AbortSignal): Promise<ImportSheetPreview> {
  const raw = await fromDataSource({
    mock: () => mockPreviewImportSheet(fileId, sheet),
    real: () => realPreviewImportSheet(fileId, sheet, signal),
    signal,
  });
  return adaptSheetPreview(raw);
}

export async function executeSheetImport(fileId: string, sheet: string, options: ImportRunOptions): Promise<ImportExecuteResponse> {
  return fromDataSource({
    mock: () => mockExecuteSheetImport(fileId, sheet, options),
    real: () => realExecuteSheetImport(fileId, sheet, options),
  });
}

export async function executeSheetsImport(fileId: string, sheets: string[], options: ImportRunOptions): Promise<ImportExecuteResponse> {
  return fromDataSource({
    mock: () => mockExecuteSheetsImport(fileId, sheets, options),
    real: () => realExecuteSheetsImport(fileId, sheets, options),
  });
}

export async function getImportJob(jobId: string): Promise<ImportJob> {
  const raw = await fromDataSource({ mock: () => mockGetImportJob(jobId), real: () => realGetImportJob(jobId) });
  return adaptImportJob(raw, jobId);
}

export async function listImportJobs(): Promise<ImportJob[]> {
  const items = await fromDataSource({ mock: mockListImportJobs, real: realListImportJobs });
  return items.map((item) => adaptImportJob(item));
}

export async function downloadImportReport(jobId: string): Promise<Blob> {
  const result = await apiDownload(`/api/v1/import/jobs/${encodeURIComponent(jobId)}/report`);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось скачать отчёт импорта.', result.error);
  return result.data;
}

export function isImportJobActive(job: ImportJob): boolean {
  return job.status === 'queued' || job.status === 'processing';
}

/**
 * Канонический порядок импорта листов (зависимости: направления раньше
 * программ, вузы/продукты раньше связей). Неизвестные листы идут в конце.
 */
export const importSheetOrder = [
  'Направления',
  'Программы',
  'ВУЗы',
  'ИТ-продукты',
  'Ответственные ВУЗа',
  'Договоры и лицензии',
  'Продукт_Направление',
];

export function sortSheetsForImport(sheets: ImportSheet[]): ImportSheet[] {
  const rank = new Map(importSheetOrder.map((id, index) => [id, index]));
  return [...sheets].sort((a, b) => {
    const ra = rank.get(a.id) ?? Number.MAX_SAFE_INTEGER;
    const rb = rank.get(b.id) ?? Number.MAX_SAFE_INTEGER;
    return ra - rb || a.label.localeCompare(b.label, 'ru');
  });
}

/** Ждать терминального статуса задачи (готово/ошибка) с опросом сервера. */
export async function waitForImportJob(
  jobId: string,
  options?: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal },
): Promise<ImportJob> {
  const intervalMs = options?.intervalMs ?? 2000;
  const timeoutMs = options?.timeoutMs ?? 5 * 60 * 1000;
  const startedAt = Date.now();
  for (;;) {
    if (options?.signal?.aborted) throw new DOMException('Ожидание прервано', 'AbortError');
    const job = await getImportJob(jobId);
    if (!isImportJobActive(job)) return job;
    if (Date.now() - startedAt > timeoutMs) throw new Error('Превышено время ожидания задачи импорта.');
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/** Refresh every server-state family a completed import may affect. */
export async function invalidateImportedDomains(queryClient: QueryClient): Promise<void> {
  const keys: Array<readonly unknown[]> = [
    queryKeys.catalogs.references,
    queryKeys.reports.filterOptions,
    queryKeys.audit.all,
    queryKeys.universities.all,
    queryKeys.universities.passports,
    queryKeys.universities.licensesAll,
    queryKeys.universities.documentsAll,
    queryKeys.universities.productsAll,
    queryKeys.universities.programsAll,
    queryKeys.universities.responsiblesAll,
    queryKeys.dashboard.overview,
    queryKeys.dashboard.analytics,
  ];
  await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export { MAX_FILE_BYTES };
