export type UserRole = 'user' | 'manager' | 'admin';

export type KeycloakRole = UserRole | 'curator';

export const roleLabels: Record<UserRole, string> = {
  user: 'Пользователь',
  manager: 'Менеджер',
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
  authSource: 'mock' | 'keycloak';
}
