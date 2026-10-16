import type { AdminUser } from './users-repository';
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
  scope: 'full' | 'own';
}

export interface UniversityInput {
  id: string;
  name: string;
  city: string;
}

export const MAX_GRAPH_NODES = 120;
export const MAX_GRAPH_EDGES = 250;

export class GraphTooLargeError extends Error {
  constructor() {
    super('Слишком много связей для графа. Используйте список пользователей.');
    this.name = 'GraphTooLargeError';
  }
}

export class GraphScopeChangedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GraphScopeChangedError';
  }
}

/** Apply one graph edit to a freshly fetched user, preserving other assignments and role. */
export function graphScopeChange(user: AdminUser, universityId: string, action: 'add' | 'remove') {
  if (user.scope.kind !== 'universities') {
    throw new GraphScopeChangedError('Доступ пользователя изменился. Обновите граф.');
  }
  const current = new Set(user.scope.universityIds);
  if (action === 'remove' && !current.has(universityId)) {
    throw new GraphScopeChangedError('Связь уже изменена. Обновите граф.');
  }
  if (action === 'add') current.add(universityId);
  else current.delete(universityId);
  return { role: user.role, scope: { kind: 'universities' as const, universityIds: [...current] } };
}

export function buildNetworkGraphData(
  users: AdminUser[],
  universities: UniversityInput[],
  roleLabels: Record<UserRole, string>,
): NetworkGraphData {
  const uniqueUsers = [...new Map(users.map((user) => [user.id, user])).values()]
    .sort((a, b) => a.id.localeCompare(b.id));
  const uniqueUniversities = [...new Map(universities.map((university) => [university.id, university])).values()]
    .sort((a, b) => a.id.localeCompare(b.id));
  if (uniqueUsers.length + uniqueUniversities.length > MAX_GRAPH_NODES) {
    throw new GraphTooLargeError();
  }
  const universityIds = new Set(uniqueUniversities.map((item) => item.id));
  const edges: NetworkEdge[] = [];
  const seenEdges = new Set<string>();
  const userDegree = new Map<string, number>();
  const universityDegree = new Map<string, number>();

  // Explicit assignments only; an all-access admin has no full-mesh edges.
  for (const user of uniqueUsers) {
    if (user.scope.kind !== 'universities') continue;
    for (const universityId of user.scope.universityIds) {
      if (!universityIds.has(universityId)) continue;
      const key = `${user.id}::${universityId}`;
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      edges.push({ id: key, userId: user.id, universityId });
      if (edges.length > MAX_GRAPH_EDGES) throw new GraphTooLargeError();
      userDegree.set(user.id, (userDegree.get(user.id) ?? 0) + 1);
      universityDegree.set(universityId, (universityDegree.get(universityId) ?? 0) + 1);
    }
  }
  edges.sort((a, b) => a.id.localeCompare(b.id));

  const nodes: NetworkNode[] = [
    ...uniqueUsers.map((user): NetworkUserNode => ({
      id: user.id,
      kind: 'user',
      label: user.name,
      username: user.username,
      email: user.email,
      role: user.role,
      roleLabel: roleLabels[user.role],
      allAccess: user.scope.kind === 'all',
      degree: userDegree.get(user.id) ?? 0,
    })),
    ...uniqueUniversities.map((university): NetworkUniversityNode => ({
      id: university.id,
      kind: 'university',
      label: university.name,
      city: university.city,
      degree: universityDegree.get(university.id) ?? 0,
    })),
  ];

  return {
    nodes,
    edges,
    usersCount: uniqueUsers.length,
    universitiesCount: uniqueUniversities.length,
    linksCount: edges.length,
    isolatedCount: nodes.filter((node) => node.degree === 0 && !(node.kind === 'user' && node.allAccess)).length,
    scope: 'full',
  };
}
