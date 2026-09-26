import { normalizeApiError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import type { UniversityStudentListRow } from './universities-repository';
import {
  mockCreateWorkflowFromExternal,
  mockGetExternalDashboardMetrics,
  mockGetUniversityExternalData,
} from '../mocks/api-adapter';
import {
  realCreateWorkflowFromExternal,
  realGetUniversityExternalData,
  realGetExternalDashboardMetrics,
} from './real-api-adapter';

export type ExternalDataSource = 'lms' | 'website';
export type ExternalRecordSource = ExternalDataSource | 'manual' | 'import';
export const EXTERNAL_SOURCE_LABELS = { lms: 'LMS', manual: 'Ручные данные', website: 'Сайт', import: 'Импорт' } as const;
export function externalSourceLabel(source: keyof typeof EXTERNAL_SOURCE_LABELS): string {
  return EXTERNAL_SOURCE_LABELS[source];
}

export interface ExternalStudent {
  id: string;
  name: string;
  programName: string | null;
  flow: string | null;
  progress: number | null;
  source: 'lms' | 'manual';
  syncedAt: string | null;
}

export interface ExternalApplication {
  id: string;
  universityId: string;
  programId: string | null;
  programName: string;
  applicationsCount: number;
  demandScore: number | null;
  source: 'website';
  syncedAt: string | null;
  workflowInstanceId: string | null;
}

export interface UniversityExternalData {
  universityId: string;
  source: ExternalDataSource;
  mode: 'real' | 'mock' | 'import' | 'unconfigured';
  syncedAt: string | null;
  students: ExternalStudent[];
  applications: ExternalApplication[];
}

export interface CreateWorkflowFromExternalInput {
  universityId: string;
  source: 'website';
  externalId: string;
}

export interface CreateWorkflowFromExternalResult {
  instanceId: string;
  universityId: string;
  externalId: string;
  existing: boolean;
  programId?: string | null;
}

export interface ExternalDashboardMetrics {
  mode: 'real' | 'mock' | 'import';
  websiteApplications7d: number | null;
  lmsStudents: number | null;
  websiteSyncedAt: string | null;
  lmsSyncedAt: string | null;
}

export function normalizeStudentRows(rows: UniversityStudentListRow[], external: ExternalStudent[]): Array<UniversityStudentListRow & { progress: number | null; source: keyof typeof EXTERNAL_SOURCE_LABELS; syncedAt: string | null }> {
  // Real rows already carry canonical source metadata from the Student API.
  // The legacy frontend demo fixture has no such fields; enrich it only there.
  const mockById = new Map(external.map((item) => [item.id, item]));
  return rows.map((row) => {
    const fixture = row.source ? undefined : mockById.get(row.externalId ?? '');
    return { ...row, flow: fixture?.flow ?? row.flow, progress: row.progress ?? fixture?.progress ?? null,
      source: row.source ?? (fixture ? 'lms' : 'manual'), syncedAt: row.syncedAt ?? fixture?.syncedAt ?? null };
  });
}

export const universityExternalDataQueryKey = (id: string, source: ExternalDataSource) =>
  queryKeys.universities.externalData(id, source);

export async function getUniversityExternalData(
  universityId: string,
  source: ExternalDataSource,
  signal?: AbortSignal,
): Promise<UniversityExternalData> {
  return fromDataSource({
    domain: 'passport',
    mock: () => mockGetUniversityExternalData(universityId, source),
    real: () => realGetUniversityExternalData(universityId, source, signal),
    signal,
  });
}

export async function createWorkflowFromExternal(
  input: CreateWorkflowFromExternalInput,
): Promise<CreateWorkflowFromExternalResult> {
  return fromDataSource({
    domain: 'workflow',
    mock: () => mockCreateWorkflowFromExternal(input),
    real: () => realCreateWorkflowFromExternal(input),
  });
}

export async function getExternalDashboardMetrics(): Promise<ExternalDashboardMetrics> {
  return fromDataSource({
    mock: () => mockGetExternalDashboardMetrics(),
    real: () => realGetExternalDashboardMetrics(),
  });
}

export function isExternalSourceUnavailable(error: unknown): boolean {
  return normalizeApiError(error).code === 'EXTERNAL_SOURCE_UNAVAILABLE';
}
