import { roleLabels, type AuthUser, type UserRole } from '@/shared/types/user';

const configuredRole = process.env.NEXT_PUBLIC_MOCK_ROLE;
const role: UserRole = configuredRole === 'user' || configuredRole === 'manager' || configuredRole === 'admin'
  ? configuredRole
  : 'admin';

export const currentUser: AuthUser = {
  id: '1',
  username: 'admin',
  name: 'Анна Иванова',
  email: 'anna.ivanova@example.ru',
  role,
  roleLabel: roleLabels[role],
  initials: 'АИ',
  rawRoles: [role],
  authSource: 'mock',
};
