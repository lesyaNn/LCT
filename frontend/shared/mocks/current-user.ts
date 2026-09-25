import { roleLabels, type AuthUser, type UserRole } from '@/shared/types/user';

const configuredRole = process.env.NEXT_PUBLIC_MOCK_ROLE;
const role: UserRole = configuredRole === 'user' || configuredRole === 'manager' || configuredRole === 'curator' || configuredRole === 'admin'
  ? configuredRole
  : 'admin';

const mockPermissions: Record<UserRole, string[]> = {
  user: ['analytics.read', 'catalog.read', 'import.read', 'reports.create', 'reports.read', 'university.read', 'workflow.read'],
  manager: ['analytics.read', 'analytics.extended', 'audit.read', 'catalog.read', 'import.read', 'import.write', 'reports.create', 'reports.read', 'university.edit', 'university.read', 'workflow.read'],
  curator: ['catalog.read', 'import.read', 'university.edit', 'university.read', 'workflow.read'],
  admin: ['*'],
};

export const currentUser: AuthUser = {
  id: '1',
  username: 'admin',
  name: 'Анна Иванова',
  email: 'anna.ivanova@example.ru',
  role,
  roleLabel: roleLabels[role],
  initials: 'АИ',
  rawRoles: [role],
  permissions: mockPermissions[role],
  scope: role === 'admin'
    ? { kind: 'all', universityIds: [] }
    : { kind: role === 'manager' ? 'group' : role === 'user' ? 'own' : 'deny', universityIds: [] },
  authSource: 'mock',
};
