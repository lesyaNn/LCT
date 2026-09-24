import type { UserRole } from '@/shared/types/user';
import { ApiRequestError } from './api-errors';
import { fromDataSource, isMockDataSource } from './data-source';
import { queryKeys } from './query-keys';
import { universityFilterOptions } from './universities-repository';
import {
  mockAssignUniversityResponsible,
  mockBlockAdminUser,
  mockInviteAdminUser,
  mockListAdminUsers,
  mockListResponsibleCandidates,
  mockResetAdminUserPassword,
  mockUpdateAdminUser,
} from '@/shared/mocks/api-adapter';
import {
  realAssignUniversityResponsible,
  realBlockAdminUser,
  realInviteAdminUser,
  realListAdminUsers,
  realListResponsibleCandidates,
  realResetAdminUserPassword,
  realUpdateAdminUser,
} from './real-api-adapter';

export type AdminUserStatus = 'active' | 'blocked';
export type AdminUserScope =
  | { kind: 'all'; universityIds?: undefined }
  | { kind: 'universities'; universityIds: string[] };

export interface AdminUser {
  id: string;
  username: string;
  name: string;
  email: string;
  role: UserRole;
  status: AdminUserStatus;
  scope: AdminUserScope;
  lastLoginAt: string | null;
}

export interface AdminUserListQuery {
  search: string;
  role: UserRole | 'all';
  page: number;
  pageSize: number;
}

export interface AdminUserListResult {
  items: AdminUser[];
  page: number;
  pageSize: number;
  total: number;
}

export interface AdminUserUpdateInput {
  role: UserRole;
  scope: AdminUserScope;
}

export interface InviteAdminUserInput {
  name: string;
  username: string;
  email: string;
  role: UserRole;
  scope: AdminUserScope;
}

export interface ResponsibleCandidate {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface ResponsibleAssignmentInput {
  universityId: string;
  responsibleId: string;
  reason: string;
}

export interface UsersApiCapabilities {
  list: boolean;
  updateRoleAndScope: boolean;
  block: boolean;
  invite: boolean;
  passwordReset: boolean;
  responsibleAssignment: boolean;
}

export const USERS_API_CAPABILITIES: UsersApiCapabilities = isMockDataSource
  ? { list: true, updateRoleAndScope: true, block: true, invite: true, passwordReset: true, responsibleAssignment: true }
  : { list: true, updateRoleAndScope: false, block: false, invite: false, passwordReset: false, responsibleAssignment: true };

export const adminUsersQueryKeys = {
  all: queryKeys.users.all,
  list: queryKeys.users.list,
  detail: queryKeys.users.detail,
  responsibleCandidates: queryKeys.users.responsibleCandidates,
  access: queryKeys.users.access,
};

export const userRoleLabels: Record<UserRole, string> = {
  user: 'Пользователь',
  manager: 'Менеджер',
  admin: 'Администратор',
};

export const userRoleDescriptions: Record<UserRole, string> = {
  user: 'Видит только назначенные ВУЗы и доступные рабочие разделы.',
  manager: 'Работает с назначенным контуром ВУЗов, отчётами и Workflow.',
  admin: 'Полный доступ к данным, настройкам и управлению пользователями.',
};

export const userScopeOptions = universityFilterOptions.universities;

export function scopeLabel(scope: AdminUserScope): string {
  if (scope.kind === 'all') return 'Все ВУЗы';
  if (!scope.universityIds.length) return 'Нет доступных ВУЗов';
  return scope.universityIds.length === 1
    ? '1 ВУЗ'
    : `${scope.universityIds.length} ВУЗа`;
}

export function scopeDescription(scope: AdminUserScope): string {
  if (scope.kind === 'all') return 'Доступ ко всем ВУЗам';
  if (!scope.universityIds.length) return 'Пользователь не увидит ни одного ВУЗа.';
  const names = userScopeOptions.filter((option) => scope.universityIds.includes(option.id)).map((option) => option.name);
  return names.slice(0, 2).join(', ') + (names.length > 2 ? ` и ещё ${names.length - 2}` : '');
}

export function normalizeScopeForRole(role: UserRole, scope: AdminUserScope): AdminUserScope {
  if (role === 'admin') return { kind: 'all' };
  if (role === 'user' && scope.kind === 'all') return { kind: 'universities', universityIds: [] };
  return scope;
}

export function getUserById(result: AdminUserListResult | undefined, id: string): AdminUser | undefined {
  return result?.items.find((item) => item.id === id);
}

export async function listAdminUsers(query: AdminUserListQuery): Promise<AdminUserListResult> {
  return fromDataSource({ mock: () => mockListAdminUsers(query), real: () => realListAdminUsers(query) });
}

export async function updateAdminUser(id: string, input: AdminUserUpdateInput): Promise<AdminUser> {
  return fromDataSource({ mock: () => mockUpdateAdminUser(id, input), real: () => realUpdateAdminUser(id, input) });
}

export async function setAdminUserBlocked(id: string, blocked: boolean): Promise<AdminUser> {
  return fromDataSource({ mock: () => mockBlockAdminUser(id, blocked), real: () => realBlockAdminUser(id, blocked) });
}

export async function inviteAdminUser(input: InviteAdminUserInput): Promise<AdminUser> {
  return fromDataSource({ mock: () => mockInviteAdminUser(input), real: () => realInviteAdminUser(input) });
}

export async function resetAdminUserPassword(id: string): Promise<{ status: 'requested'; actionUrl?: string }> {
  return fromDataSource({ mock: () => mockResetAdminUserPassword(id), real: () => realResetAdminUserPassword(id) });
}

export async function listResponsibleCandidates(): Promise<ResponsibleCandidate[]> {
  return fromDataSource({ mock: mockListResponsibleCandidates, real: realListResponsibleCandidates });
}

export async function assignUniversityResponsible(input: ResponsibleAssignmentInput): Promise<void> {
  if (!input.universityId || !input.responsibleId) {
    throw new ApiRequestError(400, { code: 'RESPONSIBLE_REQUIRED' }, 'Выберите нового ответственного.');
  }
  return fromDataSource({ mock: () => mockAssignUniversityResponsible(input), real: () => realAssignUniversityResponsible(input) });
}
