'use client';

import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { fromDataSource } from './data-source';
import { mockListAdminUsers } from '@/shared/mocks/api-adapter';
import { getUniversities, type UniversityListQuery } from './universities-repository';
import { userRoleLabels, type AdminUser } from './users-repository';
import { realListAdminUsers } from './real-api-adapter';
import type { UserRole } from '@/shared/types/user';

export type NetworkNodeKind = 'user' | 'university';

export interface NetworkUserNode {
  id: string;
  kind: 'user';
  label: string;
  username: string;
  email: string;
  role: UserRole;
  roleLabel: string;
  /** Administrators implicitly see every university: no explicit edges. */
  allAccess: boolean;
  degree: number;
}

export interface NetworkUniversityNode {
  id: string;
  kind: 'university';
  label: string;
  city: string;
  degree: number;
}

export type NetworkNode = NetworkUserNode | NetworkUniversityNode;

export interface NetworkEdge {
  id: string;
  userId: string;
  universityId: string;
}

export interface NetworkGraphData {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  usersCount: number;
  universitiesCount: number;
  linksCount: number;
  isolatedCount: number;
  /** Non-admin viewers only get their own subgraph (RBAC: no user list). */
  scope: 'full' | 'own';
}

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

interface UniversityInput {
  id: string;
  name: string;
  city: string;
}

async function fetchAllUniversities(signal?: AbortSignal): Promise<UniversityInput[]> {
  const all: UniversityInput[] = [];
  let page = 1;
  for (;;) {
    const result = await getUniversities({ ...EMPTY_UNIVERSITY_QUERY, page }, signal);
    all.push(...result.items.map((item) => ({ id: item.id, name: item.name, city: item.city })));
    if (all.length >= result.total || result.items.length === 0) break;
    page += 1;
  }
  return all;
}

function toUserNode(user: AdminUser, degree: number): NetworkUserNode {
  return {
    id: user.id,
    kind: 'user',
    label: user.name,
    username: user.username,
    email: user.email,
    role: user.role,
    roleLabel: userRoleLabels[user.role],
    allAccess: user.scope.kind === 'all',
    degree,
  };
}

export function buildNetworkGraph(
  users: AdminUser[],
  universities: UniversityInput[],
): NetworkGraphData {
  const universityIds = new Set(universities.map((item) => item.id));
  const nodes: NetworkNode[] = [];
  const edges: NetworkEdge[] = [];
  const seenEdges = new Set<string>();
  const degree = new Map<string, number>();
  const bump = (id: string) => degree.set(id, (degree.get(id) ?? 0) + 1);

  // Explicit scope assignments only: an "all" scope (admin) draws no edges,
  // otherwise the graph would be a meaningless full mesh.
  for (const user of users) {
    if (user.scope.kind !== 'universities') continue;
    for (const universityId of user.scope.universityIds) {
      if (!universityIds.has(universityId)) continue;
      const key = `${user.id}::${universityId}`;
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      edges.push({ id: key, userId: user.id, universityId });
      bump(user.id);
      bump(universityId);
    }
  }

  for (const user of users) {
    nodes.push(toUserNode(user, degree.get(user.id) ?? 0));
  }
  for (const university of universities) {
    nodes.push({
      id: university.id,
      kind: 'university',
      label: university.name,
      city: university.city,
      degree: degree.get(university.id) ?? 0,
    });
  }

  return {
    nodes,
    edges,
    usersCount: users.length,
    universitiesCount: universities.length,
    linksCount: edges.length,
    isolatedCount: nodes.filter((node) => node.degree === 0 && !(node.kind === 'user' && node.allAccess)).length,
    scope: 'full',
  };
}

async function fetchAllAdminUsers(): Promise<AdminUser[]> {
  const all: AdminUser[] = [];
  let page = 1;
  for (;;) {
    const result = await realListAdminUsers({ search: '', role: 'all', page, pageSize: PAGE_SIZE });
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
