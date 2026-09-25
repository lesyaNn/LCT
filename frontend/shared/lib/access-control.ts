import type { AuthUser, UserRole } from '@/shared/types/user';

export function hasRole(user: AuthUser | null | undefined, role: UserRole): boolean {
  return Boolean(user?.rawRoles.includes(role));
}

export function hasPermission(user: AuthUser | null | undefined, permission: string): boolean {
  return Boolean(user && (user.permissions.includes('*') || user.permissions.includes(permission)));
}

export function hasAnyPermission(
  user: AuthUser | null | undefined,
  permissions: readonly string[],
): boolean {
  return permissions.length === 0 || permissions.some((permission) => hasPermission(user, permission));
}
