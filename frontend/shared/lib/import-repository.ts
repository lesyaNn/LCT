import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockExecuteImport,
  mockGetImportJob,
  mockListImportJobs,
  mockUploadImportPreview,
} from '@/shared/mocks/api-adapter';
import {
  realExecuteImport,
  realGetImportJob,
  realListImportJobs,
  realUploadImportPreview,
} from './real-api-adapter';

export type ImportCatalogType = 'universities' | 'products' | 'directions' | 'responsibles' | 'licenses';
export type ImportJobStatus = 'queued' | 'processing' | 'done' | 'failed';

export interface ImportCatalogOption {
  id: ImportCatalogType;
  label: string;
  description: string;
}

export const importCatalogOptions: ImportCatalogOption[] = [
  { id: 'universities', label: 'ВУЗы', description: 'Названия и реквизиты образовательных организаций' },
  { id: 'products', label: 'Продукты', description: 'ИТ-продукты, версии и поставщики' },
  { id: 'directions', label: 'Направления', description: 'ИТ-направления и программы' },
  { id: 'responsibles', label: 'Ответственные', description: 'Менеджеры и представители ВУЗа' },
  { id: 'licenses', label: 'Лицензии', description: 'Лицензии, договоры и сроки действия' },
];

export function isImportCatalogType(value: unknown): value is ImportCatalogType {
  return importCatalogOptions.some((option) => option.id === value);
}

export interface ImportTargetField {
  id: string;
  label: string;
  description?: string;
}

/**
 * These identifiers mirror the backend TARGET_FIELDS contract. Labels stay
 * human-readable in the UI; only the id is sent to POST /import/execute.
 */
export const importTargetFields: ImportTargetField[] = [
  { id: 'university.name', label: 'Название ВУЗа' },
  { id: 'vendor.name', label: 'Вендор' },
  { id: 'product.name', label: 'Название продукта' },
  { id: 'product.version', label: 'Версия продукта' },
  { id: 'direction.code', label: 'Код направления' },
  { id: 'direction.name', label: 'Название направления' },
  { id: 'program.name', label: 'Название программы' },
  { id: 'program.description', label: 'Описание программы' },
  { id: 'contract.contract_number', label: 'Номер договора' },
  { id: 'license.signed_at', label: 'Дата подписания лицензии' },
  { id: 'license.expires_at', label: 'Срок действия лицензии' },
  { id: 'license.transfer_status', label: 'Статус передачи' },
  { id: 'license.comment', label: 'Комментарий к лицензии' },
  { id: 'responsible.full_name', label: 'ФИО ответственного' },
  { id: 'university_responsibles', label: 'Ответственные от ВУЗа' },
];

/** The import service validates these values for every catalog row. */
export const requiredImportFields = [
  'university.name',
  'contract.contract_number',
  'license.expires_at',
] as const;

export interface ImportPreviewResponse {
  file_id: string;
  filename: string;
  headers: string[];
  preview: Array<Record<string, string | number | boolean | null>>;
  row_count: number;
  detected_sheet?: string;
}

export interface ImportOptions {
  skip_header: boolean;
  update_existing: boolean;
  dry_run: boolean;
}

export interface ImportRowError {
  row: number;
  field: string;
  error: string;
}

export interface ImportSummary {
  total_rows: number;
  inserted: number;
  updated: number;
  skipped: number;
  errors: ImportRowError[];
  dry_run: boolean;
}

export interface ImportJob {
  id: string;
  type: string;
  status: ImportJobStatus;
  createdAt: string;
  createdBy?: string;
  filename?: string;
  catalogType?: ImportCatalogType;
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

function rowErrors(value: unknown): ImportRowError[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item)) return [];
    const row = typeof item.row === 'number' ? item.row : Number(item.row);
    if (!Number.isFinite(row)) return [];
    return [{ row, field: stringValue(item.field) ?? 'row', error: stringValue(item.error ?? item.message) ?? 'Ошибка строки' }];
  });
}

export function adaptImportSummary(raw: unknown): ImportSummary | undefined {
  if (!isRecord(raw)) return undefined;
  const source = isRecord(raw.result) ? raw.result : raw;
  if (!('total_rows' in source) && !('totalRows' in source) && !('inserted' in source) && !('errors' in source)) return undefined;
  return {
    total_rows: numberValue(source.total_rows ?? source.totalRows),
    inserted: numberValue(source.inserted),
    updated: numberValue(source.updated),
    skipped: numberValue(source.skipped),
    errors: rowErrors(source.errors),
    dry_run: Boolean(source.dry_run ?? source.dryRun),
  };
}

function statusValue(value: unknown): ImportJobStatus {
  if (value === 'queued' || value === 'processing' || value === 'done' || value === 'failed') return value;
  if (value === 'running' || value === 'in_progress') return 'processing';
  if (value === 'completed' || value === 'success') return 'done';
  return 'failed';
}

export function adaptImportJob(raw: unknown, fallbackId?: string): ImportJob {
  const item = isRecord(raw) ? raw : {};
  const result = adaptImportSummary(item.result ?? item.summary);
  const timestamp = item.created_at ?? item.createdAt ?? item.started_at ?? item.startedAt;
  const createdAt = typeof timestamp === 'number'
    ? new Date(timestamp * 1000).toISOString()
    : stringValue(timestamp) ?? new Date().toISOString();
  const rawCatalogType = stringValue(item.catalog_type ?? item.catalogType);
  const catalogType = importCatalogOptions.some((option) => option.id === rawCatalogType)
    ? rawCatalogType as ImportCatalogType
    : undefined;
  const errorValue = isRecord(item.error) ? item.error.message : item.error ?? item.message;
  return {
    id: stringValue(item.id ?? item.job_id) ?? fallbackId ?? 'unknown',
    type: stringValue(item.type) ?? 'xlsx_import',
    status: statusValue(item.status),
    createdAt,
    createdBy: stringValue(item.created_by ?? item.createdBy ?? item.user_name ?? item.userName),
    filename: stringValue(item.filename ?? item.file_name ?? item.fileName),
    catalogType,
    result,
    error: stringValue(errorValue),
    errorReportUrl: stringValue(item.error_report_url ?? item.errorReportUrl ?? (isRecord(item.result) ? item.result.error_report_url ?? item.result.errorReportUrl : undefined)),
  };
}

export function validateImportFile(file: File): string | null {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!supportedExtensions.includes(extension as (typeof supportedExtensions)[number])) return 'Загрузите файл в формате .xlsx или .xls.';
  if (file.size === 0) return 'Файл пустой. Выберите файл с данными.';
  if (file.size > MAX_FILE_BYTES) return 'Файл больше лимита 10 МБ.';
  return null;
}

export async function uploadImportPreview(file: File, signal?: AbortSignal, onProgress?: (value: number) => void): Promise<ImportPreviewResponse> {
  const validationError = validateImportFile(file);
  if (validationError) throw new ApiRequestError(400, { detail: validationError }, validationError);
  onProgress?.(0);
  const result = await fromDataSource({
    mock: () => mockUploadImportPreview(file),
    real: () => realUploadImportPreview(file, signal, onProgress),
    signal,
  });
  onProgress?.(100);
  return result;
}

export async function executeImport(fileId: string, mapping: Record<string, string>, options: ImportOptions): Promise<ImportExecuteResponse> {
  return fromDataSource({
    mock: () => mockExecuteImport(fileId, mapping, options),
    real: () => realExecuteImport(fileId, mapping, options),
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

export function importTargetLabel(id: string): string {
  return importTargetFields.find((field) => field.id === id)?.label ?? id;
}

export function normalizeImportHeader(value: string): string {
  return value
    .toLocaleLowerCase('ru-RU')
    .replace(/[ё]/g, 'е')
    .trim()
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ');
}

const importHeaderAliases: Record<string, string[]> = {
  'university.name': ['вуз', 'название вуз', 'название вуза', 'университет', 'наименование вуза', 'university name', 'university'],
  'vendor.name': ['вендор', 'поставщик', 'vendor', 'vendor name'],
  'product.name': ['продукт', 'по', 'название продукта', 'программное обеспечение', 'product', 'product name'],
  'product.version': ['версия', 'версия продукта', 'product version', 'version'],
  'direction.code': ['код направления', 'код ит направления', 'direction code'],
  'direction.name': ['направление', 'ит направление', 'название направления', 'direction', 'direction name'],
  'program.name': ['программа', 'ит программа', 'название программы', 'program', 'program name'],
  'program.description': ['описание программы', 'описание', 'program description'],
  'contract.contract_number': ['номер договора', 'договор', 'contract number', 'contract'],
  'license.signed_at': ['подписание лицензии', 'дата подписания', 'дата лицензии', 'license signed at', 'signed at'],
  'license.expires_at': ['срок действия лицензии', 'срок действия', 'год окончания', 'год действия лицензии', 'license expires at', 'expires at'],
  'license.transfer_status': ['статус передачи', 'статус по передачи', 'статус лицензии', 'transfer status'],
  'license.comment': ['комментарий', 'комментарий к лицензии', 'примечание', 'comment'],
  'responsible.full_name': ['фио', 'фио менеджера', 'ответственный', 'ответственный менеджер', 'responsible', 'responsible full name'],
  university_responsibles: ['ответственные от вуза', 'контакты вуза', 'представители вуза', 'university responsibles'],
};

export function autoMapImportHeaders(headers: string[]): Record<string, string> {
  const mapping: Record<string, string> = {};
  const usedTargets = new Set<string>();
  for (const header of headers) {
    const normalized = normalizeImportHeader(header);
    if (!normalized) continue;
    let candidate: string | undefined;
    for (const field of importTargetFields) {
      if (usedTargets.has(field.id)) continue;
      const fieldName = normalizeImportHeader(field.id.replace('.', ' '));
      const aliases = (importHeaderAliases[field.id] ?? []).map(normalizeImportHeader);
      if (normalized === fieldName || aliases.includes(normalized)) {
        candidate = field.id;
        break;
      }
      if (!candidate && (normalized.includes(fieldName) || aliases.some((alias) => normalized.includes(alias) || alias.includes(normalized)))) candidate = field.id;
    }
    if (candidate) {
      mapping[header] = candidate;
      usedTargets.add(candidate);
    }
  }
  return mapping;
}

export function isImportJobActive(job: ImportJob): boolean {
  return job.status === 'queued' || job.status === 'processing';
}

export { MAX_FILE_BYTES };
