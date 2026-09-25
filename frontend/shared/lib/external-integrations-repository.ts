import { normalizeApiError } from './api-errors';
import { fromDataSource, isMockDataSourceFor } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockCreateWorkflowFromExternal,
  mockGetExternalDashboardMetrics,
  mockGetUniversityExternalData,
} from '../mocks/api-adapter';
import {
  realCreateWorkflowFromExternal,
  realGetUniversityExternalData,
} from './real-api-adapter';

export type ExternalDataSource = 'lms' | 'website';
export type ExternalRecordSource = ExternalDataSource | 'manual';

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
}

export interface ExternalDashboardMetrics {
  websiteApplications7d: number | null;
  lmsStudents: number | null;
  websiteSyncedAt: string | null;
  lmsSyncedAt: string | null;
}

export const universityExternalDataQueryKey = (id: string, source: ExternalDataSource) =>
  queryKeys.universities.externalData(id, source);

export async function getUniversityExternalData(
  universityId: string,
  source: ExternalDataSource,
  signal?: AbortSignal,
): Promise<UniversityExternalData> {
  return fromDataSource({
    mock: () => mockGetUniversityExternalData(universityId, source),
    real: () => realGetUniversityExternalData(universityId, source, signal),
    signal,
  });
}

export async function createWorkflowFromExternal(
  input: CreateWorkflowFromExternalInput,
): Promise<CreateWorkflowFromExternalResult> {
  if (!isMockDataSourceFor('workflow')) throw new Error('Создание Workflow будет подключено на этапе 6.');
  return fromDataSource({
    mock: () => mockCreateWorkflowFromExternal(input),
    real: () => realCreateWorkflowFromExternal(input),
  });
}

/**
 * The current backend contract does not expose dashboard-level integration metrics.
 * Mock mode keeps the UI demonstrable; real mode returns null values until that
 * aggregate endpoint is published, without inventing a client-side dataset.
 */
export async function getExternalDashboardMetrics(): Promise<ExternalDashboardMetrics> {
  return fromDataSource({
    mock: () => mockGetExternalDashboardMetrics(),
    real: async () => ({
      websiteApplications7d: null,
      lmsStudents: null,
      websiteSyncedAt: null,
      lmsSyncedAt: null,
    }),
  });
}

export function isExternalSourceUnavailable(error: unknown): boolean {
  return normalizeApiError(error).code === 'EXTERNAL_SOURCE_UNAVAILABLE';
}
