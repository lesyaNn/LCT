import { ApiRequestError } from './api-errors';
import type { QueryClient } from '@tanstack/react-query';
import { apiDownload } from './api-client';
import { fromDataSource, isMockDataSource } from './data-source';
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

export type ImportCatalogType = 'universities' | 'products' | 'directions' | 'responsibles' | 'licenses' | 'vendor_contacts';
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
  { id: 'vendor_contacts', label: 'Контакты поставщиков', description: 'Контакты существующих вендоров и их ИТ-продуктов' },
];

export function isImportCatalogType(value: unknown): value is ImportCatalogType {
  return importCatalogOptions.some((option) => option.id === value);
}

export interface ImportTargetField {
  id: string;
  label: string;
  description?: string;
}

/** Demo-only field definitions. Real previews carry the server-owned contract. */
export const importTargetFields: ImportTargetField[] = [
  { id: 'university.name', label: 'Название ВУЗа' },
  { id: 'university.city', label: 'Город ВУЗа' },
  { id: 'vendor.name', label: 'Вендор' },
  { id: 'product.name', label: 'Название продукта' },
  { id: 'product.version', label: 'Версия продукта' },
  { id: 'vendor_contact.full_name', label: 'ФИО контакта вендора' },
  { id: 'vendor_contact.phone', label: 'Телефон контакта вендора' },
  { id: 'vendor_contact.email', label: 'Почта контакта вендора' },
  { id: 'vendor_contact.communication_method', label: 'Способ связи' },
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
  { id: 'responsible.email', label: 'Почта ответственного' },
  { id: 'responsible.phone', label: 'Телефон ответственного' },
  { id: 'responsible.role', label: 'Роль ответственного' },
  { id: 'university_responsibles', label: 'Ответственные от ВУЗа' },
];

/** The import service validates these values for every catalog row. */
export const requiredImportFields: Record<ImportCatalogType, readonly string[]> = {
  universities: ['university.name'],
  directions: ['direction.code'],
  products: ['vendor.name', 'product.name'],
  responsibles: ['responsible.full_name', 'responsible.email'],
  licenses: ['university.name', 'contract.contract_number', 'license.expires_at'],
  vendor_contacts: ['vendor.name', 'product.name', 'vendor_contact.full_name', 'vendor_contact.email'],
};

const importFieldPrefixes: Record<ImportCatalogType, readonly string[]> = {
  universities: ['university.'],
  directions: ['direction.'],
  products: ['vendor.', 'product.'],
  responsibles: ['responsible.'],
  vendor_contacts: ['vendor.', 'product.', 'vendor_contact.'],
  licenses: ['university.', 'vendor.', 'product.', 'direction.', 'program.', 'contract.', 'license.', 'responsible.', 'university_responsibles'],
};

export function targetFieldsForCatalog(type: ImportCatalogType): ImportTargetField[] {
  return importTargetFields.filter((field) => importFieldPrefixes[type].some((prefix) => field.id.startsWith(prefix)));
}

export interface ImportPreviewResponse {
  file_id: string;
  filename: string;
  headers: string[];
  preview: Array<Record<string, string | number | boolean | null>>;
  row_count: number;
  detected_sheet?: string;
  target_fields?: Array<ImportTargetField & { required?: boolean }>;
  required_fields?: string[];
  suggested_mapping?: Record<string, string>;
  warnings?: string[];
}

export function previewTargetFields(preview: ImportPreviewResponse, type: ImportCatalogType): ImportTargetField[] {
  return preview.target_fields ?? (isMockDataSource ? targetFieldsForCatalog(type) : []);
}

export function previewRequiredFields(preview: ImportPreviewResponse, type: ImportCatalogType): readonly string[] {
  return preview.required_fields ?? (isMockDataSource ? requiredImportFields[type] : []);
}

export function previewSuggestedMapping(preview: ImportPreviewResponse, type: ImportCatalogType): Record<string, string> {
  return preview.suggested_mapping ?? (isMockDataSource ? autoMapImportHeaders(preview.headers, type) : {});
}

export interface ImportOptions {
  skip_header: boolean;
  update_existing: boolean;
  dry_run: boolean;
  catalog_type: ImportCatalogType;
  filename?: string;
}

export interface ImportRowError {
  row: number;
  field: string;
  sourceField?: string;
  code?: string;
  error: string;
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
    return [{ row, field: stringValue(item.field) ?? 'row', sourceField: stringValue(item.source_field), code: stringValue(item.code), error: stringValue(item.error ?? item.message) ?? 'Ошибка строки' }];
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
    errors_total: numberValue(source.errors_total),
    truncated: Boolean(source.truncated),
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
  const rawCatalogType = stringValue(item.catalog_type ?? item.catalogType);
  const catalogType = importCatalogOptions.some((option) => option.id === rawCatalogType)
    ? rawCatalogType as ImportCatalogType
    : undefined;
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
    catalogType,
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

export async function uploadImportPreview(file: File, catalogType: ImportCatalogType, signal?: AbortSignal, onProgress?: (value: number) => void): Promise<ImportPreviewResponse> {
  const validationError = validateImportFile(file);
  if (validationError) throw new ApiRequestError(400, { detail: validationError }, validationError);
  onProgress?.(0);
  const result = await fromDataSource({
    mock: () => mockUploadImportPreview(file),
    real: () => realUploadImportPreview(file, catalogType, signal, onProgress),
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

export async function downloadImportReport(jobId: string): Promise<Blob> {
  const result = await apiDownload(`/api/v1/import/jobs/${encodeURIComponent(jobId)}/report`);
  if (!result.ok) throw new ApiRequestError(result.status, result.body, 'Не удалось скачать отчёт импорта.', result.error);
  return result.data;
}

export function importTargetLabel(id: string, preview?: ImportPreviewResponse): string {
  return preview?.target_fields?.find((field) => field.id === id)?.label
    ?? (isMockDataSource ? importTargetFields.find((field) => field.id === id)?.label : undefined)
    ?? id;
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
  'university.city': ['город вуза', 'город университета', 'university city'],
  'vendor.name': ['вендор', 'поставщик', 'компания', 'vendor', 'vendor name'],
  'product.name': ['продукт', 'по', 'название продукта', 'программное обеспечение', 'product', 'product name'],
  'product.version': ['версия', 'версия продукта', 'product version', 'version'],
  'vendor_contact.full_name': ['фио контакта', 'контактное лицо', 'фио', 'contact name'],
  'vendor_contact.phone': ['телефон контакта', 'телефон', 'contact phone'],
  'vendor_contact.email': ['почта контакта', 'почта', 'email', 'contact email'],
  'vendor_contact.communication_method': ['способ связи', 'канал связи', 'communication method'],
  'direction.code': ['код направления', 'код ит направления', 'direction code'],
  'direction.name': ['направление', 'ит направление', 'название направления', 'direction', 'direction name'],
  'program.name': ['программа', 'ит программа', 'название программы', 'program', 'program name'],
  'program.description': ['описание программы', 'описание', 'program description'],
  'contract.contract_number': ['номер договора', 'договор', 'contract number', 'contract'],
  'license.signed_at': ['подписание лицензии', 'дата подписания', 'дата лицензии', 'license signed at', 'signed at'],
  'license.expires_at': ['срок действия лицензии', 'срок действия', 'год окончания', 'год действия лицензии', 'license expires at', 'expires at'],
  'license.transfer_status': ['статус передачи', 'статус по передаче', 'статус лицензии', 'transfer status'],
  'license.comment': ['комментарий', 'комментарий к лицензии', 'примечание', 'comment'],
  'responsible.full_name': ['фио', 'фио менеджера', 'ответственный', 'ответственный менеджер', 'responsible', 'responsible full name'],
  'responsible.email': ['email ответственного', 'почта ответственного', 'email', 'почта'],
  'responsible.phone': ['телефон ответственного', 'телефон'],
  'responsible.role': ['роль ответственного', 'роль', 'должность'],
  university_responsibles: ['ответственные от вуза', 'контакты вуза', 'представители вуза', 'university responsibles'],
};

export function autoMapImportHeaders(headers: string[], catalogType: ImportCatalogType = 'licenses'): Record<string, string> {
  const mapping: Record<string, string> = {};
  const usedTargets = new Set<string>();
  const fields = targetFieldsForCatalog(catalogType);
  for (const header of headers) {
    const normalized = normalizeImportHeader(header);
    if (!normalized) continue;
    let candidate: string | undefined;
    for (const field of fields) {
      if (usedTargets.has(field.id)) continue;
      const fieldName = normalizeImportHeader(field.id.replace('.', ' '));
      const aliases = (importHeaderAliases[field.id] ?? []).map(normalizeImportHeader);
      if (normalized === fieldName || aliases.includes(normalized)) {
        candidate = field.id;
        break;
      }
      if (!candidate && (normalized.includes(fieldName) || aliases.some((alias) => alias.length > 3 && (normalized.includes(alias) || alias.includes(normalized))))) candidate = field.id;
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

/** Refresh only server-state families affected by a completed real import. */
export async function invalidateImportedDomains(queryClient: QueryClient, type: ImportCatalogType | undefined): Promise<void> {
  const affected = [
    queryKeys.catalogs.references,
    queryKeys.reports.filterOptions,
    queryKeys.audit.all,
  ] as readonly (readonly unknown[])[];
  const keys: Array<readonly unknown[]> = [...affected];
  if (type === 'universities' || type === 'licenses') {
    keys.push(queryKeys.universities.all, queryKeys.universities.passports, queryKeys.dashboard.overview, queryKeys.dashboard.analytics);
  }
  if (type === 'products' || type === 'vendor_contacts' || type === 'licenses') {
    keys.push(queryKeys.catalogs.family('products'), queryKeys.universities.productsAll, queryKeys.universities.passports);
  }
  if (type === 'directions' || type === 'licenses') {
    keys.push(queryKeys.catalogs.family('directions'), queryKeys.universities.programsAll, queryKeys.universities.passports, queryKeys.dashboard.overview, queryKeys.dashboard.analytics);
  }
  if (type === 'responsibles' || type === 'licenses') {
    keys.push(queryKeys.catalogs.family('responsibles'), queryKeys.universities.responsiblesAll, queryKeys.universities.passports);
  }
  if (type === 'universities') keys.push(queryKeys.catalogs.family('universities'));
  if (type === 'licenses') keys.push(queryKeys.universities.licensesAll, queryKeys.universities.documentsAll);
  await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export { MAX_FILE_BYTES };
