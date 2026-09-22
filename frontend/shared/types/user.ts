import type { UserRole } from './navigation';

export interface MockUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  roleLabel: string;
  initials: string;
}
