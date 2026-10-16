'use client';

import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { mockListAdminUsers } from '@/shared/mocks/api-adapter';
import { getUniversities, type UniversityListQuery } from './universities-repository';
import { userRoleLabels, type AdminUser } from './users-repository';
import { realListAdminUsers } from './real-api-adapter';
import { buildNetworkGraphData, GraphTooLargeError, MAX_GRAPH_NODES, type UniversityInput } from './network-graph-data';
import type { NetworkGraphData } from './network-graph-data';
import type { UserRole } from '@/shared/types/user';

export type { NetworkNodeKind, NetworkUserNode, NetworkUniversityNode, NetworkNode, NetworkEdge, NetworkGraphData } from './network-graph-data';

export const networkGraphQueryKey = ['network-graph'] as const;

const PAGE_SIZE = 100;

const EMPTY_UNIVERSITY_QUERY: UniversityListQuery = {
  filters: {
    search: '',
    city: '',
    externalSource: '',
    universityIds: [],
    programIds: [],
    productIds: [],
    responsibleIds: [],
    workflowStageId: '',
    dateFrom: '',
    dateTo: '',
  },
  sort: 'name',
  order: 'asc',
  page: 1,
  pageSize: PAGE_SIZE,
};

async function fetchAllUniversities(signal?: AbortSignal): Promise<UniversityInput[]> {
  const all: UniversityInput[] = [];
  let page = 1;
  for (;;) {
    const result = await getUniversities({ ...EMPTY_UNIVERSITY_QUERY, page }, signal);
    if (result.total > MAX_GRAPH_NODES) throw new GraphTooLargeError();
    all.push(...result.items.map((item) => ({ id: item.id, name: item.name, city: item.city })));
    if (all.length >= result.total || result.items.length === 0) break;
    page += 1;
  }
  return all;
}

export function buildNetworkGraph(
  users: AdminUser[],
  universities: UniversityInput[],
): NetworkGraphData {
  return buildNetworkGraphData(users, universities, userRoleLabels);
}

async function fetchAllAdminUsers(): Promise<AdminUser[]> {
  const all: AdminUser[] = [];
  let page = 1;
  for (;;) {
    const result = await realListAdminUsers({ search: '', role: 'all', page, pageSize: PAGE_SIZE });
    if (result.total > MAX_GRAPH_NODES) throw new GraphTooLargeError();
    all.push(...result.items);
    if (all.length >= result.total || result.items.length === 0) break;
    page += 1;
  }
  return all;
}

interface MeDto {
  id: string;
  username: string | null;
  email: string | null;
  name: string | null;
  roles: string[];
  scope: { kind: string; university_ids: string[] };
}

function toUserRole(roles: string[]): UserRole {
  if (roles.includes('admin')) return 'admin';
  if (roles.includes('manager')) return 'manager';
  return 'user';
}

/** Ego-graph for viewers without the admin.users permission. */
async function getOwnNetworkGraph(signal?: AbortSignal): Promise<NetworkGraphData> {
  const result = await apiFetch<MeDto>('/api/v1/auth/me', { signal });
  if (!result.ok) {
    throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить данные пользователя.', result.error);
  }
  const dto = result.data;
  const name = dto.name?.trim() || dto.username || 'Пользователь';
  const user: AdminUser = {
    id: dto.id,
    username: dto.username ?? '',
    name,
    email: dto.email ?? '',
    role: toUserRole(dto.roles),
    status: 'active',
    scope: dto.scope.kind === 'all'
      ? { kind: 'all' }
      : { kind: 'universities', universityIds: dto.scope.university_ids },
    lastLoginAt: null,
  };
  const universities = await fetchAllUniversities(signal);
  return { ...buildNetworkGraph([user], universities), scope: 'own' };
}

async function getRealNetworkGraph(signal?: AbortSignal): Promise<NetworkGraphData> {
  try {
    const [users, universities] = await Promise.all([
      fetchAllAdminUsers(),
      fetchAllUniversities(signal),
    ]);
    return buildNetworkGraph(users, universities);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 403) {
      return getOwnNetworkGraph(signal);
    }
    throw error;
  }
}

function fetchAllMockAdminUsers(): AdminUser[] {
  const all: AdminUser[] = [];
  let page = 1;
  for (;;) {
    const result = mockListAdminUsers({ search: '', role: 'all', page, pageSize: PAGE_SIZE });
    all.push(...result.items);
    if (all.length >= result.total || result.items.length === 0) break;
    page += 1;
  }
  return all;
}

async function getMockNetworkGraph(signal?: AbortSignal): Promise<NetworkGraphData> {
  const universities = await fetchAllUniversities(signal);
  return buildNetworkGraph(fetchAllMockAdminUsers(), universities);
}

export async function getNetworkGraph(signal?: AbortSignal): Promise<NetworkGraphData> {
  return fromDataSource({
    mock: () => getMockNetworkGraph(signal),
    real: () => getRealNetworkGraph(signal),
    signal,
  });
}
