import { apiFetch } from './api-client';
import { ApiRequestError } from './api-errors';
import { getKeycloakAccessClaims } from './keycloak-adapter';
import { roleLabels, type AuthUser, type DataScope, type UserRole } from '@/shared/types/user';

export interface CurrentUserDto {
  id: string;
  username: string | null;
  email: string | null;
  name: string | null;
  roles: string[];
  permissions: string[];
}

const knownRoles = new Set<UserRole>(['user', 'manager', 'curator', 'admin']);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isUserRole(value: string): value is UserRole {
  return knownRoles.has(value as UserRole);
}

function primaryRole(roles: readonly UserRole[]): UserRole {
  return (['admin', 'manager', 'curator', 'user'] as const).find((role) => roles.includes(role)) ?? 'user';
}

function initialsFor(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('ru-RU') || 'П';
}

function dataScopeFor(roles: readonly UserRole[], universityIds: readonly string[]): DataScope {
  if (roles.includes('admin')) return { kind: 'all', universityIds: [] };
  const kind = roles.includes('manager') ? 'group' : roles.includes('user') ? 'own' : 'deny';
  return {
    kind,
    universityIds: kind === 'deny'
      ? []
      : [...new Set(universityIds.filter((id) => uuidPattern.test(id)))].sort(),
  };
}

/** The single backend DTO -> frontend current-user boundary. */
export function currentUserFromDto(dto: CurrentUserDto, universityIds: readonly string[]): AuthUser {
  const roles = [...new Set(dto.roles.filter(isUserRole))];
  const role = primaryRole(roles);
  const username = dto.username?.trim() ?? '';
  const name = dto.name?.trim() || username || 'Пользователь';

  return {
    id: dto.id,
    username,
    name,
    email: dto.email?.trim() ?? '',
    role,
    roleLabel: roleLabels[role],
    initials: initialsFor(name),
    rawRoles: roles,
    permissions: [...new Set(dto.permissions.filter((permission) => Boolean(permission.trim())).map((permission) => permission.trim()))].sort(),
    scope: dataScopeFor(roles, universityIds),
    authSource: 'keycloak',
  };
}

export async function getCurrentUser(): Promise<AuthUser> {
  const result = await apiFetch<CurrentUserDto>('/api/v1/auth/me');
  if (!result.ok) {
    throw new ApiRequestError(result.status, result.body, 'Не удалось загрузить данные текущего пользователя.', result.error);
  }
  return currentUserFromDto(result.data, getKeycloakAccessClaims().universityIds);
}
