export type UserRole = 'user' | 'manager' | 'admin';

export type KeycloakRole = UserRole;

export type DataScopeKind = 'own' | 'group' | 'all' | 'deny';

export interface DataScope {
  kind: DataScopeKind;
  universityIds: string[];
}

export const roleLabels: Record<UserRole, string> = {
  user: 'Пользователь',
  manager: 'Руководитель',
  admin: 'Администратор',
};

export interface AuthUser {
  id: string;
  username: string;
  name: string;
  email: string;
  role: UserRole;
  roleLabel: string;
  initials: string;
  rawRoles: string[];
  permissions: string[];
  scope: DataScope;
  authSource: 'mock' | 'keycloak';
}
