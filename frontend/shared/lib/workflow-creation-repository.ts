'use client';

import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { queryKeys } from './query-keys';
import {
  mockGetCatalogReferenceData,
  mockListCatalogItems,
} from '@/shared/mocks/api-adapter';
import type { WorkflowInstanceApiRecord, WorkflowPage } from './universities-repository';

export interface WizardDirection {
  id: string;
  name: string;
  code: string;
}

export interface WizardProgram {
  id: string;
  name: string;
  directionId: string;
  directionName: string;
}

export interface WizardProduct {
  id: string;
  name: string;
  vendorName: string;
  version: string;
}

export const wizardDirectionsQueryKey = ['workflow-wizard', 'directions'] as const;
export const wizardProgramsQueryKey = (directionId: string) => ['workflow-wizard', 'programs', directionId] as const;
export const wizardProductsQueryKey = (directionId: string) => ['workflow-wizard', 'products', directionId] as const;
export const universityWorkflowInstancesQueryKey = (universityId: string) =>
  [...queryKeys.universities.workflowInstances(1, 1).slice(0, 2), 'university', universityId] as const;

interface ApiPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

interface ApiDirection {
  id: string;
  code: string;
  name: string;
}

interface ApiProgram {
  id: string;
  name: string;
  direction_id: string;
  direction_name: string | null;
}

interface ApiProduct {
  id: string;
  name: string;
  vendor_name: string | null;
  version: string;
}

function fail(status: number, body: unknown, error: string, fallback: string): never {
  throw new ApiRequestError(status, body, fallback, error);
}

async function allPages<T>(pathWithQuery: string, message: string, signal?: AbortSignal): Promise<T[]> {
  const separator = pathWithQuery.includes('?') ? '&' : '?';
  const firstResult = await apiFetch<ApiPage<T>>(`/api/v1/${pathWithQuery}${separator}page=1&page_size=100`, { signal });
  if (!firstResult.ok) return fail(firstResult.status, firstResult.body, firstResult.error, message);
  const first = firstResult.data;
  const pages = Math.ceil(first.total / first.page_size);
  if (pages <= 1) return first.items;
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, index) => index + 2).map(async (page) => {
      const result = await apiFetch<ApiPage<T>>(`/api/v1/${pathWithQuery}${separator}page=${page}&page_size=100`, { signal });
      if (!result.ok) return fail(result.status, result.body, result.error, message);
      return result.data.items;
    }),
  );
  return [first.items, ...rest].flat();
}

export async function listWizardDirections(signal?: AbortSignal): Promise<WizardDirection[]> {
  return fromDataSource({
    domain: 'catalogs',
    signal,
    mock: () => mockGetCatalogReferenceData().directions.map((item) => ({
      id: item.id,
      name: item.name,
      code: item.description ?? '',
    })),
    real: async () => (await allPages<ApiDirection>('directions', 'Не удалось загрузить направления.', signal)).flatMap((item) =>
      item.id && item.name ? [{ id: item.id, name: item.name, code: item.code ?? '' }] : [],
    ),
  });
}

export async function listWizardPrograms(directionId: string, signal?: AbortSignal): Promise<WizardProgram[]> {
  return fromDataSource({
    domain: 'catalogs',
    signal,
    mock: async () => [],
    real: async () => (await allPages<ApiProgram>(
      `programs?direction_id=${encodeURIComponent(directionId)}`,
      'Не удалось загрузить программы направления.',
      signal,
    )).flatMap((item) => item.id && item.name
      ? [{ id: item.id, name: item.name, directionId: item.direction_id ?? directionId, directionName: item.direction_name ?? '' }]
      : []),
  });
}

export async function listWizardProducts(directionId: string, signal?: AbortSignal): Promise<WizardProduct[]> {
  return fromDataSource({
    domain: 'catalogs',
    signal,
    mock: async () => {
      const page = mockListCatalogItems({ type: 'products', search: '', page: 1, pageSize: 100 });
      return page.items.flatMap((item) => item.type === 'products'
        ? [{ id: item.id, name: item.name, vendorName: item.vendorName, version: item.version }]
        : []);
    },
    real: async () => (await allPages<ApiProduct>(
      `products?direction_id=${encodeURIComponent(directionId)}`,
      'Не удалось загрузить продукты направления.',
      signal,
    )).flatMap((item) => item.id && item.name
      ? [{ id: item.id, name: item.name, vendorName: item.vendor_name ?? '', version: item.version ?? '' }]
      : []),
  });
}

export async function listUniversityWorkflowInstances(
  universityId: string,
  signal?: AbortSignal,
): Promise<WorkflowInstanceApiRecord[]> {
  return fromDataSource({
    domain: 'workflow',
    signal,
    mock: async () => [],
    real: async () => {
      const result = await apiFetch<WorkflowPage<WorkflowInstanceApiRecord>>(
        `/api/v1/workflow/instances?university_id=${encodeURIComponent(universityId)}&page=1&page_size=100`,
        { signal },
      );
      if (!result.ok) return fail(result.status, result.body, result.error, 'Не удалось загрузить Workflow вуза.');
      const first = result.data;
      const pages = Math.ceil(first.total / first.page_size);
      if (pages <= 1) return first.items;
      const rest = await Promise.all(
        Array.from({ length: pages - 1 }, (_, index) => index + 2).map(async (page) => {
          const pageResult = await apiFetch<WorkflowPage<WorkflowInstanceApiRecord>>(
            `/api/v1/workflow/instances?university_id=${encodeURIComponent(universityId)}&page=${page}&page_size=100`,
            { signal },
          );
          if (!pageResult.ok) return fail(pageResult.status, pageResult.body, pageResult.error, 'Не удалось загрузить Workflow вуза.');
          return pageResult.data.items;
        }),
      );
      return [first.items, ...rest].flat();
    },
  });
}

export function wizardProductLabel(product: WizardProduct): string {
  return [product.name, product.vendorName, product.version].filter(Boolean).join(' · ');
}
